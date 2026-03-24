from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from agent.llms import coder_llm, extractor_llm
from dotenv import load_dotenv
load_dotenv()


class CodeChange(BaseModel):
    filename: str = Field(description="which file to modify — must be the exact full path")
    content: str = Field(description="complete new file content")
    explanation: str = Field(description="what changed and why")


def coder(plan, file_content, target_file: str = "", feedback=None):
    parser = PydanticOutputParser(pydantic_object=CodeChange)
    feedback_section = f"Reviewer/tester feedback:\n{feedback}" if feedback else "No feedback provided."

    # Call 1 — think and write code with coder_llm
    thinking_prompt = PromptTemplate.from_template("""You are a senior software developer implementing code changes.

Plan:
{plan}

Target file path (use this EXACT string as filename — do not shorten):
{target_file}

File Content:
{file_content}

{feedback_section}

Instructions:
- The filename in your response must be exactly: {target_file}
- Only modify what the plan asks — changes must be minimal
- Do not touch anything not mentioned in the plan
- Match the existing code style exactly
- IMPORTANT: For multiline strings always use triple quotes: f\"\"\"...\"\"\"
- NEVER use f\"\" for multiline content — this causes SyntaxError
- If you don't know the answer, say so

Write the complete updated file content with all changes applied.
""")

    thinking = coder_llm.invoke(thinking_prompt.format(
        plan=plan,
        file_content=file_content,
        target_file=target_file,
        feedback_section=feedback_section,
    ))

    # Call 2 — extract JSON with extractor_llm
    extraction_prompt = PromptTemplate.from_template("""You are a JSON extraction engine.
Output ONLY valid JSON. No explanation. No markdown. No text before or after.
CRITICAL: The 'content' field must preserve ALL newlines as \\n in the JSON string.
Every single line of code must be separated by \\n.
A function definition like 'def foo():' must be followed by \\n then the indented body.
NEVER put two statements on the same line.


Analysis:
{thinking}

IMPORTANT: The filename field MUST be exactly: {target_file}

{format_instructions}
""")

    ans = extractor_llm.invoke(extraction_prompt.format(
        thinking=thinking.content,
        target_file=target_file,
        format_instructions=parser.get_format_instructions(),
    ))
    result = parser.invoke(ans)

    # Hard override — if LLM still shortened the path, correct it
    if target_file and result.filename != target_file:
        object.__setattr__(result, "filename", target_file)

    return result