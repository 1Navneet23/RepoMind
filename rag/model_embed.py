from sentence_transformers import SentenceTransformer

# FIX #8: lazy-load the model only when first accessed, not on every import
_embedding_model = None


def get_embedding_model() -> SentenceTransformer:
    """Return the shared embedding model, loading it on first call."""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model