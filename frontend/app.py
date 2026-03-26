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

 
import os

def check_password():
    if st.session_state.get("authenticated"):
        return True
    st.title("Git Analyser")
    pwd = st.text_input("Password", type="password")
    if st.button("Enter"):
        if pwd == st.secrets["APP_PASSWORD"]
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Wrong password")
    return False

if not check_password():
    st.stop()

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
.step-done  { background: #e6f4ea; color: #1e6e35; border-left: 4px solid #34a853; }
.step-running { background: #fff8e1; color: #7a5c00; border-left: 4px solid #fbbc04;
                animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.6} }
.section-title { font-size: 18px; font-weight: 600; margin: 20px 0 8px; }
.code-label    { font-size: 13px; color: #666; margin-bottom: 4px; }
</style>
""", unsafe_allow_html=True)

st.title("Git Analyser")
st.caption("Multi-agent GitHub assistant — RAG + automated code changes")

# ── Session state defaults ────────────────────────────────────────────────────

for key, val in {
    "thread_id":       None,
    "owner":           "",
    "repo":            "",
    "query":           "",
    "issue_number":    0,
    "completed_steps": [],   # list of node names completed so far
    "waiting":         False,
    "finished":        False,
    "state":           None,
    "pipeline_ran":    False,
}.items():
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


def stream_and_collect(url: str) -> dict:
    """
    GET SSE endpoint — update step UI live, return final done payload.
    """
    completed  = list(st.session_state.completed_steps)
    steps_box  = st.empty()
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
            if done:
                break

    st.session_state.completed_steps = completed
    return final_data


def stream_and_collect_post(url: str, body: dict) -> dict:
    """
    POST SSE endpoint — update step UI live, return final done payload.
    """
    completed  = list(st.session_state.completed_steps)
    steps_box  = st.empty()
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
            if done:
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


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Repository")
    running = st.session_state.pipeline_ran and not st.session_state.finished and not st.session_state.waiting
    owner        = st.text_input("Owner",        value=st.session_state.owner,        placeholder="e.g. 1Navneet23",  disabled=running)
    repo         = st.text_input("Repo",         value=st.session_state.repo,         placeholder="e.g. LegalMind",   disabled=running)
    issue_number = st.number_input("Issue number (0 = auto-create)", min_value=0,
                                   value=st.session_state.issue_number, step=1,       disabled=running)
    st.divider()
    query   = st.text_area("Query / Task", value=st.session_state.query, height=130,
                            placeholder="e.g. add input validation to py_reader in backend/pdf_reader.py",
                            disabled=running)
    run_btn = st.button("Run", type="primary", use_container_width=True,
                        disabled=st.session_state.pipeline_ran)

    if st.session_state.pipeline_ran:
        if st.button("New run", use_container_width=True):
            for key in ["thread_id", "completed_steps", "waiting", "finished", "state", "pipeline_ran"]:
                st.session_state[key] = [] if key == "completed_steps" else (False if key != "thread_id" else None)
            st.rerun()

# ── Start pipeline ────────────────────────────────────────────────────────────

if run_btn and owner and repo and query:
    # Verify repo exists before starting the pipeline
    try:
        v = requests.get(f"{API}/verify", params={"owner": owner, "repo": repo}, timeout=10)
        v.raise_for_status()
        result = v.json()
        if not result["valid"]:
            st.error(f"Invalid repository — {result['message']}")
            st.stop()
        else:
            st.sidebar.success(result["message"])
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to backend. Run: uvicorn backend.api:app --reload --port 8000")
        st.stop()

    st.session_state.owner        = owner
    st.session_state.repo         = repo
    st.session_state.query        = query
    st.session_state.issue_number = int(issue_number)
    st.session_state.completed_steps = []
    st.session_state.pipeline_ran = True

    try:
        res = requests.post(f"{API}/run", json={
            "owner": owner, "repo": repo,
            "query": query, "issue_number": int(issue_number),
        }, timeout=10)
        res.raise_for_status()
        data = res.json()
        st.session_state.thread_id = data["thread_id"]
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to backend. Run: uvicorn backend.api:app --reload --port 8000")
        st.stop()

    stream_url = (
        f"{API}/stream/{st.session_state.thread_id}"
        f"?owner={owner}&repo={repo}&query={requests.utils.quote(query)}&issue_number={int(issue_number)}"
    )
    final = stream_and_collect(stream_url)

    st.session_state.waiting  = final.get("waiting_for_human", False)
    st.session_state.finished = final.get("finished", False)
    st.session_state.state    = final.get("state")
    st.rerun()

# ── Show completed steps (after rerun) ────────────────────────────────────────

if st.session_state.completed_steps and not st.session_state.waiting and not st.session_state.finished:
    render_steps(st.session_state.completed_steps)

# ── Human review panel ────────────────────────────────────────────────────────

if st.session_state.waiting and st.session_state.thread_id:
    render_steps(st.session_state.completed_steps)
    st.divider()
    st.markdown('<div class="section-title">Your review</div>', unsafe_allow_html=True)

    s = st.session_state.state or {}

    # Show what the coder was told if this is a retry
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
            st.success("Approved")
        else:
            for c in reviewer_out.get("comments", []):
                st.warning(c)

        st.markdown("**Tester**")
        if tester_out.get("passed"):
            st.success("Syntax OK")
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
        if st.button("Approve & raise PR", type="primary", use_container_width=True):
            resume_url = f"{API}/resume/{st.session_state.thread_id}"
            final = stream_and_collect_post(resume_url, {"approved": True, "note": ""})
            st.session_state.waiting  = final.get("waiting_for_human", False)
            st.session_state.finished = final.get("finished", False)
            st.session_state.state    = final.get("state")
            st.rerun()

    with reject_col:
        if st.button("Reject", use_container_width=True):
            resume_url = f"{API}/resume/{st.session_state.thread_id}"
            final = stream_and_collect_post(resume_url, {"approved": False, "note": note or ""})
            st.session_state.waiting  = final.get("waiting_for_human", False)
            st.session_state.finished = final.get("finished", False)
            st.session_state.state    = final.get("state")
            st.rerun()

# ── Final result ──────────────────────────────────────────────────────────────

if st.session_state.finished and st.session_state.state:
    render_steps(st.session_state.completed_steps)
    st.divider()
    s = st.session_state.state

    if s.get("answer"):
        st.markdown('<div class="section-title">Answer</div>', unsafe_allow_html=True)
        answer_placeholder = st.empty()
        typewriter(s["answer"], answer_placeholder)

    pr = s.get("pr_agent")
    if pr:
        if pr.get("success"):
            st.success("Pull request created successfully")
            st.markdown(f"[View PR on GitHub]({pr.get('pr_url')})")
        else:
            st.error(f"PR failed: {pr.get('error')}")

    if not s.get("answer") and not s.get("pr_agent"):
        st.warning("Pipeline ended without creating a PR.")