import os
import time

from sqlalchemy.orm import Session

from database import Document
from services.ai_log_service import AiLogService
from services.embedding_service import EmbeddingService
from splitter import split_paragraphs


DEFAULT_SUMMARY_MODEL = "gpt-5-nano"
DEFAULT_SUMMARY_MAX_CHARS = 9000
CONTEXT_KEYWORDS: dict[str, int] = {
    "введение": 7,
    "актуаль": 8,
    "цель": 9,
    "задач": 8,
    "объект": 5,
    "предмет": 5,
    "метод": 5,
    "исследован": 4,
    "научн": 4,
    "новизн": 8,
    "практическ": 6,
    "теоретическ": 4,
    "результат": 7,
    "вывод": 9,
    "заключен": 9,
    "итог": 7,
    "основн": 3,
    "апробац": 4,
    "рекомендац": 4,
}


class SummaryService:
    def __init__(self, db: Session, *, model: str | None = None):
        self._db = db
        self.model = model or os.getenv("OPENAI_SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL)

    @staticmethod
    def is_configured() -> bool:
        return EmbeddingService.is_configured()

    def generate_for_document(self, *, document: Document, text: str) -> str | None:
        if not self.is_configured():
            return None

        prompt = self._build_prompt(document=document, text=text)
        try:
            summary, usage, duration_ms = self._request_summary(prompt)
        except Exception as exc:
            AiLogService(self._db).create(
                operation="summary_generation",
                status="error",
                document_id=document.id,
                model=self.model,
                request_text=prompt,
                error_message=str(exc),
            )
            return None

        document.ai_summary = summary
        self._db.add(document)
        self._db.commit()

        AiLogService(self._db).create(
            operation="summary_generation",
            status="success",
            document_id=document.id,
            model=self.model,
            request_text=prompt,
            response_text=summary,
            prompt_tokens=usage.get("prompt_tokens"),
            total_tokens=usage.get("total_tokens"),
            duration_ms=duration_ms,
        )
        return summary

    def _request_summary(self, prompt: str) -> tuple[str, dict[str, int | None], int]:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI Python package is not installed. Run `pip install .` or rebuild Docker.") from exc

        client = OpenAI()
        started = time.perf_counter()
        response = client.responses.create(
            model=self.model,
            input=prompt,
            reasoning={"effort": "minimal"},
            max_output_tokens=1200,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        summary = (getattr(response, "output_text", None) or "").strip()
        if not summary:
            summary = self._extract_output_text(response).strip()
        if not summary:
            raise RuntimeError("Summary model returned an empty response.")

        usage_raw = getattr(response, "usage", None)
        usage = {
            "prompt_tokens": getattr(usage_raw, "input_tokens", None) if usage_raw is not None else None,
            "total_tokens": getattr(usage_raw, "total_tokens", None) if usage_raw is not None else None,
        }
        return summary, usage, duration_ms

    def _build_prompt(self, *, document: Document, text: str) -> str:
        context = self._select_context(text)
        meta = "\n".join(
            [
                f"Название: {document.title or document.filename}",
                f"Автор: {document.author or 'не указан'}",
                f"Издательство: {document.publisher or 'не указано'}",
                f"Год: {document.publication_year or 'не указан'}",
                f"Тип документа: {document.doc_type or 'не указан'}",
                f"Библиография: {document.bibliography or 'не указана'}",
            ]
        )
        return (
            "Составь краткую аннотацию книги для электронной библиотеки.\n"
            "Ответь на таджикском языке, кириллицей, 2 коротких абзаца, без списков.\n"
            "Опирайся в первую очередь на фрагменты текста и метаданные. "
            "Если информации недостаточно, не выдумывай факты.\n\n"
            f"Метаданные:\n{meta}\n\n"
            f"Фрагменты текста книги:\n{context}"
        )

    def _select_context(self, text: str) -> str:
        paragraphs = split_paragraphs(text or "")
        if not paragraphs:
            return " ".join((text or "").split())

        limit = self._max_chars()
        normalized_paragraphs = [" ".join(paragraph.split()) for paragraph in paragraphs if paragraph.strip()]
        joined = "\n\n".join(normalized_paragraphs)
        if len(joined) <= limit:
            return joined

        ranked = self._rank_paragraphs(normalized_paragraphs)
        chosen_indexes: list[int] = []
        current_length = 0

        for index, _score in ranked:
            paragraph = normalized_paragraphs[index]
            extra = len(paragraph) + (4 if chosen_indexes else 0)
            if chosen_indexes and current_length + extra > limit:
                continue
            if not chosen_indexes and len(paragraph) > limit:
                return paragraph[:limit].strip()
            chosen_indexes.append(index)
            current_length += extra
            if current_length >= limit:
                break

        if not chosen_indexes:
            return joined[:limit].strip()

        chosen_indexes.sort()
        selected_parts: list[str] = []
        previous_index = None
        for index in chosen_indexes:
            if previous_index is not None and index - previous_index > 1:
                selected_parts.append("...")
            selected_parts.append(normalized_paragraphs[index])
            previous_index = index

        context = "\n\n".join(selected_parts).strip()
        return context[:limit].strip()

    def _rank_paragraphs(self, paragraphs: list[str]) -> list[tuple[int, int]]:
        total = len(paragraphs)
        ranked: list[tuple[int, int]] = []
        for index, paragraph in enumerate(paragraphs):
            score = self._paragraph_score(paragraph=paragraph, index=index, total=total)
            ranked.append((index, score))
        ranked.sort(key=lambda item: (item[1], -item[0] if item[0] > total // 2 else item[0]), reverse=True)
        return ranked

    def _paragraph_score(self, *, paragraph: str, index: int, total: int) -> int:
        lower = paragraph.lower().replace("ё", "е")
        score = 0

        for keyword, weight in CONTEXT_KEYWORDS.items():
            if keyword in lower:
                score += weight

        if index == 0:
            score += 7
        elif index <= min(2, total - 1):
            score += 4

        if index >= max(0, total - 2):
            score += 7
        elif index >= max(0, total - 4):
            score += 4

        length = len(paragraph)
        if 250 <= length <= 1400:
            score += 4
        elif 120 <= length < 250:
            score += 2
        elif length > 1800:
            score -= 2
        elif length < 80:
            score -= 3

        if any(char.isdigit() for char in paragraph):
            score += 1

        return score

    def _max_chars(self) -> int:
        raw = os.getenv("OPENAI_SUMMARY_MAX_CHARS", str(DEFAULT_SUMMARY_MAX_CHARS))
        try:
            value = int(raw)
        except ValueError:
            return DEFAULT_SUMMARY_MAX_CHARS
        return max(2000, min(20000, value))

    def _extract_output_text(self, response) -> str:
        parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
