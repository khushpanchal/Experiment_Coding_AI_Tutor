# mcp-server-ai-tutor

The **tool server**. An MCP server (FastMCP, SSE transport) that exposes the
capabilities the agent cannot do on its own: reaching the internet and
remembering documents.

Serves on `http://127.0.0.1:8000/sse`.

## Tools

| Tool | Signature | What it does |
|---|---|---|
| `get_crypto_price` | `(coin: str, currency: str = "usd") -> float` | Calls the CoinGecko public API. |
| `ingest_and_query_pdf` | `(pdf_path: str, query: str) -> {"chunks": [str, ...]}` | Reads the PDF, splits it into ~500-word overlapping chunks, embeds each with `all-MiniLM-L6-v2` (384-dim), upserts the vectors into Qdrant, then returns the top-2 chunks nearest to `query` by cosine similarity. |

## Run

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Requires a Qdrant instance reachable at `localhost:6333` (see the top-level
README). The embedding model downloads from Hugging Face on first run and is
cached afterwards. The `pdf_chunks` collection is created automatically on
startup if it does not exist.

## Notes

- SSE is used because `mcp.run(transport="sse")` streams; this is why the server
  is started with `python main.py` rather than `uvicorn`.
- There is no `--reload`; restart the process after editing.
- `mcp` is pinned to `<2` because the `1.x` API (`mcp.server.fastmcp.FastMCP`)
  was renamed in `2.x`.
