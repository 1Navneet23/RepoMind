from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from agent.llms import answer_llm
from dotenv import load_dotenv
load_dotenv()
def answer(query,top_chunks):
    
    prompt=PromptTemplate.from_template("""You are a senior software engineer analyzing a GitHub repository.

    Use the following code context to answer the question.

    Code Context:
    {top_chunks}

    Question:
    {query}

    Rules:
    - Be concise and specific
    - Reference exact file names and functions
    - If the answer is not in the context, say "I don't know\""""
    )
    formatted_prompt = prompt.format(query=query,top_chunks=top_chunks)
    result=answer_llm.invoke(formatted_prompt)
    
    parser = StrOutputParser()
    result1 = parser.invoke(result) 
    return result1