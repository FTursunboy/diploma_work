import os
import time

from sqlalchemy.orm import Session

from database import Document
from services.ai_log_service import AiLogService
from services.embedding_service import EmbeddingService


DEFAULT_SUMMARY_MODEL = "gpt-5-nano"
DEFAULT_SUMMARY_MAX_CHARS = 9000


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
        normalized = " ".join((text or "").split())
        limit = self._max_chars()
        if len(normalized) <= limit:
            return normalized

        part = limit // 3
        middle_start = max(0, (len(normalized) // 2) - (part // 2))
        return "\n\n...\n\n".join(
            [
                normalized[:part],
                normalized[middle_start : middle_start + part],
                normalized[-part:],
            ]
        )

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
