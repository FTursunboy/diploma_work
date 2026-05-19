import json
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Document, DocumentChunk
from services.ai_log_service import AiLogService
from services.embedding_service import EmbeddingService


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b

    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


class VectorSearchService:
    def __init__(self, db: Session, embedding_service: EmbeddingService | None = None):
        self._db = db
        self._embedding_service = embedding_service or EmbeddingService()

    def search(
        self,
        *,
        query: str,
        document_id: int | None = None,
        limit: int = 10,
        user_id: int | None = None,
    ) -> list[dict[str, int | float | str | None]]:
        normalized = (query or "").strip()
        if not normalized:
            return []

        try:
            result = self._embedding_service.get_embedding_result(normalized)
            query_embedding = result.embedding
        except Exception as exc:
            AiLogService(self._db).create(
                operation="semantic_search",
                status="error",
                user_id=user_id,
                document_id=document_id,
                model=getattr(self._embedding_service, "model", None),
                request_text=normalized,
                error_message=str(exc),
            )
            raise

        statement = (
            select(DocumentChunk, Document.filename, Document.title)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.embedding.is_not(None))
        )
        if document_id is not None:
            statement = statement.where(DocumentChunk.document_id == document_id)

        scored: list[dict[str, int | float | str | None]] = []
        for chunk, filename, title in self._db.execute(statement).all():
            try:
                chunk_embedding = json.loads(chunk.embedding or "[]")
            except json.JSONDecodeError:
                continue
            score = cosine_similarity(query_embedding, chunk_embedding)
            scored.append(
                {
                    "document_id": int(chunk.document_id),
                    "chunk_id": int(chunk.id),
                    "chunk_index": int(chunk.chunk_index),
                    "chunk_text": chunk.chunk_text,
                    "score": round(float(score), 4),
                    "filename": filename,
                    "title": title,
                }
            )

        scored.sort(key=lambda item: float(item["score"]), reverse=True)
        top_results = scored[:limit]
        response_text = "; ".join(
            f"doc={item['document_id']},chunk={item['chunk_id']},score={item['score']}" for item in top_results
        )
        AiLogService(self._db).create(
            operation="semantic_search",
            status="success",
            user_id=user_id,
            document_id=document_id,
            model=result.model,
            request_text=normalized,
            response_text=response_text or "no_results",
            prompt_tokens=result.prompt_tokens,
            total_tokens=result.total_tokens,
            duration_ms=result.duration_ms,
        )
        return top_results
