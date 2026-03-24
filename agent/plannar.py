from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from agent.llms import planner_llm, extractor_llm
from dotenv import load_dotenv
load_dotenv()


class Plan(BaseModel):
    mode: str = Field(description="rag or dev")
    steps: list[str] = Field(description="Ordered list of steps")
    resoning: str = Field(description="why did planner choose these steps")
    target_file: str = Field(description="file path to modify in dev mode, empty string if rag mode")


def plannar_agent(query):
    parser = PydanticOutputParser(pydantic_object=Plan)

    # Call 1 — think freely with planner_llm
    thinking_prompt = PromptTemplate.from_template("""You are an intelligent orchestrator for a multi-agent software system.
Your job is to analyze the incoming request and create an execution plan.

Request:
{query}

Available Modes:
    - rag: Use this when the user wants to UNDERSTAND a repository
    Examples: "explain this code", "where is auth implemented", "summarize this repo"

    - dev: Use this when the user wants to CHANGE a repository
    Examples: "fix this bug", "add this feature", "resolve this issue"

Your job:
1. Decide which mode fits the request — rag or dev
2. Break the task into clear ordered steps
3. Explain your reasoning in detail
4. If mode is dev — extract the exact file path from the request that needs to be modified
   Example: "add error handling to explain_legal_question in backend/llm_explainer.py" -> target_file = "backend/llm_explainer.py"
   If no file is mentioned explicitly, make your best guess based on the request context
   If mode is rag — target_file should be empty string
""")

    thinking = planner_llm.invoke(thinking_prompt.format(query=query))

    # Call 2 — extract JSON with extractor_llm (fast, no reasoning needed)
    extraction_prompt = PromptTemplate.from_template("""You are a JSON extraction engine.
Extract the execution plan from the analysis below into the exact JSON format specified.
Output ONLY valid JSON. No explanation. No markdown. No text before or after.

Plan Analysis:
{thinking}

{format_instructions}
""")

    ans = extractor_llm.invoke(extraction_prompt.format(
        thinking=thinking.content,
        format_instructions=parser.get_format_instructions(),
    ))
    return parser.invoke(ans)