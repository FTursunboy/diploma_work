from sqlalchemy import select

from database import Document, Paragraph, Sentence

from .base import BaseSearchService


class SentenceSearchService(BaseSearchService):
    def search(
        self,
        *,
        query: str,
        document_id: int | None = None,
    ) -> list[dict[str, int | str | None]]:
        normalized = (query or "").strip()
        if not normalized:
            return []

        statement = (
            select(Document.id, Sentence.text, Paragraph.paragraph_index, Sentence.sentence_index)
            .join(Sentence, Sentence.document_id == Document.id)
            .join(Paragraph, Paragraph.id == Sentence.paragraph_id)
            .where(Document.deleted_at.is_(None), Sentence.text.ilike(f"%{normalized}%"))
            .order_by(Document.filename, Paragraph.paragraph_index, Sentence.sentence_index)
        )
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        rows = self._db.execute(statement).all()
        return [
            {
                "document_id": int(document_id_row),
                "text": text,
                "paragraph_index": int(paragraph_index) if paragraph_index is not None else None,
                "sentence_index": int(sentence_index) if sentence_index is not None else None,
            }
            for document_id_row, text, paragraph_index, sentence_index in rows
        ]
