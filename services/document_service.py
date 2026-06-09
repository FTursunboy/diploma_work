from pathlib import Path
import logging
import threading

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from database import (
    AiRequestLog,
    Document,
    DocumentChunk,
    DocumentNgram,
    Paragraph,
    ParagraphEmbeddingBlock,
    Sentence,
    Word,
)

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, db: Session):
        self._db = db

    def list_documents(self) -> list[dict]:
        documents = self._db.scalars(select(Document).order_by(Document.created_at.desc())).all()
        chunk_counts = dict(
            self._db.execute(select(DocumentChunk.document_id, func.count(DocumentChunk.id)).group_by(DocumentChunk.document_id)).all()
        )
        return [
            {
                "id": document.id,
                "filename": document.filename,
                "file_type": document.file_type,
                "title": document.title,
                "author": document.author,
                "publisher": document.publisher,
                "publication_year": document.publication_year,
                "doc_type": document.doc_type,
                "bibliography": document.bibliography,
                "ai_summary": document.ai_summary,
                "ai_status": document.ai_status,
                "status": document.status,
                "full_text": document.full_text,
                "error_message": document.error_message,
                "chunks_count": int(chunk_counts.get(document.id, 0)),
            }
            for document in documents
        ]

    def get_document_detail(self, *, document_id: int) -> dict:
        statement = (
            select(Document)
            .where(Document.id == document_id)
            .options(
                selectinload(Document.paragraphs),
                selectinload(Document.sentences),
                selectinload(Document.words),
                selectinload(Document.chunks),
            )
        )
        document = self._db.scalar(statement)
        if document is None:
            raise HTTPException(status_code=404, detail="Файл ёфт нашуд.")

        paragraph_map = {paragraph.id: paragraph.paragraph_index for paragraph in document.paragraphs}
        sentence_map = {sentence.id: sentence.sentence_index for sentence in document.sentences}

        return {
            "id": document.id,
            "filename": document.filename,
            "file_type": document.file_type,
            "title": document.title,
            "author": document.author,
            "publisher": document.publisher,
            "publication_year": document.publication_year,
            "doc_type": document.doc_type,
            "bibliography": document.bibliography,
            "ai_summary": document.ai_summary,
            "ai_status": document.ai_status,
            "status": document.status,
            "full_text": document.full_text,
            "error_message": document.error_message,
            "chunks_count": len(document.chunks),
            "paragraphs": [
                {
                    "id": paragraph.id,
                    "document_id": paragraph.document_id,
                    "paragraph_index": paragraph.paragraph_index,
                    "text": paragraph.text,
                }
                for paragraph in document.paragraphs
            ],
            "sentences": [
                {
                    "id": sentence.id,
                    "document_id": sentence.document_id,
                    "paragraph_id": sentence.paragraph_id,
                    "paragraph_index": paragraph_map.get(sentence.paragraph_id),
                    "sentence_index": sentence.sentence_index,
                    "text": sentence.text,
                }
                for sentence in document.sentences
            ],
            "words": [
                {
                    "id": word.id,
                    "document_id": word.document_id,
                    "sentence_id": word.sentence_id,
                    "sentence_index": sentence_map.get(word.sentence_id),
                    "word_index": word.word_index,
                    "word": word.word,
                }
                for word in document.words
            ],
        }

    def get_download_info(self, *, document_id: int) -> tuple[Path, str, str]:
        document = self._db.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Файл ёфт нашуд.")

        stored_path = Path(document.stored_path)
        if not stored_path.exists():
            raise HTTPException(status_code=404, detail="Файли аслӣ ёфт нашуд.")

        media_type = "application/octet-stream"
        if document.file_type == ".pdf":
            media_type = "application/pdf"
        elif document.file_type == ".doc":
            media_type = "application/msword"
        elif document.file_type == ".docx":
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        return stored_path, document.filename, media_type

    def mark_document_deleting(self, *, document_id: int) -> None:
        document = self._db.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Файл ёфт нашуд.")

        document.status = "deleting"
        document.error_message = None
        self._db.add(document)
        self._db.commit()

    def delete_document(self, *, document_id: int) -> str | None:
        return self.delete_document_now(document_id=document_id)

    def delete_document_now(self, *, document_id: int) -> str | None:
        document = self._db.get(Document, document_id)
        if document is None:
            return None

        stored_path = document.stored_path
        self._db.query(AiRequestLog).filter(AiRequestLog.document_id == document_id).delete(synchronize_session=False)
        self._db.query(Word).filter(Word.document_id == document_id).delete(synchronize_session=False)
        self._db.query(DocumentNgram).filter(DocumentNgram.document_id == document_id).delete(synchronize_session=False)
        self._db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete(synchronize_session=False)
        self._db.query(ParagraphEmbeddingBlock).filter(
            ParagraphEmbeddingBlock.document_id == document_id
        ).delete(synchronize_session=False)
        self._db.query(Sentence).filter(Sentence.document_id == document_id).delete(synchronize_session=False)
        self._db.query(Paragraph).filter(Paragraph.document_id == document_id).delete(synchronize_session=False)
        self._db.query(Document).filter(Document.id == document_id).delete(synchronize_session=False)
        self._db.commit()
        return stored_path


def run_document_deletion_job(document_id: int) -> None:
    from database import SessionLocal

    db = SessionLocal()
    try:
        stored_path = DocumentService(db).delete_document_now(document_id=document_id)
        if stored_path:
            try:
                Path(stored_path).unlink(missing_ok=True)
            except Exception:
                logger.exception("document_file_delete_error document_id=%s path=%s", document_id, stored_path)
    except Exception as exc:
        logger.exception("document_deletion_job_error document_id=%s", document_id)
        try:
            db.rollback()
            document = db.get(Document, document_id)
            if document is not None:
                document.status = "error"
                document.error_message = str(exc)
                db.add(document)
                db.commit()
        except Exception:
            logger.exception("document_deletion_error_save_failed document_id=%s", document_id)
    finally:
        db.close()


def start_document_deletion_job(document_id: int) -> None:
    thread = threading.Thread(
        target=run_document_deletion_job,
        args=(document_id,),
        name=f"document-deletion-{document_id}",
        daemon=True,
    )
    thread.start()


def resume_pending_document_deletions() -> None:
    from database import SessionLocal

    db = SessionLocal()
    try:
        document_ids = db.scalars(select(Document.id).where(Document.status == "deleting")).all()
    finally:
        db.close()

    for document_id in document_ids:
        start_document_deletion_job(int(document_id))
