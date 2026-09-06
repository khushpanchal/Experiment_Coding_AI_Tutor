# Experiment: Coding AI Tutor

A small, deliberately-minimal **AI agent** built from parts you can see through:

- a **FastAPI agent** (`ai-tutor/`) that owns the conversation and the control flow,
- a **local LLM** via [Ollama](https://ollama.com) (`qwen2.5:7b-instruct`) as the reasoning engine,
- an **MCP tool server** (`mcp-server-ai-tutor/`) that does the things the model cannot: hit the internet, and remember documents,
- **Qdrant** as the vector database behind a tiny RAG pipeline.

You `POST` a question (and optionally a PDF) to the agent. It asks the LLM what
to do, calls a tool if needed, and asks the LLM again to phrase the final answer.

This repo is a personal experiment for understanding the moving parts — not a
production system.

---

## The one idea to hold onto

An LLM is just files on disk (architecture + weights + a token table). It is good
at exactly one thing: reading text and generating text. **It cannot make a
network call, run code, or "use a tool."**

What actually happens when people say "the model used a tool":

1. Your code hands the model: the question **+** a JSON list of available tools (name + description + parameter schema).
2. The model generates a structured suggestion: *"call `get_crypto_price` with `{coin: "bitcoin", currency: "usd"}`"*. Just text.
3. **Your code** (the agent) makes the real call, gets a result.
4. **Your code** builds a new prompt: question **+** tool result **+** instructions, and hands it back.
5. The model reads that and generates the human answer.

The model decides; the agent acts. That round-trip is the whole program.

---

## Architecture

```
   POST /chat (multipart: query + optional PDF)
                     |
                     v
        +--------------------------------+            +------------------------+
        |  ai-tutor        (port 8001)   |  local API |  Ollama    (port 11434)|
        |  FastAPI + LangChain           | <--------> |  qwen2.5:7b-instruct    |
        |  main -> agent -> llm_ollama   |            |  (reasoning engine)     |
        +---------------+----------------+            +------------------------+
                        | MCP over SSE
                        v
        +--------------------------------+            +------------------------+
        |  mcp-server-ai-tutor (8000)    | ---------> |  CoinGecko API (web)   |
        |  FastMCP, 2 tools:             |            +------------------------+
        |   - get_crypto_price          |            +------------------------+
        |   - ingest_and_query_pdf ------+ ---------> |  Qdrant    (port 6333) |
        |     (read -> chunk -> embed    |   local    |  vector database       |
        |      -> store -> retrieve)     |            +------------------------+
        +---------------+----------------+
                        | reads PDFs from
                        v
                 uploaded_pdfs/   (shared: both services reach it)
```

### Request flows

| Question | Path |
|---|---|
| `"What is reflection?"` | agent → LLM → *"answer directly"* → done. No tool, no DB. |
| `"Price of bitcoin in usd?"` | agent → LLM → *"call `get_crypto_price`"* → MCP → CoinGecko → result → LLM → answer. |
| `"Summarise chapter 1"` + PDF | agent saves PDF → LLM → *"call `ingest_and_query_pdf`"* → MCP: read → chunk → embed → upsert to Qdrant → nearest-2 chunks → result → LLM → grounded answer. |

---

## Repository layout

```
Experiment_Coding_AI_Tutor/
├── ai-tutor/                 FastAPI agent (port 8001)
│   ├── main.py               POST /chat: validate, save PDF, delegate
│   ├── agent.py              the orchestration loop
│   ├── mcp_client.py         MCP/SSE client (list_tools, call_tool)
│   ├── llm_ollama.py         ChatOllama wrapper + bind_tools
│   ├── prompt.py             single prompt builder
│   └── requirements.txt
├── mcp-server-ai-tutor/      MCP tool server (port 8000)
│   ├── main.py               get_crypto_price + ingest_and_query_pdf
│   └── requirements.txt
├── uploaded_pdfs/            shared upload dir (contents gitignored)
└── README.md
```

---

## Prerequisites

Tested on macOS (Apple Silicon, 24 GB RAM) with [Homebrew](https://brew.sh).

| Tool | Why | Install |
|---|---|---|
| Python 3.12 | the system Python is too old for these libs | `brew install python@3.12` |
| Ollama | runs the local LLM | `brew install ollama` |
| A container engine | runs Qdrant | `brew install colima docker` (or Docker Desktop) |

```bash
brew install python@3.12 ollama colima docker
```

---

## Setup

### 1. LLM

```bash
brew services start ollama              # background server on :11434
ollama pull qwen2.5:7b-instruct         # ~4.7 GB, one time
```

`qwen2.5:7b-instruct` is used because it was fine-tuned for tool-calling: it
reliably emits tool-call JSON instead of prose. `llm_ollama.py` points at
`http://localhost:11434` with `temperature=0`.

### 2. Vector database (Qdrant in a container)

```bash
colima start --cpu 4 --memory 4        # starts the Docker engine (Linux VM)
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_storage:/qdrant/storage \
  --restart unless-stopped \
  qdrant/qdrant
```

- `-p 6333:6333` REST + dashboard (`http://localhost:6333/dashboard`), `6334` gRPC.
- `-v qdrant_storage:/qdrant/storage` a named volume so stored vectors survive `docker rm`. (A bind mount like `-v ~/qdrant_storage:/qdrant/storage` works too and keeps the files visible on the host.)
- `--restart unless-stopped` comes back after a reboot.

Check: `curl -s localhost:6333/collections` → `{"result":{"collections":[]}, ...}`.

Docker Desktop works identically (`docker run ...` is the same) if you prefer it
over Colima.

### 3. Python environments (one venv per service)

```bash
# tool server
cd mcp-server-ai-tutor
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
deactivate

# agent
cd ../ai-tutor
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
deactivate
```

The MCP server's first startup downloads the `all-MiniLM-L6-v2` embedding model
(~90 MB) from Hugging Face and caches it.

---

## Run

Three long-running processes (plus Ollama and Qdrant, already up):

```bash
# terminal 1 — tool server (start this first; the agent calls it)
cd mcp-server-ai-tutor && source venv/bin/activate
python main.py                         # http://127.0.0.1:8000/sse

# terminal 2 — agent
cd ai-tutor && source venv/bin/activate
uvicorn main:app --port 8001           # http://127.0.0.1:8001
```

On startup the tool server connects to Qdrant and creates the `pdf_chunks`
collection if missing.

---

## Test

```bash
# 1. plain question — answered directly, no tool
curl -s -X POST http://127.0.0.1:8001/chat \
  -F "query=What is reflection in programming? One sentence."

# 2. crypto — triggers get_crypto_price -> CoinGecko
curl -s -X POST http://127.0.0.1:8001/chat \
  -F "query=What is the price of bitcoin in usd?"

# 3. PDF — triggers the full RAG pipeline
curl -s -X POST http://127.0.0.1:8001/chat \
  -F "query=Summarise the key points of this document" \
  -F "file=@/path/to/some.pdf;type=application/pdf"
```

Each returns `{"answer": "..."}`. Watch the tool server's log for
`ListToolsRequest` / `CallToolRequest` and the Qdrant `PUT .../points` /
`POST .../points/query` lines.

---

## How it works

### The agent loop (`ai-tutor/agent.py`)

```python
tools_response = await list_mcp_tools()                 # discover tools
tools = [ {"type": "function", "function": {...}} ... ]  # -> LLM-friendly JSON

custom_prompt = get_prompt(query, pdf_path)             # no tool result yet
llm_response  = call_llm(custom_prompt, tools)          # LLM call #1

if llm_response.tool_calls:                             # model wants a tool
    tool_call   = llm_response.tool_calls[0]            # first tool only
    tool_result = await call_mcp_tool(tool_call["name"], tool_call["args"])
    custom_prompt = get_prompt(query, pdf_path, tool_result)
    llm_response  = call_llm(custom_prompt, tools)      # LLM call #2 (grounded)

return llm_response.content
```

Stateless: each request rebuilds everything. `tool_calls[0]` only — no
multi-tool / looping logic (that would be a `for` loop here, or LangGraph).

### The RAG pipeline (`mcp-server-ai-tutor/main.py`, `ingest_and_query_pdf`)

| Stage | Code | Purpose |
|---|---|---|
| Read | `PdfReader(pdf_path)` page by page | pull raw text (basic extractor; no OCR/tables) |
| Chunk | `chunk_text(text, 500, 50)` | 500-word windows, 50-word overlap so a sentence on a boundary survives whole in one chunk |
| Embed | `embedding_model.encode(chunks)` | each chunk → a 384-dim vector (meaning → geometry) |
| Store | `qdrant.upsert(PointStruct(id, vector, payload={"text": chunk}))` | vector for search, `payload.text` to hand back to the LLM |
| Retrieve | `qdrant.query_points(query=<query vector>, limit=2)` | embed the question, return the 2 nearest chunks by cosine similarity (top-k) |

Qdrant uses an index (HNSW), so retrieval does not compare the query against
every stored vector — this is the reason to use a vector DB rather than a
dictionary + manual cosine loop.

Everything (read/chunk/embed/store/retrieve) lives in the tool server, not the
agent, so optimisations (skip re-embedding an unchanged PDF, multi-PDF filters,
citations in the payload) all live in one place.

---

## Configuration

| What | Where | Default |
|---|---|---|
| LLM model | `ai-tutor/llm_ollama.py` `MODEL_NAME` | `qwen2.5:7b-instruct` |
| Ollama URL | `ai-tutor/llm_ollama.py` `base_url` | `http://localhost:11434` |
| MCP server URL | `ai-tutor/mcp_client.py` `MCP_URL` | `http://127.0.0.1:8000/sse` |
| Agent port | `uvicorn ... --port` | `8001` |
| Qdrant host/port | `mcp-server-ai-tutor/main.py` `QdrantClient(...)` | `localhost:6333` |
| Collection name | `mcp-server-ai-tutor/main.py` `QDRANT_COLLECTION` | `pdf_chunks` |
| Embedding model | `mcp-server-ai-tutor/main.py` `SentenceTransformer(...)` | `all-MiniLM-L6-v2` (384-dim) |
| Chunk size / overlap | `chunk_text(...)` | `500` / `50` |
| Retrieved chunks (top-k) | `query_points(..., limit=2)` | `2` |

Model sizing on 24 GB RAM: `qwen2.5:7b-instruct` (~4.7 GB, needs ~6–8 GB while
running) is comfortable. `qwen2.5:3b-instruct` is faster/lighter;
`qwen2.5:14b-instruct` (~9 GB) is better quality and still fits.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` | `mcp 2.x` renamed the API. `requirements.txt` pins `mcp<2`; reinstall in the venv. |
| `docker: error getting credentials ... docker-credential-desktop ... not found` | Leftover from a previous Docker Desktop install. Remove `"credsStore": "desktop"` from `~/.docker/config.json`. |
| `Cannot connect to the Docker daemon` | `colima start` (or launch Docker Desktop). |
| Agent returns an error mentioning connection refused to `:8000` | Tool server not running, or started after the agent — start `mcp-server-ai-tutor` first. |
| First PDF request is slow / logs show Hugging Face downloads | One-time embedding-model download; cached afterwards. |
| Edits to `mcp-server-ai-tutor/main.py` not picked up | No `--reload` for the SSE server; restart `python main.py`. |
| `FutureWarning: get_sentence_embedding_dimension ... renamed` | Harmless deprecation warning from `sentence-transformers`; still returns 384. |
| `address already in use` on 8000/8001 | A previous process is still bound: `lsof -nP -iTCP:8001 -sTCP:LISTEN` then `kill` it. |

---

## Restarting the stack later

```bash
colima start                                   # Docker engine
brew services start ollama                      # LLM server
docker start qdrant                             # if not already running
cd mcp-server-ai-tutor && source venv/bin/activate && python main.py     # tab 1
cd ai-tutor          && source venv/bin/activate && uvicorn main:app --port 8001   # tab 2
```
