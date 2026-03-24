# import logging
# from states.state import workflow

# # add this before workflow.invoke
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s — %(levelname)s — %(message)s"
# )

# result = workflow.invoke({
#     "owner":        "1Navneet23",
#     "repo":         "LegalMind",
#     "query":        "explain what this repo does",
#     "issue_number": 0,
#     "retry_count":  0,
#     "feedback":     "",
#     "file_content": "",
# })

# print(result["answer"])
import logging
from states.state import workflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s"
)

config = {"configurable": {"thread_id": "run-legalmind-001"}}

initial_input = {
    "owner":          "1Navneet23",
    "repo":           "LegalMind",
    "query":          "add error handling to explain_legal_question in backend/llm_explainer.py",
    "issue_number":   1,
    "retry_count":    0,
    "tester_retry":   0,
    "feedback":       "",
    "file_content":   "",
    "target_file":    "",
    "human_approved": None,
    "human_note":     "",
}

# ── Phase 1: run until human_review interrupt ─────────────────────────────────
print("Starting pipeline...\n")
for event in workflow.stream(initial_input, config=config):
    for node_name in event:
        print(f"  {node_name}")


def show_state():
    """Print the current pipeline output for human to review."""
    s = workflow.get_state(config).values
    print("\n=== PLAN ===")
    print(s.get("plan"))
    print("\n=== CODER OUTPUT ===")
    print(s.get("coder"))
    print("\n=== REVIEWER ===")
    print(s.get("reviewer"))
    print("\n=== TESTER ===")
    print(s.get("tester"))


# ── Human decision loop — runs as many times as human wants ───────────────────
while True:
    show_state()

    decision = input("\nApprove this PR? [y/n]: ").strip().lower()
    approved = decision == "y"

    note = ""
    if not approved:
        note = input("What needs fixing? (leave empty to abort): ").strip()

    workflow.update_state(
        config,
        {
            "human_approved": approved,
            "human_note":     note,
        },
    )

    if approved:
        print("\nApproved — raising PR...\n")
    elif note:
        print(f"\nFeedback sent to coder: '{note}'\nRe-running...\n")
    else:
        print("\nNo note given — aborting.\n")

    # resume graph from checkpoint
    for event in workflow.stream(None, config=config):
        for node_name in event:
            print(f"  {node_name}")

    # check if graph has fully ended
    current = workflow.get_state(config)

    # graph ended (no more next nodes) → break out of loop
    if not current.next:
        break

    # graph paused again at human_review → loop back and ask again
    if "__interrupt__" not in str(current.next) and "human_review" not in str(current.next):
        break

# ── Final output ──────────────────────────────────────────────────────────────
final = workflow.get_state(config).values
pr = final.get("pr_agent")

if pr and pr.get("success"):
    print("\n=== PR CREATED ===")
    print(pr.get("pr_url"))
elif pr and not pr.get("success"):
    print("\n=== PR FAILED ===")
    print(pr.get("error"))
else:
    print("\nPipeline ended — no PR created.")