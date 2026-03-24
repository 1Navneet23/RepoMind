"""
llms.py — Central LLM configuration for all agents.

Each agent has its own LLM instance tuned for its specific job:

  planner   — needs strong reasoning to decide mode + extract file path
  coder     — needs precise code generation, low temperature to avoid syntax errors
  reviewer  — needs strict analytical thinking, low temperature for consistent verdicts
  extractor — used for the JSON extraction call in every two-phase agent
              (fast, low temp, just reformatting not reasoning)
  answer    — RAG answers, slightly more creative since it's explaining code

To switch a model globally, change it here — all agents update automatically.
"""

from langchain_groq import ChatGroq
from dotenv import load_dotenv
load_dotenv()

# ── Planner ───────────────────────────────────────────────────────────────────
# Needs to reason about intent, classify mode, extract file paths.
# Versatile model at moderate temp — needs some creativity for edge cases.
planner_llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,
)


# Coder — best available model specifically for code generation
# kimi-k2 is optimised for agentic coding tasks (SWE-bench, LiveCodeBench)
# NOTE: preview model — if it causes issues, fall back to llama-3.3-70b-versatile
coder_llm = ChatGroq(
    model="moonshotai/kimi-k2-instruct",
    temperature=0.1,
)

# ── Reviewer ──────────────────────────────────────────────────────────────────
# Strict pass/fail decisions. Low temperature = consistent, not creative.
reviewer_llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.1,
)

# ── Extractor ─────────────────────────────────────────────────────────────────
# Second call in every two-phase agent — just reformats thinking into JSON.
# Uses the fastest available model since this is a simple reformatting task.
# gemma2-9b-it is fast and reliable for pure extraction.
extractor_llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.0,
)

# ── Answer (RAG) ──────────────────────────────────────────────────────────────
# Explains code to the user. Slightly higher temp for more natural language.
answer_llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.5,
)