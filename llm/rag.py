"""
RAG (Retrieval-Augmented Generation) for the local LLM chat app.

This is how you "feed the model more information" WITHOUT training
it -- your own documents live in docs/ (your knowledge repository:
plain .txt or .md files, add/remove/edit them like any other
git-tracked content), get chunked and embedded into a local vector
index, and the most relevant chunks are retrieved and handed to the
model as context at query time.

Everything here runs locally/offline after the one-time embedding
model download (sentence-transformers/all-MiniLM-L6-v2, ~90MB, tiny
compared to the LLM itself) -- no external API calls, consistent with
the rest of this app's offline design.
"""
import os
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

DOCS_DIR = Path(__file__).parent / "docs"
INDEX_DIR = Path(__file__).parent / ".rag_index"
INDEX_FILE = INDEX_DIR / "index.faiss"
CHUNKS_FILE = INDEX_DIR / "chunks.txt"  # one chunk per line, newline-escaped

EMBED_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 500       # characters per chunk
CHUNK_OVERLAP = 50     # characters of overlap between consecutive chunks

_embed_model = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(EMBED_MODEL_ID)
    return _embed_model


def _chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c.strip() for c in chunks if c.strip()]


def build_index() -> int:
    """
    Reads every .txt/.md file in docs/, chunks it, embeds every chunk,
    and writes a fresh FAISS index to disk. Call this whenever you add
    or change documents in docs/ -- it's a full rebuild, not
    incremental, which is simple and fast enough for a knowledge base
    of reasonable size (thousands of chunks). Returns the number of
    chunks indexed.
    """
    DOCS_DIR.mkdir(exist_ok=True)
    INDEX_DIR.mkdir(exist_ok=True)

    all_chunks = []
    for path in list(DOCS_DIR.glob("*.txt")) + list(DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        all_chunks.extend(_chunk_text(text))

    if not all_chunks:
        return 0

    model = _get_embed_model()
    embeddings = model.encode(all_chunks, show_progress_bar=False)
    embeddings = np.array(embeddings, dtype="float32")

    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)
    faiss.write_index(index, str(INDEX_FILE))

    # Chunks are stored with literal newlines escaped so one-chunk-per-
    # line stays valid even if a chunk itself contains a newline.
    with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(chunk.replace("\n", "\\n") + "\n")

    return len(all_chunks)


def retrieve(query: str, k: int = 3) -> list[str]:
    """
    Returns the top-k most relevant chunks for the query, or an empty
    list if no index has been built yet (e.g. docs/ is empty).
    """
    if not INDEX_FILE.exists() or not CHUNKS_FILE.exists():
        return []

    index = faiss.read_index(str(INDEX_FILE))
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        chunks = [line.rstrip("\n").replace("\\n", "\n") for line in f]

    if index.ntotal == 0 or not chunks:
        return []

    model = _get_embed_model()
    query_vec = np.array(model.encode([query]), dtype="float32")
    k = min(k, index.ntotal)
    distances, indices = index.search(query_vec, k)

    return [chunks[i] for i in indices[0] if 0 <= i < len(chunks)]


def index_stats() -> dict:
    doc_count = len(list(DOCS_DIR.glob("*.txt")) + list(DOCS_DIR.glob("*.md"))) if DOCS_DIR.exists() else 0
    chunk_count = 0
    if CHUNKS_FILE.exists():
        with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
            chunk_count = sum(1 for _ in f)
    return {"documents": doc_count, "chunks_indexed": chunk_count}