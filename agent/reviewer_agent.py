from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import List
from agent.llms import reviewer_llm, extractor_llm
from dotenv import load_dotenv
load_dotenv()


class Review(BaseModel):
    approved: bool = Field(description="is the code accepted or rejected")
    comments: List[str] = Field(description="specific issues if the code is rejected")


def reviewer(plan, original_code, generated_code):
    parser = PydanticOutputParser(pydantic_object=Review)

    # Call 1 — review carefully with reviewer_llm
    thinking_prompt = PromptTemplate.from_template("""You are a strict code reviewer in a multi-agent software system.
Your job is to evaluate whether the generated code correctly implements the given plan.

Original Code:
{original_code}

Plan (what changes were requested):
{plan}

Generated Code (what the coder produced):
{generated_code}

Review Criteria:
- Does the generated code fully implement everything in the plan?
- Are the changes minimal — only what the plan asked for, nothing extra?
- Does the generated code match the original code style (indentation, naming, patterns)?
- Are there any bugs, logic errors, or broken functionality introduced?
- Does it preserve all existing behavior that was not meant to change?

Instructions:
- Think through each criteria carefully
- Give your verdict — approved or rejected
- If rejected, list every specific issue precisely — reference function names and line numbers where possible
- Do not approve code that changes more than what the plan requires
""")

    thinking = reviewer_llm.invoke(thinking_prompt.format(
        plan=plan,
        original_code=original_code,
        generated_code=generated_code,
    ))

    # Call 2 — extract JSON with extractor_llm
    extraction_prompt = PromptTemplate.from_template("""You are a JSON extraction engine.
Extract the review verdict from the analysis below into the exact JSON format specified.
Output ONLY valid JSON. No explanation. No markdown. No text before or after.

Review Analysis:
{thinking}

{format_instructions}
""")

    ans = extractor_llm.invoke(extraction_prompt.format(
        thinking=thinking.content,
        format_instructions=parser.get_format_instructions(),
    ))
    return parser.invoke(ans)