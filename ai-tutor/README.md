# ai-tutor

The **agent**. A FastAPI service with a single `POST /chat` endpoint. It decides
*whether* a tool is needed, calls the tool server when it is, and asks the local
LLM to turn the result into an answer.

Serves on `http://127.0.0.1:8001`.

## Request

`multipart/form-data`:

| Field | Type | Required | Notes |
|---|---|---|---|
| `query` | text | yes | the user's question |
| `file` | file | no | a PDF; saved to `../uploaded_pdfs/` so the tool server can read it too |

Response: `{"answer": "..."}`.

## Files

| File | Responsibility |
|---|---|
| `main.py` | HTTP layer: validate input, persist the PDF, hand off to the agent. |
| `agent.py` | Orchestration: list tools -> LLM call -> (optional) tool call -> LLM call -> answer. |
| `mcp_client.py` | Talks to the tool server over MCP/SSE: `list_tools`, `call_tool`. |
| `llm_ollama.py` | Wraps `ChatOllama`; binds the tool catalogue when tools are supplied. |
| `prompt.py` | Builds the single prompt string (query + optional PDF path + optional tool result + instructions). |

## The loop (`agent.py`)

```
list_mcp_tools()                      # what can I do?
prompt = get_prompt(query, pdf_path)  # no tool result yet
resp = call_llm(prompt, tools)        # LLM call #1

if resp.tool_calls:                   # LLM asked for a tool
    call = resp.tool_calls[0]
    result = call_mcp_tool(call["name"], call["args"])
    prompt = get_prompt(query, pdf_path, result)
    resp = call_llm(prompt, tools)    # LLM call #2, now grounded

answer = resp.content
```

The agent is stateless; every request rebuilds everything. Only the first tool
call is handled (no multi-tool loop).

## Run

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8001
```

Needs the tool server on `:8000` and Ollama on `:11434` with the
`qwen2.5:7b-instruct` model pulled.
