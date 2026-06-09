from sqlalchemy import select

from database import Document, Paragraph

from .base import BaseSearchService


class ParagraphSearchService(BaseSearchService):
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
            select(Document.id, Paragraph.text, Paragraph.paragraph_index)
            .join(Paragraph, Paragraph.document_id == Document.id)
            .where(Document.deleted_at.is_(None), Paragraph.text.ilike(f"%{normalized}%"))
            .order_by(Document.filename, Paragraph.paragraph_index)
        )
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        rows = self._db.execute(statement).all()
        return [
            {
                "document_id": int(document_id_row),
                "text": text,
                "paragraph_index": int(paragraph_index) if paragraph_index is not None else None,
                "sentence_index": None,
            }
            for document_id_row, text, paragraph_index in rows
        ]
