import json
import shutil
import threading
from pathlib import Path
from uuid import uuid4

from docx import Document as DocxDocument
from pypdf import PdfReader
from sqlalchemy.orm import Session

from database import Document, DocumentChunk, Paragraph, Sentence, SessionLocal, UPLOAD_DIR, Word
from services.ai_log_service import AiLogService
from services.chunk_service import split_text_chunks
from services.embedding_service import EmbeddingService
from services.summary_service import SummaryService
from splitter import normalize_text, split_paragraphs, split_sentences, split_words


SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


class DocumentParserService:
    def __init__(self, db: Session | None):
        self._db = db

    def validate_extension(self, file_name: str) -> str:
        extension = Path(file_name).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError("Танҳо файлҳои PDF ва DOCX дастгирӣ мешаванд.")
        return extension

    def copy_file_to_storage(self, source_path: Path) -> tuple[str, Path]:
        extension = self.validate_extension(source_path.name)
        stored_name = f"{uuid4().hex}{extension}"
        destination = UPLOAD_DIR / stored_name
        shutil.copy2(source_path, destination)
        return extension, destination

    def save_upload_file(self, upload_file) -> tuple[str, Path]:
        extension = self.validate_extension(upload_file.filename or "")
        stored_name = f"{uuid4().hex}{extension}"
        destination = UPLOAD_DIR / stored_name
        with destination.open("wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
        return extension, destination

    def create_uploaded_document(
        self,
        *,
        filename: str,
        file_type: str,
        stored_path: Path,
        title: str | None = None,
        author: str | None = None,
        publisher: str | None = None,
        publication_year: int | None = None,
        doc_type: str | None = None,
        bibliography: str | None = None,
    ) -> Document:
        if self._db is None:
            raise RuntimeError("Database session is required for create_uploaded_document().")
        document = Document(
            filename=filename,
            file_type=file_type,
            stored_path=str(stored_path),
            status="uploaded",
            title=title,
            author=author,
            publisher=publisher,
            publication_year=publication_year,
            doc_type=doc_type,
            bibliography=bibliography,
        )
        self._db.add(document)
        self._db.commit()
        self._db.refresh(document)
        return document

    def extract_pdf_text(self, file_path: Path) -> str:
        reader = PdfReader(str(file_path))
        page_texts = [page.extract_text() or "" for page in reader.pages]
        return normalize_text("\n\n".join(page_texts))

    def extract_docx_text(self, file_path: Path) -> str:
        document = DocxDocument(str(file_path))
        paragraph_texts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
        return normalize_text("\n\n".join(paragraph_texts))

    def extract_text(self, file_path: Path, file_type: str) -> str:
        if file_type == ".pdf":
            return self.extract_pdf_text(file_path)
        if file_type == ".docx":
            return self.extract_docx_text(file_path)
        raise ValueError("Формати файл дастгирӣ намешавад.")

    def parse_document(self, document: Document) -> dict[str, int]:
        if self._db is None:
            raise RuntimeError("Database session is required for parse_document().")
        try:
            structured_text = self.extract_text(Path(document.stored_path), document.file_type)
            if not structured_text:
                raise ValueError("Аз файл матн бароварда нашуд.")

            document.full_text = " ".join(structured_text.split())
            document.status = "parsed"
            document.ai_status = "pending"
            document.ai_summary = None
            document.error_message = None

            self._db.query(Word).filter(Word.document_id == document.id).delete()
            self._db.query(Sentence).filter(Sentence.document_id == document.id).delete()
            self._db.query(Paragraph).filter(Paragraph.document_id == document.id).delete()
            self._db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()

            paragraphs = split_paragraphs(structured_text)
            sentence_counter = 0
            word_counter = 0

            for paragraph_index, paragraph_text in enumerate(paragraphs, start=1):
                paragraph = Paragraph(
                    document_id=document.id,
                    paragraph_index=paragraph_index,
                    text=paragraph_text,
                )
                self._db.add(paragraph)
                self._db.flush()

                sentences = split_sentences(paragraph_text)
                for sentence_index, sentence_text in enumerate(sentences, start=1):
                    sentence_counter += 1
                    sentence = Sentence(
                        document_id=document.id,
                        paragraph_id=paragraph.id,
                        sentence_index=sentence_index,
                        text=sentence_text,
                    )
                    self._db.add(sentence)
                    self._db.flush()

                    for word_text in split_words(sentence_text):
                        word_counter += 1
                        self._db.add(
                            Word(
                                document_id=document.id,
                                sentence_id=sentence.id,
                                word_index=word_counter,
                                word=word_text,
                            )
                        )

            self._db.commit()

            return {
                "paragraphs": len(paragraphs),
                "sentences": sentence_counter,
                "words": word_counter,
                "chunks": 0,
            }
        except Exception as exc:
            self._db.rollback()
            document.status = "error"
            document.error_message = str(exc)
            self._db.add(document)
            self._db.commit()
            return {"paragraphs": 0, "sentences": 0, "words": 0, "chunks": 0}

    def run_ai_processing_for_document(self, *, document_id: int) -> None:
        if self._db is None:
            raise RuntimeError("Database session is required for run_ai_processing_for_document().")

        document = self._db.get(Document, document_id)
        if document is None or document.status != "parsed":
            return

        document.ai_status = "processing"
        self._db.add(document)
        self._db.commit()

        try:
            structured_text = self.extract_text(Path(document.stored_path), document.file_type)
            if not structured_text:
                structured_text = document.full_text or ""
            self.index_document_chunks(document=document, structured_text=structured_text)
            SummaryService(self._db).generate_for_document(document=document, text=structured_text)
            document.ai_status = "ready"
            document.error_message = None
            self._db.add(document)
            self._db.commit()
        except Exception as exc:
            self._db.rollback()
            document = self._db.get(Document, document_id)
            if document is not None:
                document.ai_status = "error"
                document.error_message = str(exc)
                self._db.add(document)
                self._db.commit()

    def index_document_chunks(self, *, document: Document, structured_text: str) -> int:
        if self._db is None:
            raise RuntimeError("Database session is required for index_document_chunks().")

        chunks = split_text_chunks(structured_text)
        if not chunks:
            return 0

        self._db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()

        embedding_service = None
        if EmbeddingService.is_configured():
            try:
                embedding_service = EmbeddingService()
            except Exception:
                embedding_service = None

        created = 0
        for chunk_index, chunk_text in enumerate(chunks, start=1):
            embedding_json = None
            embedding_model = None
            if embedding_service is not None:
                started_model = embedding_service.model
                try:
                    result = embedding_service.get_embedding_result(chunk_text)
                    embedding_json = json.dumps(result.embedding, separators=(",", ":"))
                    embedding_model = result.model
                    AiLogService(self._db).create(
                        operation="embedding_chunk",
                        status="success",
                        document_id=document.id,
                        model=result.model,
                        request_text=chunk_text,
                        response_text=f"chunk_index={chunk_index}; vector_dimensions={len(result.embedding)}",
                        prompt_tokens=result.prompt_tokens,
                        total_tokens=result.total_tokens,
                        duration_ms=result.duration_ms,
                    )
                except Exception as exc:
                    embedding_json = None
                    embedding_model = started_model
                    AiLogService(self._db).create(
                        operation="embedding_chunk",
                        status="error",
                        document_id=document.id,
                        model=started_model,
                        request_text=chunk_text,
                        error_message=str(exc),
                    )

            self._db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    embedding=embedding_json,
                    embedding_model=embedding_model,
                )
            )
            created += 1

        self._db.commit()
        return created

    def load_document_from_path(
        self,
        *,
        file_path: str,
        title: str | None = None,
        author: str | None = None,
        publisher: str | None = None,
        publication_year: int | None = None,
        doc_type: str | None = None,
        bibliography: str | None = None,
    ) -> tuple[Document, dict[str, int]]:
        if self._db is None:
            raise RuntimeError("Database session is required for load_document_from_path().")
        source_path = Path(file_path)
        if not source_path.exists() or not source_path.is_file():
            raise ValueError("Файл ёфт нашуд.")

        file_type, stored_path = self.copy_file_to_storage(source_path)
        document = self.create_uploaded_document(
            filename=source_path.name,
            file_type=file_type,
            stored_path=stored_path,
            title=title,
            author=author,
            publisher=publisher,
            publication_year=publication_year,
            doc_type=doc_type,
            bibliography=bibliography,
        )
        counts = self.parse_document(document)
        self._db.refresh(document)
        return document, counts


def run_ai_processing_job(document_id: int) -> None:
    db = SessionLocal()
    try:
        DocumentParserService(db).run_ai_processing_for_document(document_id=document_id)
    finally:
        db.close()


def start_ai_processing_job(document_id: int) -> None:
    thread = threading.Thread(
        target=run_ai_processing_job,
        args=(document_id,),
        name=f"ai-processing-document-{document_id}",
        daemon=True,
    )
    thread.start()
