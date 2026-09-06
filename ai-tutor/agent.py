from mcp_client import list_mcp_tools, call_mcp_tool
from llm_ollama import call_llm
from langchain_core.messages import AIMessage
from prompt import get_prompt

class ChatAgent:

    def needs_tool_execution(self, llm_response: AIMessage) -> bool:
        return bool(llm_response.tool_calls)

    async def run(self, query: str, pdf_path: str) -> str:

        tools_response = await list_mcp_tools()

        tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in tools_response.tools
        ]

        custom_prompt = get_prompt(query, pdf_path)

        llm_response = call_llm(custom_prompt, tools)

        if self.needs_tool_execution(llm_response):

            tool_call = llm_response.tool_calls[0]

            tool_result = await call_mcp_tool(
                tool_name=tool_call["name"],
                arguments=tool_call["args"]
            )

            custom_prompt = get_prompt(query, pdf_path, tool_result)

            llm_response = call_llm(custom_prompt, tools)

            final_answer = llm_response.content
        else:
            final_answer = llm_response.content

        return final_answer
