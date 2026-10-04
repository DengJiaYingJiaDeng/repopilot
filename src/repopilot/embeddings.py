"""Optional embedding providers; importing this module never loads model packages."""

from importlib import import_module
from typing import Protocol

from repopilot.openai_client import create_openai_client


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one numeric vector per input text, in input order."""


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings")
        self._client = create_openai_client(api_key)
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 64):
            batch = texts[start : start + 64]
            response = self._client.embeddings.create(model=self.model, input=batch)
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(batch):
                raise ValueError("Embedding provider returned the wrong number of vectors")
            vectors.extend([[float(value) for value in item.embedding] for item in ordered])
        return vectors


class LocalEmbedder:
    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        sentence_transformers = import_module("sentence_transformers")
        self._model = sentence_transformers.SentenceTransformer(model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts)
        return [[float(value) for value in row] for row in vectors]
