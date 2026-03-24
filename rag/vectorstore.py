import chromadb
import os
from rag.model_embed import get_embedding_model

_DATA_DIR    = "/data" if os.path.isdir("/data") else "."
_CHROMA_PATH = os.path.join(_DATA_DIR, "chroma_db")

client = chromadb.PersistentClient(path=_CHROMA_PATH)


def _get_collection(session_id: str):
    """Return (or create) the ChromaDB collection dedicated to this session."""
    return client.get_or_create_collection(f"session_{session_id}")


def store_embeddings(chunks: list[dict], session_id: str) -> None:
    """
    Encode and store a list of code chunks into the session's ChromaDB collection.

    FIX #1: IDs are derived from file + name + index to avoid collision across calls.
    FIX #2: chunk contents extracted once and reused for both embeddings and documents.
    """
    if not chunks:
        return

    collection = _get_collection(session_id)
    model = get_embedding_model()

    # FIX #2: build contents once — reused for both encoding and storing as documents
    contents = [c["content"] for c in chunks]
    embeddings = model.encode(contents).tolist()

    # FIX #1: unique IDs scoped to file + chunk name to prevent overwrite on re-ingestion
    ids = [f"{c['file']}::{c['name']}::{i}" for i, c in enumerate(chunks)]
    metadatas = [{"file": c["file"], "name": c["name"]} for c in chunks]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=contents,
        metadatas=metadatas
    )


def search_embeddings(query: str, session_id: str, top_k: int = 8) -> str:
    """
    Search the session's ChromaDB collection for chunks most similar to the query.
    Returns the top results joined as a single string for LLM context.

    FIX #3: guards against empty collection returning no results.
    """
    collection = _get_collection(session_id)
    model = get_embedding_model()

    query_embedding = model.encode([query]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=top_k)

    # FIX #3: guard against empty collection or no matching results
    if not results["documents"] or not results["documents"][0]:
        return ""

    top_chunks = results["documents"][0]
    return "\n\n---\n\n".join(top_chunks)