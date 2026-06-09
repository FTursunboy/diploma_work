import json
import math
import os
import re
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Document, DocumentChunk, Paragraph, ParagraphEmbeddingBlock
from services.ai_log_service import AiLogService
from services.embedding_service import EmbeddingService


DEFAULT_RERANK_MODEL = "gpt-5-nano"
DEFAULT_RERANK_TOP_K = 12
DEFAULT_RERANK_CANDIDATE_LIMIT = 20
DEFAULT_MIN_SEMANTIC_SCORE = 0.18


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


def _normalize_search_text(text: str) -> str:
    lowered = str(text or "").lower().replace("ё", "е")
    return " ".join(re.findall(r"[0-9a-zа-я]+", lowered, flags=re.IGNORECASE))


def _tokenize(text: str) -> list[str]:
    normalized = _normalize_search_text(text)
    return [token for token in normalized.split(" ") if token]


def _lexical_score(query: str, text: str) -> float:
    normalized_query = _normalize_search_text(query)
    normalized_text = _normalize_search_text(text)
    if not normalized_query or not normalized_text:
        return 0.0

    query_tokens = _tokenize(normalized_query)
    text_tokens = _tokenize(normalized_text)
    if not query_tokens or not text_tokens:
        return 0.0

    unique_query_tokens = list(dict.fromkeys(query_tokens))
    exact_hits = sum(1 for token in unique_query_tokens if token in text_tokens)
    soft_hits = 0
    for token in unique_query_tokens:
        if token in text_tokens:
            continue
        if len(token) < 5:
            continue
        if any(token in candidate or candidate in token for candidate in text_tokens):
            soft_hits += 1

    token_coverage = min(1.0, (exact_hits + soft_hits * 0.6) / max(1, len(unique_query_tokens)))
    phrase_bonus = 1.0 if normalized_query in normalized_text else 0.0

    bigrams = [f"{query_tokens[i]} {query_tokens[i + 1]}" for i in range(len(query_tokens) - 1)]
    bigram_hits = sum(1 for bigram in bigrams if bigram in normalized_text)
    bigram_score = (bigram_hits / len(bigrams)) if bigrams else 0.0

    return round(min(1.0, token_coverage * 0.6 + phrase_bonus * 0.25 + bigram_score * 0.15), 4)


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

        paragraph_results = self._search_paragraph_embeddings(
            query=normalized,
            query_embedding=query_embedding,
            document_id=document_id,
        )
        if paragraph_results:
            candidates = paragraph_results[: self._candidate_limit(limit)]
            reranked = (
                self._rerank_candidates(
                    query=normalized,
                    candidates=candidates,
                    document_id=document_id,
                    user_id=user_id,
                )
                if self._rerank_enabled()
                else candidates
            )
            top_results = reranked[:limit]
        else:
            top_results = self._search_chunk_fallback(
                query=normalized,
                query_embedding=query_embedding,
                document_id=document_id,
                limit=limit,
            )

        response_text = "; ".join(
            f"doc={item['document_id']},paragraph={item.get('paragraph_index')}-{item.get('paragraph_end_index')},score={item['score']}"
            for item in top_results
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

    def _search_paragraph_embeddings(
        self,
        *,
        query: str,
        query_embedding: list[float],
        document_id: int | None = None,
    ) -> list[dict[str, int | float | str | None]]:
        statement = (
            select(ParagraphEmbeddingBlock, Document.filename, Document.title)
            .join(Document, Document.id == ParagraphEmbeddingBlock.document_id)
            .where(Document.deleted_at.is_(None), ParagraphEmbeddingBlock.embedding.is_not(None))
            .order_by(ParagraphEmbeddingBlock.document_id, ParagraphEmbeddingBlock.block_index)
        )
        if document_id is not None:
            statement = statement.where(ParagraphEmbeddingBlock.document_id == document_id)

        scored: list[dict[str, int | float | str | None]] = []
        for block, filename, title in self._db.execute(statement).all():
            try:
                paragraph_embedding = json.loads(block.embedding or "[]")
            except json.JSONDecodeError:
                continue
            block_text = str(block.block_text or "")
            semantic_score = cosine_similarity(query_embedding, paragraph_embedding)
            lexical_score = _lexical_score(query, block_text)
            if not self._passes_relevance_floor(semantic_score=semantic_score, lexical_score=lexical_score):
                continue
            final_score = round(max(0.0, semantic_score) * 0.85 + lexical_score * 0.15, 4)
            scored.append(
                {
                    "document_id": int(block.document_id),
                    "chunk_id": None,
                    "chunk_index": None,
                    "chunk_text": None,
                    "text": block_text,
                    "paragraph_index": int(block.start_paragraph_index),
                    "paragraph_end_index": int(block.end_paragraph_index),
                    "paragraph_text": block_text,
                    "sentence_index": None,
                    "score": final_score,
                    "semantic_score": round(float(semantic_score), 4),
                    "keyword_score": round(lexical_score, 4),
                    "structure_score": None,
                    "filename": filename,
                    "title": title,
                }
            )

        scored.sort(key=lambda item: float(item["score"]), reverse=True)
        return scored

    def _search_chunk_fallback(
        self,
        *,
        query: str,
        query_embedding: list[float],
        document_id: int | None = None,
        limit: int = 10,
    ) -> list[dict[str, int | float | str | None]]:
        statement = (
            select(DocumentChunk, Document.filename, Document.title)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.deleted_at.is_(None), DocumentChunk.embedding.is_not(None))
        )
        if document_id is not None:
            statement = statement.where(DocumentChunk.document_id == document_id)

        paragraph_map = self._load_document_paragraphs(document_id=document_id)
        scored: list[dict[str, int | float | str | None]] = []
        for chunk, filename, title in self._db.execute(statement).all():
            try:
                chunk_embedding = json.loads(chunk.embedding or "[]")
            except json.JSONDecodeError:
                continue
            semantic_score = cosine_similarity(query_embedding, chunk_embedding)
            chunk_lexical_score = _lexical_score(query, chunk.chunk_text)
            if not self._passes_relevance_floor(semantic_score=semantic_score, lexical_score=chunk_lexical_score):
                continue
            paragraph_match = self._resolve_paragraph_match(
                document_id=int(chunk.document_id),
                query=query,
                chunk_text=chunk.chunk_text,
                paragraph_map=paragraph_map,
            )
            paragraph_index = paragraph_match["paragraph_index"]
            paragraph_text = paragraph_match["paragraph_text"]
            paragraph_score = float(paragraph_match["paragraph_score"] or 0.0)
            display_text = paragraph_text or chunk.chunk_text
            final_score = round(max(0.0, semantic_score) * 0.85 + max(chunk_lexical_score, paragraph_score) * 0.15, 4)
            scored.append(
                {
                    "document_id": int(chunk.document_id),
                    "chunk_id": int(chunk.id),
                    "chunk_index": int(chunk.chunk_index),
                    "chunk_text": chunk.chunk_text,
                    "text": display_text,
                    "paragraph_index": paragraph_index,
                    "paragraph_end_index": paragraph_index,
                    "paragraph_text": paragraph_text,
                    "sentence_index": None,
                    "score": final_score,
                    "semantic_score": round(float(semantic_score), 4),
                    "keyword_score": round(max(chunk_lexical_score, paragraph_score), 4),
                    "structure_score": None,
                    "filename": filename,
                    "title": title,
                }
            )

        scored.sort(key=lambda item: float(item["score"]), reverse=True)
        return scored[:limit]

    def _load_document_paragraphs(self, *, document_id: int | None = None) -> dict[int, list[dict[str, int | str]]]:
        statement = (
            select(Paragraph.document_id, Paragraph.paragraph_index, Paragraph.text)
            .join(Document, Document.id == Paragraph.document_id)
            .where(Document.deleted_at.is_(None))
            .order_by(Paragraph.document_id, Paragraph.paragraph_index)
        )
        if document_id is not None:
            statement = statement.where(Paragraph.document_id == document_id)

        rows = self._db.execute(statement).all()
        paragraph_map: dict[int, list[dict[str, int | str]]] = {}
        for doc_id, paragraph_index, text in rows:
            normalized = " ".join(str(text or "").split())
            if not normalized:
                continue
            paragraph_map.setdefault(int(doc_id), []).append(
                {
                    "paragraph_index": int(paragraph_index),
                    "text": normalized,
                    "normalized": _normalize_search_text(normalized),
                }
            )
        return paragraph_map

    def _resolve_paragraph_match(
        self,
        *,
        document_id: int,
        query: str,
        chunk_text: str,
        paragraph_map: dict[int, list[dict[str, int | str]]],
    ) -> dict[str, int | float | str | None]:
        paragraphs = paragraph_map.get(document_id) or []
        normalized_chunk = " ".join(str(chunk_text or "").split())
        normalized_chunk_for_search = _normalize_search_text(normalized_chunk)
        if not normalized_chunk:
            return {"paragraph_index": None, "paragraph_text": None, "paragraph_score": 0.0}

        best_match = {"paragraph_index": None, "paragraph_text": None, "paragraph_score": 0.0}
        for paragraph in paragraphs:
            paragraph_index = int(paragraph["paragraph_index"])
            paragraph_text = str(paragraph["text"])
            paragraph_normalized = str(paragraph["normalized"])
            contains_match = (
                paragraph_normalized in normalized_chunk_for_search or normalized_chunk_for_search in paragraph_normalized
            )
            if not contains_match:
                continue

            lexical_score = _lexical_score(query, paragraph_text)
            containment_bonus = 0.1 if paragraph_normalized and paragraph_normalized in normalized_chunk_for_search else 0.0
            match_score = round(min(1.0, lexical_score * 0.9 + containment_bonus), 4)
            if match_score > float(best_match["paragraph_score"] or 0.0):
                best_match = {
                    "paragraph_index": paragraph_index,
                    "paragraph_text": paragraph_text,
                    "paragraph_score": match_score,
                }

        if best_match["paragraph_index"] is not None:
            return best_match

        fallback_score = _lexical_score(query, chunk_text)
        return {"paragraph_index": None, "paragraph_text": None, "paragraph_score": fallback_score}

    def _candidate_limit(self, limit: int) -> int:
        return max(limit, min(self._rerank_top_k(), max(limit * 2, DEFAULT_RERANK_CANDIDATE_LIMIT)))

    def _min_semantic_score(self) -> float:
        raw = os.getenv("SEMANTIC_MIN_SCORE", str(DEFAULT_MIN_SEMANTIC_SCORE))
        try:
            value = float(raw)
        except ValueError:
            return DEFAULT_MIN_SEMANTIC_SCORE
        return max(0.0, min(1.0, value))

    def _passes_relevance_floor(self, *, semantic_score: float, lexical_score: float) -> bool:
        if lexical_score >= 0.15:
            return True
        return semantic_score >= self._min_semantic_score()

    def _rerank_enabled(self) -> bool:
        raw = (os.getenv("OPENAI_ENABLE_RERANK", "0") or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _rerank_model(self) -> str:
        return os.getenv("OPENAI_RERANK_MODEL", DEFAULT_RERANK_MODEL)

    def _rerank_top_k(self) -> int:
        raw = os.getenv("OPENAI_RERANK_TOP_K", str(DEFAULT_RERANK_TOP_K))
        try:
            value = int(raw)
        except ValueError:
            return DEFAULT_RERANK_TOP_K
        return max(5, min(20, value))

    def _rerank_candidates(
        self,
        *,
        query: str,
        candidates: list[dict[str, int | float | str | None]],
        document_id: int | None = None,
        user_id: int | None = None,
    ) -> list[dict[str, int | float | str | None]]:
        if not candidates:
            return candidates

        try:
            from openai import OpenAI
        except ImportError:
            return candidates

        rerank_slice = candidates[: self._rerank_top_k()]
        prompt_items = []
        for idx, item in enumerate(rerank_slice, start=1):
            paragraph_index = item.get("paragraph_index")
            text_value = " ".join(str(item.get("text") or "").split())
            prompt_items.append(
                f"{idx}. doc={item.get('document_id')}, paragraph={paragraph_index}, text={text_value[:1000]}"
            )

        prompt = (
            "Ты выполняешь второй этап ранжирования результатов семантического поиска по научным текстам.\n"
            "Учитывай намерение пользователя, точность ответа, терминологию, формулировки разделов и фактическую полезность.\n"
            "Верни только номера результатов в порядке убывания релевантности через запятую, без пояснений.\n\n"
            f"Запрос: {query}\n\n"
            "Кандидаты:\n"
            + "\n".join(prompt_items)
        )

        client = OpenAI()
        started = time.perf_counter()
        try:
            response = client.responses.create(
                model=self._rerank_model(),
                input=prompt,
                reasoning={"effort": "minimal"},
                max_output_tokens=120,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            raw_text = (getattr(response, "output_text", None) or "").strip()
            order = self._parse_rerank_order(raw_text, len(rerank_slice))
            if not order:
                raise ValueError("Empty rerank order.")

            ordered = [rerank_slice[index] for index in order]
            tail = candidates[len(rerank_slice) :]
            AiLogService(self._db).create(
                operation="semantic_search_rerank",
                status="success",
                user_id=user_id,
                document_id=document_id,
                model=self._rerank_model(),
                request_text=prompt,
                response_text=raw_text,
                duration_ms=duration_ms,
            )
            return ordered + tail
        except Exception as exc:
            AiLogService(self._db).create(
                operation="semantic_search_rerank",
                status="error",
                user_id=user_id,
                document_id=document_id,
                model=self._rerank_model(),
                request_text=prompt,
                error_message=str(exc),
            )
            return candidates

    def _parse_rerank_order(self, raw_text: str, limit: int) -> list[int]:
        seen: set[int] = set()
        order: list[int] = []
        for match in re.findall(r"\d+", raw_text or ""):
            value = int(match) - 1
            if value < 0 or value >= limit or value in seen:
                continue
            seen.add(value)
            order.append(value)
        for index in range(limit):
            if index not in seen:
                order.append(index)
        return order
