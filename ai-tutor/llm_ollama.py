from typing import List, Dict, Any, Optional
from langchain_ollama import ChatOllama

MODEL_NAME = "qwen2.5:7b-instruct"

llm = ChatOllama(
    model=MODEL_NAME,
    base_url="http://localhost:11434",
    temperature=0,
)

def call_llm(
    input: str,
    tools: Optional[List[Dict[str, Any]]] = None,
):
    if tools:
        return llm.bind_tools(tools).invoke(input)

    return llm.invoke(input)
