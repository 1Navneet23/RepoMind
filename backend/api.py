"""
backend/api.py

Endpoints:
  POST /run                — start pipeline, returns thread_id immediately
  GET  /stream/{thread_id} — SSE stream of node completions
  GET  /state/{thread_id}  — full state snapshot
  POST /resume/{thread_id} — human approve / reject

Run:
  uvicorn backend.api:app --reload --port 8000
"""

import hashlib
import json
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from states.state import workflow

app = FastAPI(title="Git Analyser API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    owner:        str
    repo:         str
    query:        str
    issue_number: int = 0


class ResumeRequest(BaseModel):
    approved: bool
    note:     Optional[str] = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_thread_id(owner: str, repo: str, query: str) -> str:
    return hashlib.md5(f"{owner}-{repo}-{query}".encode()).hexdigest()[:12]


def _is_waiting(config: dict) -> bool:
    current = workflow.get_state(config)
    return bool(current.next and "human_review" in str(current.next))


def _is_finished(config: dict) -> bool:
    return not workflow.get_state(config).next


def _safe_state(config: dict) -> dict:
    s = workflow.get_state(config).values
    return {
        "plan":         s.get("plan"),
        "coder":        s.get("coder"),
        "reviewer":     s.get("reviewer"),
        "tester":       s.get("tester"),
        "answer":       s.get("answer"),
        "pr_agent":     s.get("pr_agent"),
        "mode":         s.get("mode"),
        "feedback":     s.get("feedback", ""),
        "retry_count":  s.get("retry_count", 0),
        "tester_retry": s.get("tester_retry", 0),
    }


def _make_initial_input(req: RunRequest) -> dict:
    return {
        "owner":          req.owner,
        "repo":           req.repo,
        "query":          req.query,
        "issue_number":   req.issue_number,
        "retry_count":    0,
        "tester_retry":   0,
        "feedback":       "",
        "file_content":   "",
        "target_file":    "",
        "human_approved": None,
        "human_note":     "",
    }


# ── SSE generator ─────────────────────────────────────────────────────────────

def _sse_event(data: dict) -> str:
    """Format a dict as a Server-Sent Event string."""
    return f"data: {json.dumps(data)}\n\n"


def _stream_pipeline(input_data, config: dict):
    """
    Generator that runs the workflow and yields SSE events:
      {type: "step",  node: "git_fetcher"}
      {type: "done",  waiting_for_human: bool, finished: bool}
      {type: "error", message: "..."}
    """
    try:
        for event in workflow.stream(input_data, config=config):
            for node_name in event:
                yield _sse_event({"type": "step", "node": node_name})

        yield _sse_event({
            "type":              "done",
            "waiting_for_human": _is_waiting(config),
            "finished":          _is_finished(config),
            "state":             _safe_state(config),
        })
    except Exception as e:
        yield _sse_event({"type": "error", "message": str(e)})


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/verify")
def verify_repo(owner: str, repo: str):
    """
    Quick check — does this owner/repo exist and is it accessible
    with the configured GitHub token?
    Returns {valid: bool, message: str}
    """
    import requests as http
    import os

    token = os.getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"Token {token}"} if token else {}

    try:
        r = http.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=headers,
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            return {
                "valid":    True,
                "message":  f"Found — {data.get('full_name')} ({data.get('visibility', 'unknown')} repo)",
                "stars":    data.get("stargazers_count", 0),
                "language": data.get("language", "unknown"),
            }
        elif r.status_code == 404:
            return {"valid": False, "message": "Repository not found. Check owner and repo name."}
        elif r.status_code == 401:
            return {"valid": False, "message": "GitHub token is invalid or expired."}
        elif r.status_code == 403:
            return {"valid": False, "message": "Access denied. Repository may be private."}
        else:
            return {"valid": False, "message": f"GitHub returned status {r.status_code}."}
    except Exception as e:
        return {"valid": False, "message": f"Could not reach GitHub: {e}"}


@app.post("/run")
def run_pipeline(req: RunRequest):
    """Start the pipeline — returns thread_id. Frontend then opens /stream."""
    thread_id = _make_thread_id(req.owner, req.repo, req.query)
    return {
        "thread_id":   thread_id,
        "initial_input": _make_initial_input(req),
    }


@app.get("/stream/{thread_id}")
def stream_pipeline(thread_id: str, owner: str, repo: str, query: str, issue_number: int = 0):
    """SSE endpoint — streams node completions as they happen."""
    config = {"configurable": {"thread_id": thread_id}}
    req    = RunRequest(owner=owner, repo=repo, query=query, issue_number=issue_number)

    return StreamingResponse(
        _stream_pipeline(_make_initial_input(req), config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/state/{thread_id}")
def get_state(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    try:
        return {
            "thread_id":         thread_id,
            "waiting_for_human": _is_waiting(config),
            "finished":          _is_finished(config),
            "state":             _safe_state(config),
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/resume/{thread_id}")
def resume_pipeline(thread_id: str, req: ResumeRequest):
    """Update human decision then stream the resumed pipeline via SSE."""
    config = {"configurable": {"thread_id": thread_id}}

    workflow.update_state(config, {
        "human_approved": req.approved,
        "human_note":     req.note or "",
    })

    return StreamingResponse(
        _stream_pipeline(None, config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )