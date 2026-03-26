from langgraph.graph import StateGraph, START, END

 
from typing import TypedDict, Optional

from agent.answer_agent import answer
from agent.coder_agent import coder
from agent.plannar import plannar_agent
from agent.pr_agent import prs
from agent.reviewer_agent import reviewer
from agent.tester_agent import tester

from data.chunk import chunk_repo
from data.git_fetcher import (
    get_file_tree,
    get_file_content,
    get_meta_data,
    get_issues,
    get_prs,
    get_all_commits,
    get_contributor,
)
from rag.embedding import embed_chunks
from rag.vectorstore import store_embeddings, search_embeddings
 
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
import os

# On Railway the persistent volume is mounted at /data.
# Locally everything stays in the project folder as before.
_DATA_DIR = "/data" if os.path.isdir("/data") else "."

_CHROMA_PATH   = os.path.join(_DATA_DIR, "chroma_db")
_SQLITE_PATH   = os.path.join(_DATA_DIR, "checkpoints.db")

conn = sqlite3.connect(_SQLITE_PATH, check_same_thread=False)
checkpointer = SqliteSaver(conn)

class agent_state(TypedDict):
    # inputs
    repo: str
    owner: str
    query: str
    session_id: str
    issue_number: int
    # pipeline data
    meta_data: dict
    commits: list
    prs: list
    issues: list
    contributors: list
    files: list
    all_chunks: list
    file_content: str
    target_file: str
    # rag
    top_chunks: str
    # agent outputs
    plan: dict
    answer: str
    coder: dict
    reviewer: dict
    feedback: str
    tester: dict
    pr_agent: dict
    mode: str
    retry_count: int    # reviewer retries — capped at 3
    tester_retry: int   # tester retries   — capped at 2
    # human-in-the-loop
    human_approved: Optional[bool]
    human_note: Optional[str]


# ── Node wrappers ─────────────────────────────────────────────────────────────

def run_git_fetcher(state: agent_state) -> dict:
    owner, repo = state["owner"], state["repo"]
    return {
        "session_id":   f"{owner}_{repo}",
        "meta_data":    get_meta_data(owner, repo),
        "issues":       get_issues(owner, repo),
        "commits":      get_all_commits(owner, repo),
        "prs":          get_prs(owner, repo),
        "contributors": get_contributor(owner, repo),
        "files":        get_file_tree(owner, repo),
    }


def run_chunks(state: agent_state) -> dict:
    return {"all_chunks": chunk_repo(state["owner"], state["repo"])}


def run_embedding(state: agent_state) -> dict:
    return {"all_chunks": embed_chunks(state["all_chunks"])}

def run_vectorstore(state: agent_state) -> dict:
    import chromadb
    client = chromadb.PersistentClient(path=_CHROMA_PATH)
    collection = client.get_or_create_collection(f"session_{state['session_id']}")

    if collection.count() > 0:
        print(f"  Skipping ingestion — already have {collection.count()} chunks")
        return {}

    store_embeddings(state["all_chunks"], state["session_id"])
    return {}
 


def run_planner(state: agent_state) -> dict:
    result = plannar_agent(state["query"])
    return {
        "plan": {
            "mode":        result.mode,
            "steps":       result.steps,
            "reasoning":   result.resoning,
            "target_file": result.target_file,
        },
        "mode":        result.mode,
        "target_file": result.target_file,
    }


def run_file_fetcher(state: agent_state) -> dict:
    file_path = state.get("target_file", "")
    if not file_path:
        return {"file_content": ""}
    return {"file_content": get_file_content(state["owner"], state["repo"], file_path) or ""}


def run_answer(state: agent_state) -> dict:
    top_chunks = search_embeddings(state["query"], state["session_id"], top_k=8)
    return {"answer": answer(state["query"], top_chunks), "top_chunks": top_chunks}


def run_coder(state: agent_state) -> dict:
    result = coder(
        plan=state["plan"],
        file_content=state.get("file_content", ""),
        target_file=state.get("target_file", ""),
        feedback=state.get("feedback"),
    )
    return {
        "coder": {
            "filename":    result.filename,
            "content":     result.content,
            "explanation": result.explanation,
        },
        "retry_count": state.get("retry_count", 0) + 1,
    }


def run_reviewer(state: agent_state) -> dict:
    result = reviewer(
        plan=state["plan"],
        original_code=state.get("file_content", ""),
        generated_code=state["coder"]["content"],
    )
    return {
        "reviewer": {"approved": result.approved, "comments": result.comments},
        "feedback": "\n".join(result.comments) if not result.approved else "",
    }


def run_tester(state: agent_state) -> dict:
    result = tester(
        generated_code=state["coder"]["content"],
        filename=state["coder"]["filename"],
    )
    feedback = state.get("feedback", "")
    if not result["passed"]:
        feedback = f"Tester caught a syntax error -- fix this before anything else:\n{result['errors']}"
    return {
        "tester": result,
        "feedback": feedback,
        "tester_retry": state.get("tester_retry", 0) + 1,
    }


def run_human_review(state: agent_state) -> dict:
    """
    Interrupt node — graph pauses here waiting for human input.

    APPROVAL  (human_approved=True)  → nothing to set, routes to pr → END
    REJECTION (human_approved=False)
        + note given   → format note as coder feedback, loop back to coder
        + no note      → human gave up, routes to END
    """
    if state.get("human_approved") is False:
        note = state.get("human_note", "").strip()
        if note:
            # human gave specific feedback — send to coder, reset human_approved
            # so the next interrupt works correctly
            return {
                "feedback":       f"Human reviewer rejected. Fix this:\n{note}",
                "human_approved": None,   # reset so next interrupt is fresh
                "human_note":     "",     # clear note so it isn't re-used
            }
    return {}


def run_pr(state: agent_state) -> dict:
    coder_out = state["coder"]
    result = prs(
        owner=state["owner"],
        repo_name=state["repo"],
        filename=coder_out["filename"],
        content=coder_out["content"],
        plan=state["plan"],
        issue_number=state["issue_number"],
    )
    return {"pr_agent": result}


# ── Routing ───────────────────────────────────────────────────────────────────

def route_by_mode(state: agent_state) -> str:
    return "answer_node" if state["plan"]["mode"] == "rag" else "file_fetcher"


def route_after_review(state: agent_state) -> str:
    if state["reviewer"]["approved"] or state.get("retry_count", 0) >= 3:
        return "test"
    return "code"


def route_after_test(state: agent_state) -> str:
    """
    passed              → human_review
    failed + retries left   → code (coder gets syntax error as feedback)
    failed + retries gone   → abort (automated loop is broken, give up cleanly)
    """
    if state["tester"]["passed"]:
        return "human_review"
    if state.get("tester_retry", 0) >= 2:
        return "abort"        # automated retries exhausted — abort, do not bother human
    return "code"


def route_after_human(state: agent_state) -> str:
    """
    approved                        → pr → END
    rejected + note given           → code (human note as feedback, no retry cap)
    rejected + no note              → abort (human gave up with nothing to say)
    """
    if state.get("human_approved"):
        return "pr"

    note = state.get("human_note", "").strip()
    if note:
        return "code"   # human gave feedback — loop back, no cap
    return "abort"      # human said no but gave nothing to work with — end


# ── Graph ─────────────────────────────────────────────────────────────────────

 
 
graph = StateGraph(agent_state)

graph.add_node("git_fetcher",  run_git_fetcher)
graph.add_node("chunk",        run_chunks)
graph.add_node("embedding",    run_embedding)
graph.add_node("vs",           run_vectorstore)
graph.add_node("planner",      run_planner)
graph.add_node("file_fetcher", run_file_fetcher)
graph.add_node("answer_node",       run_answer)
graph.add_node("code",         run_coder)
graph.add_node("review",       run_reviewer)
graph.add_node("test",         run_tester)
graph.add_node("human_review", run_human_review)
graph.add_node("pr",           run_pr)

graph.add_edge(START,         "git_fetcher")
graph.add_edge("git_fetcher", "chunk")
graph.add_edge("chunk",       "embedding")
graph.add_edge("embedding",   "vs")
graph.add_edge("vs",          "planner")

graph.add_conditional_edges(
    "planner",
    route_by_mode,
    {"answer": "answer_node", "file_fetcher": "file_fetcher"}
)

graph.add_edge("file_fetcher", "code")
graph.add_edge("code",         "review")

graph.add_conditional_edges(
    "review",
    route_after_review,
    {"test": "test", "code": "code"}
)

graph.add_conditional_edges(
    "test",
    route_after_test,
    {"human_review": "human_review", "code": "code", "abort": END}
)

graph.add_conditional_edges(
    "human_review",
    route_after_human,
    {"pr": "pr", "code": "code", "abort": END}
)

graph.add_edge("answer_node", END)
graph.add_edge("pr",     END)   # pr → END, always final

workflow = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_review"],
)