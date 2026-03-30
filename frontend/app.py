"""
app.py — Git Analyser frontend.

Run backend first:
  uvicorn backend.api:app --reload --port 8000

Then:
  streamlit run app.py
"""
import time
import json
import requests
import streamlit as st

API = "https://repomind-54s3.onrender.com"

st.set_page_config(page_title="Git Analyser", layout="wide")

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
.step-box {
    padding: 10px 16px;
    border-radius: 8px;
    margin-bottom: 8px;
    font-size: 15px;
    display: flex;
    align-items: center;
    gap: 10px;
}
.step-done    { background: #e6f4ea; color: #1e6e35; border-left: 4px solid #34a853; }
.step-running { background: #fff8e1; color: #7a5c00; border-left: 4px solid #fbbc04;
                animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.6} }
.section-title { font-size: 18px; font-weight: 600; margin: 20px 0 8px; }
.code-label    { font-size: 13px; color: #666; margin-bottom: 4px; }
.status-dot    { display: inline-block; width: 10px; height: 10px;
                 border-radius: 50%; margin-right: 6px; }
.dot-green  { background: #34a853; }
.dot-red    { background: #ea4335; }
.dot-yellow { background: #fbbc04; }
.elapsed    { font-size: 13px; color: #888; margin-top: 4px; }

/* Mobile friendliness */
@media (max-width: 768px) {
    .step-box { font-size: 13px; padding: 8px 12px; }
    .section-title { font-size: 16px; }
}
</style>
""", unsafe_allow_html=True)

# ── Page header (defined ONCE) ────────────────────────────────────────────────

st.title("Git Analyser 🚀")
st.caption("Multi-agent GitHub assistant — RAG + automated code changes")
st.caption("⚡ First request may take ~30 seconds due to free hosting")

# ── Session state defaults ────────────────────────────────────────────────────

DEFAULTS = {
    "thread_id":        None,
    "owner":            "",
    "repo":             "",
    "query":            "",
    "issue_number":     0,
    "completed_steps":  [],
    "waiting":          False,
    "finished":         False,
    "state":            None,
    "pipeline_ran":     False,
    "backend_ready":    False,
    "backend_status":   "unknown",  # "ok" | "error" | "unknown"
    "pipeline_start":   None,       # epoch time when pipeline started
}

for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ── Step metadata ─────────────────────────────────────────────────────────────

STEPS = {
    "git_fetcher":  ("Fetching repository data",  "Pulling commits, issues, PRs and file tree from GitHub"),
    "chunk":        ("Chunking source files",      "Splitting code into functions and classes"),
    "embedding":    ("Embedding chunks",           "Converting code into semantic vectors"),
    "vs":           ("Storing in vector DB",       "Writing embeddings to ChromaDB"),
    "planner":      ("Planning",                   "Deciding mode and steps for your query"),
    "file_fetcher": ("Fetching target file",       "Downloading the file to be modified"),
    "answer":       ("Generating answer",          "Searching codebase and composing response"),
    "code":         ("Writing code",               "Coder agent generating the change"),
    "review":       ("Reviewing code",             "Checking the change matches the plan"),
    "test":         ("Testing code",               "Syntax checking the generated file"),
    "human_review": ("Waiting for your review",   "Pipeline paused — your decision needed"),
    "pr":           ("Creating pull request",      "Pushing branch and opening PR on GitHub"),
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def render_steps(steps: list, running_node: str = None):
    for node in steps:
        label, desc = STEPS.get(node, (node, ""))
        st.markdown(
            f'<div class="step-box step-done">✓&nbsp;&nbsp;<b>{label}</b>'
            f'<span style="font-size:12px;color:#555;margin-left:8px">{desc}</span></div>',
            unsafe_allow_html=True,
        )
    if running_node:
        label, desc = STEPS.get(running_node, (running_node, ""))
        st.markdown(
            f'<div class="step-box step-running">⟳&nbsp;&nbsp;<b>{label}</b>'
            f'<span style="font-size:12px;color:#888;margin-left:8px">{desc}</span></div>',
            unsafe_allow_html=True,
        )


def typewriter(text: str, placeholder, delay: float = 0.018):
    """Write text into a Streamlit placeholder one character at a time."""
    displayed = ""
    for char in text:
        displayed += char
        placeholder.markdown(displayed)
        time.sleep(delay)


def elapsed_str(start: float) -> str:
    """Return a human-readable elapsed time string."""
    secs = int(time.time() - start)
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m {secs % 60}s"


def request_with_retry(method: str, url: str, retries: int = 5, **kwargs) -> requests.Response:
    """
    Retries on ReadTimeout and 502/503 (backend still warming up).
    Uses back-off for gateway errors. Raises last exception if all attempts fail.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            if method == "get":
                resp = requests.get(url, **kwargs)
            elif method == "post":
                resp = requests.post(url, **kwargs)
            # Retry on gateway errors — backend not fully up yet
            if resp.status_code in (502, 503):
                last_exc = requests.exceptions.HTTPError(response=resp)
                if attempt < retries:
                    wait = 5 * attempt  # back-off: 5s, 10s, 15s …
                    st.toast(f"Backend not ready ({resp.status_code}), retrying in {wait}s… ({attempt}/{retries})", icon="⏳")
                    time.sleep(wait)
                continue
            return resp
        except requests.exceptions.ReadTimeout as e:
            last_exc = e
            if attempt < retries:
                st.toast(f"Request timed out, retrying… ({attempt}/{retries})", icon="⏳")
                time.sleep(2)
        except requests.exceptions.ConnectionError:
            raise  # don't retry connection errors
    raise last_exc


def stream_and_collect(url: str) -> dict:
    """GET SSE endpoint — update step UI live, return final done payload."""
    completed  = list(st.session_state.completed_steps)
    steps_box  = st.empty()
    timer_box  = st.empty()
    final_data = {}

    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        current_node = None

        for raw_line in r.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:].strip())
            current_node, final_data, done = _handle_sse_event(
                event, completed, steps_box, current_node
            )
            if st.session_state.pipeline_start:
                timer_box.markdown(
                    f'<div class="elapsed">⏱ Elapsed: {elapsed_str(st.session_state.pipeline_start)}</div>',
                    unsafe_allow_html=True,
                )
            if done:
                timer_box.empty()
                break

    st.session_state.completed_steps = completed
    return final_data


def stream_and_collect_post(url: str, body: dict) -> dict:
    """POST SSE endpoint — update step UI live, return final done payload."""
    completed  = list(st.session_state.completed_steps)
    steps_box  = st.empty()
    timer_box  = st.empty()
    final_data = {}

    with requests.post(url, json=body, stream=True, timeout=600) as r:
        r.raise_for_status()
        current_node = None

        for raw_line in r.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:].strip())
            current_node, final_data, done = _handle_sse_event(
                event, completed, steps_box, current_node
            )
            if st.session_state.pipeline_start:
                timer_box.markdown(
                    f'<div class="elapsed">⏱ Elapsed: {elapsed_str(st.session_state.pipeline_start)}</div>',
                    unsafe_allow_html=True,
                )
            if done:
                timer_box.empty()
                break

    st.session_state.completed_steps = completed
    return final_data


def _handle_sse_event(event, completed, steps_box, current_node):
    """Process one SSE event. Returns (current_node, final_data, is_done)."""
    if event["type"] == "step":
        current_node = event["node"]
        with steps_box.container():
            render_steps(completed, running_node=current_node)
        return current_node, {}, False

    elif event["type"] == "done":
        if current_node and current_node not in completed:
            completed.append(current_node)
        with steps_box.container():
            render_steps(completed)
        return current_node, event, True

    elif event["type"] == "error":
        st.error(f"Pipeline error: {event['message']}")
        return current_node, {}, True

    return current_node, {}, False

# ── Backend Wake System (auto, no button needed) ──────────────────────────────

def ping_backend() -> bool:
    """Ping the health/root endpoint. Returns True only on a non-502/503 response."""
    try:
        r = requests.get(API, timeout=10)
        # 502/503 means the process is still booting — treat as not ready
        return r.status_code not in (502, 503) and r.status_code < 500
    except Exception:
        return False


def auto_wake_backend():
    """
    Auto-ping backend on page load. Retries every 5s for up to 300s (5 min).
    Render free-tier cold starts can take 2-4 minutes.
    """
    if st.session_state.backend_ready:
        return True

    status_box = st.empty()

    # Quick first check
    status_box.info("⏳ Checking backend status…")
    if ping_backend():
        st.session_state.backend_ready  = True
        st.session_state.backend_status = "ok"
        status_box.empty()
        return True

    # Backend cold — auto-retry with progress
    status_box.warning("🟡 Backend is waking up (free tier cold start — up to 3 min). Hang tight…")
    progress = st.progress(0)
    max_wait, interval = 300, 5
    elapsed = 0

    while elapsed < max_wait:
        time.sleep(interval)
        elapsed += interval
        progress.progress(min(elapsed / max_wait, 1.0))
        if ping_backend():
            st.session_state.backend_ready  = True
            st.session_state.backend_status = "ok"
            progress.empty()
            status_box.empty()
            st.toast("Backend is ready 🚀", icon="✅")
            return True

    # Timed out
    progress.empty()
    st.session_state.backend_status = "error"
    status_box.error(
        "❌ Backend didn't respond within 5 minutes. "
        "It may be down — try refreshing the page."
    )
    return False


if not auto_wake_backend():
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    # Backend status indicator
    status = st.session_state.backend_status
    if status == "ok":
        dot, label = '<span class="status-dot dot-green"></span>', "Backend online"
    elif status == "error":
        dot, label = '<span class="status-dot dot-red"></span>', "Backend offline"
    else:
        dot, label = '<span class="status-dot dot-yellow"></span>', "Backend unknown"

    st.markdown(f'{dot}<small>{label}</small>', unsafe_allow_html=True)
    st.divider()

    st.header("Repository")
    running = (
        st.session_state.pipeline_ran
        and not st.session_state.finished
        and not st.session_state.waiting
    )

    owner        = st.text_input("Owner",  value=st.session_state.owner,
                                  placeholder="e.g. 1Navneet23", disabled=running)
    repo         = st.text_input("Repo",   value=st.session_state.repo,
                                  placeholder="e.g. LegalMind",  disabled=running)
    issue_number = st.number_input(
        "Issue number (0 = auto-create)", min_value=0,
        value=st.session_state.issue_number, step=1, disabled=running,
    )
    st.divider()
    query   = st.text_area(
        "Query / Task", value=st.session_state.query, height=130,
        placeholder="e.g. add input validation to py_reader in backend/pdf_reader.py",
        disabled=running,
    )
    run_btn = st.button("▶ Run", type="primary", use_container_width=True,
                        disabled=st.session_state.pipeline_ran)

    if st.session_state.pipeline_ran:
        if st.button("🔄 New Run", use_container_width=True):
            # Clean reset — preserve backend state, reset everything else
            for k, v in DEFAULTS.items():
                if k not in ("backend_ready", "backend_status"):
                    st.session_state[k] = v
            st.rerun()

# ── Start pipeline ────────────────────────────────────────────────────────────

if run_btn and owner and repo and query:

    # Step 1 — verify repo (with up to 3 retries)
    with st.spinner("Verifying repository…"):
        try:
            v = request_with_retry(
                "get", f"{API}/verify",
                params={"owner": owner, "repo": repo},
                timeout=60,
            )
            v.raise_for_status()
            result = v.json()
            if not result["valid"]:
                st.error(f"Invalid repository — {result['message']}")
                st.stop()
            else:
                st.sidebar.success(result["message"])
        except requests.exceptions.ReadTimeout:
            st.error("Backend timed out after 3 attempts. Please wait a moment and try again.")
            st.stop()
        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to backend. Run: uvicorn backend.api:app --reload --port 8000")
            st.stop()
        except Exception as e:
            st.error(f"Unexpected error verifying repository: {e}")
            st.stop()

    # Persist inputs
    st.session_state.owner          = owner
    st.session_state.repo           = repo
    st.session_state.query          = query
    st.session_state.issue_number   = int(issue_number)
    st.session_state.completed_steps = []
    st.session_state.pipeline_ran   = True
    st.session_state.pipeline_start = time.time()

    # Step 2 — start pipeline run (with up to 3 retries)
    try:
        res = request_with_retry(
            "post", f"{API}/run",
            json={
                "owner": owner, "repo": repo,
                "query": query, "issue_number": int(issue_number),
            },
            timeout=60,
        )
        res.raise_for_status()
        st.session_state.thread_id = res.json()["thread_id"]
    except requests.exceptions.ReadTimeout:
        st.error("Backend timed out while starting the pipeline. Please try again.")
        st.stop()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to backend. Run: uvicorn backend.api:app --reload --port 8000")
        st.stop()
    except Exception as e:
        st.error(f"Unexpected error starting pipeline: {e}")
        st.stop()

    # Step 3 — stream events
    stream_url = (
        f"{API}/stream/{st.session_state.thread_id}"
        f"?owner={owner}&repo={repo}"
        f"&query={requests.utils.quote(query)}"
        f"&issue_number={int(issue_number)}"
    )
    final = stream_and_collect(stream_url)

    st.session_state.waiting  = final.get("waiting_for_human", False)
    st.session_state.finished = final.get("finished", False)
    st.session_state.state    = final.get("state")
    st.rerun()

# ── Show completed steps mid-pipeline ────────────────────────────────────────

if st.session_state.completed_steps and not st.session_state.waiting and not st.session_state.finished:
    render_steps(st.session_state.completed_steps)

# ── Human review panel ────────────────────────────────────────────────────────

if st.session_state.waiting and st.session_state.thread_id:
    render_steps(st.session_state.completed_steps)
    st.divider()
    st.markdown('<div class="section-title">👤 Your Review</div>', unsafe_allow_html=True)

    s = st.session_state.state or {}

    feedback    = s.get("feedback", "")
    retry_count = s.get("retry_count", 0)
    if feedback and retry_count > 1:
        with st.expander(f"Feedback given to coder on retry {retry_count}", expanded=False):
            st.info(feedback)

    col1, col2 = st.columns(2)

    with col1:
        plan = s.get("plan") or {}
        st.markdown("**Plan**")
        st.write(f"Mode: `{plan.get('mode')}`")
        st.write(f"Target file: `{plan.get('target_file')}`")
        for i, step in enumerate(plan.get("steps", []), 1):
            st.write(f"{i}. {step}")

    with col2:
        reviewer_out = s.get("reviewer") or {}
        tester_out   = s.get("tester")   or {}

        st.markdown("**Reviewer**")
        if reviewer_out.get("approved"):
            st.success("Approved ✅")
        else:
            for c in reviewer_out.get("comments", []):
                st.warning(c)

        st.markdown("**Tester**")
        if tester_out.get("passed"):
            st.success("Syntax OK ✅")
        else:
            st.error(tester_out.get("errors", "Failed"))

    coder_out = s.get("coder") or {}
    st.markdown("**Generated code**")
    st.code(coder_out.get("content", ""), language="python")
    st.caption(coder_out.get("explanation", ""))

    st.divider()
    note = st.text_area(
        "Feedback for coder (leave empty to abort if rejecting)",
        height=80,
        placeholder="e.g. you forgot to handle the case where the file is empty",
    )

    approve_col, reject_col = st.columns(2)

    with approve_col:
        if st.button("✅ Approve & raise PR", type="primary", use_container_width=True):
            st.session_state.pipeline_start = time.time()
            resume_url = f"{API}/resume/{st.session_state.thread_id}"
            final = stream_and_collect_post(resume_url, {"approved": True, "note": ""})
            st.session_state.waiting  = final.get("waiting_for_human", False)
            st.session_state.finished = final.get("finished", False)
            st.session_state.state    = final.get("state")
            st.rerun()

    with reject_col:
        if st.button("❌ Reject", use_container_width=True):
            st.session_state.pipeline_start = time.time()
            resume_url = f"{API}/resume/{st.session_state.thread_id}"
            final = stream_and_collect_post(resume_url, {"approved": False, "note": note or ""})
            st.session_state.waiting  = final.get("waiting_for_human", False)
            st.session_state.finished = final.get("finished", False)
            st.session_state.state    = final.get("state")
            st.rerun()

# ── Final result ──────────────────────────────────────────────────────────────

if st.session_state.finished and st.session_state.state:
    render_steps(st.session_state.completed_steps)

    if st.session_state.pipeline_start:
        st.markdown(
            f'<div class="elapsed">✅ Completed in {elapsed_str(st.session_state.pipeline_start)}</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    s = st.session_state.state

    if s.get("answer"):
        st.markdown('<div class="section-title">💡 Answer</div>', unsafe_allow_html=True)
        answer_placeholder = st.empty()
        typewriter(s["answer"], answer_placeholder)

    pr = s.get("pr_agent")
    if pr:
        if pr.get("success"):
            st.success("Pull request created successfully 🎉")
            st.markdown(f"[View PR on GitHub ↗]({pr.get('pr_url')})")
        else:
            st.error(f"PR failed: {pr.get('error')}")

    if not s.get("answer") and not s.get("pr_agent"):
        st.warning("Pipeline ended without creating a PR.")