from mcp.server.fastmcp import FastMCP
import requests
import uuid

from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

mcp = FastMCP()

QDRANT_COLLECTION = "pdf_chunks"

qdrant = QdrantClient(host="localhost", port=6333)

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
embedding_dim = embedding_model.get_sentence_embedding_dimension()

if QDRANT_COLLECTION not in [c.name for c in qdrant.get_collections().collections]:
    qdrant.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(
            size=embedding_dim,
            distance=Distance.COSINE,
        ),
    )

@mcp.tool(
    name="get_crypto_price",
    description="Fetch the current price of a cryptocurrency from CoinGecko."
)
def get_crypto_price(
    coin: str,
    currency: str = "usd"
) -> float:

    coin = coin.lower()
    currency = currency.lower()

    url = "https://api.coingecko.com/api/v3/simple/price"

    params = {
        "ids": coin,
        "vs_currencies": currency
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    if coin not in data or currency not in data[coin]:
        raise ValueError("Price data not found")

    return data[coin][currency]

@mcp.tool(
    name="ingest_and_query_pdf",
    description="Ingest a PDF (chunk, embed, store), then retrieve relevant chunks to answer a query."
)
def ingest_and_query_pdf(pdf_path: str, query: str) -> dict:
    if not pdf_path:
        raise ValueError("pdf_path is required")

    if not query:
        raise ValueError("query is required")

    reader = PdfReader(pdf_path)
    full_text = ""

    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"

    if not full_text.strip():
        raise ValueError("No text found in PDF")

    def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50):
        words = text.split()
        chunks = []
        start = 0

        while start < len(words):
            end = start + chunk_size
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            start = end - overlap

        return chunks

    chunks = chunk_text(full_text)

    embeddings = embedding_model.encode(chunks, convert_to_numpy=True).tolist()

    points = []

    for chunk, vector in zip(chunks, embeddings):
        point_id = str(uuid.uuid4())

        points.append(
            PointStruct(
                id=point_id,
                vector=vector,
                payload={"text": chunk}
            )
        )

    qdrant.upsert(
        collection_name=QDRANT_COLLECTION,
        points=points
    )

    query_embedding = embedding_model.encode(query, convert_to_numpy=True)

    search_result = qdrant.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_embedding.tolist(),
        limit=2
    )

    top_chunks = [point.payload["text"] for point in search_result.points]

    return {
        "chunks": top_chunks
    }

if __name__ == "__main__":
    mcp.run(transport="sse")
