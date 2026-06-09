from sqlalchemy import func, select

from database import Document, Paragraph, Sentence, Word

from .base import BaseSearchService


class WordSearchService(BaseSearchService):
    def search(
        self,
        *,
        query: str,
        exact: bool = False,
        mode: str | None = None,
        document_id: int | None = None,
    ) -> list[dict[str, int | str | None]]:
        normalized = (query or "").strip()
        if not normalized:
            return []

        normalized_lower = normalized.lower()
        if mode is None:
            mode = "exact" if exact else "partial"

        if mode == "exact":
            condition = func.lower(Word.word) == normalized_lower
        else:
            condition = func.lower(Word.word).like(f"%{normalized_lower}%")

        statement = (
            select(Document.id, Word.word, Paragraph.paragraph_index, Sentence.sentence_index)
            .join(Word, Word.document_id == Document.id)
            .join(Sentence, Sentence.id == Word.sentence_id)
            .join(Paragraph, Paragraph.id == Sentence.paragraph_id)
            .where(Document.deleted_at.is_(None), condition)
            .order_by(Document.filename, Paragraph.paragraph_index, Sentence.sentence_index, Word.word_index)
        )
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        rows = self._db.execute(statement).all()
        return [
            {
                "document_id": int(document_id_row),
                "text": word,
                "paragraph_index": int(paragraph_index) if paragraph_index is not None else None,
                "sentence_index": int(sentence_index) if sentence_index is not None else None,
            }
            for document_id_row, word, paragraph_index, sentence_index in rows
        ]
