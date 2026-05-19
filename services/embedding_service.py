import os
import time
from dataclasses import dataclass


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass(frozen=True)
class EmbeddingResult:
    embedding: list[float]
    model: str
    prompt_tokens: int | None
    total_tokens: int | None
    duration_ms: int


class EmbeddingService:
    def __init__(self, *, model: str | None = None):
        self.model = model or os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        if not self.is_configured():
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI Python package is not installed. Run `pip install .` or rebuild Docker.") from exc

        self._client = OpenAI()

    @staticmethod
    def is_configured() -> bool:
        return bool((os.getenv("OPENAI_API_KEY") or "").strip())

    def get_embedding(self, text: str) -> list[float]:
        return self.get_embedding_result(text).embedding

    def get_embedding_result(self, text: str) -> EmbeddingResult:
        normalized = " ".join((text or "").split())
        if not normalized:
            raise ValueError("Text for embedding must not be empty.")

        started = time.perf_counter()
        response = self._client.embeddings.create(
            model=self.model,
            input=normalized,
            encoding_format="float",
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
        total_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
        return EmbeddingResult(
            embedding=list(response.data[0].embedding),
            model=str(getattr(response, "model", None) or self.model),
            prompt_tokens=prompt_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
        )
