from rag.model_embed import get_embedding_model


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Embed a list of code chunks using the shared sentence-transformer model.

    FIX #4: does not mutate input dicts — creates new dicts with embedding added.
    FIX #5: converts numpy arrays to plain Python lists via .tolist().
    FIX #6: encodes all chunks in a single batch call for GPU/CPU efficiency.
    """
    if not chunks:
        return []

    model = get_embedding_model()

    # FIX #6: batch encode all content at once instead of one-by-one in a loop
    contents = [c["content"] for c in chunks]
    vectors = model.encode(contents).tolist()  # FIX #5: .tolist() → plain list, not numpy array

    # FIX #4: build new dicts instead of mutating the originals
    return [{**chunk, "embedding": vector} for chunk, vector in zip(chunks, vectors)]