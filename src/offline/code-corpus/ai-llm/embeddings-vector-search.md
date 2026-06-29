---
language: python
tags: [ai, embeddings, vector-search, ollama, openai, cosine-similarity]
title: Embeddings & Vector Search
description: Creating text embeddings with Ollama or OpenAI, computing cosine similarity, and basic semantic search in Python
source: pattern
---

```python
import numpy as np
from typing import List

# ——— Embedding providers ———

def ollama_embed(texts: List[str], model: str = "nomic-embed-text") -> List[List[float]]:
    """Create embeddings via Ollama."""
    import requests
    resp = requests.post(
        "http://localhost:11434/api/embed",
        json={"model": model, "input": texts},
    )
    return resp.json()["embeddings"]


def openai_embed(texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
    """Create embeddings via OpenAI (requires OPENAI_API_KEY)."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.embeddings.create(model=model, input=texts)
    return [d.embedding for d in resp.data]

# ——— Similarity functions ———

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors (1.0 = identical, -1.0 = opposite)."""
    A, B = np.array(a), np.array(b)
    return float(np.dot(A, B) / (np.linalg.norm(A) * np.linalg.norm(B) + 1e-10))


def euclidean_distance(a: List[float], b: List[float]) -> float:
    return float(np.linalg.norm(np.array(a) - np.array(b)))


def dot_product(a: List[float], b: List[float]) -> float:
    return float(np.dot(np.array(a), np.array(b)))

# ——— Semantic search ———

class SemanticSearch:
    """Simple in-memory semantic search over a document store."""

    def __init__(self, embed_fn=ollama_embed):
        self.embed_fn = embed_fn
        self.docs: List[str] = []
        self.vectors: List[List[float]] = []

    def index(self, documents: List[str]):
        self.docs = documents
        self.vectors = self.embed_fn(documents)

    def search(self, query: str, top_k: int = 3) -> List[tuple[str, float]]:
        q_vec = self.embed_fn([query])[0]
        scores = [cosine_similarity(q_vec, vec) for vec in self.vectors]
        indices = np.argsort(scores)[::-1][:top_k]
        return [(self.docs[i], scores[i]) for i in indices]


if __name__ == "__main__":
    documents = [
        "PostgreSQL is a powerful open-source relational database.",
        "Ollama runs large language models locally on your machine.",
        "pgvector enables vector similarity search inside PostgreSQL.",
        "OpenAI provides hosted embedding and chat completion APIs.",
        "MCP (Model Context Protocol) standardizes LLM tool interactions.",
    ]

    # Index with Ollama embeddings
    search_engine = SemanticSearch(embed_fn=ollama_embed)
    search_engine.index(documents)

    results = search_engine.search("database for AI embeddings", top_k=2)
    print("Top results:")
    for doc, score in results:
        print(f"  {score:.4f}  {doc}")
```