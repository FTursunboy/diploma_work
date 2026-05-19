from pathlib import Path

from sqlalchemy.orm import Session

from database import Document
from services.document_parser_service import SUPPORTED_EXTENSIONS, DocumentParserService


def validate_extension(file_name: str) -> str:
    return DocumentParserService(None).validate_extension(file_name)


def copy_file_to_storage(source_path: Path) -> tuple[str, Path]:
    return DocumentParserService(None).copy_file_to_storage(source_path)


def save_upload_file(upload_file) -> tuple[str, Path]:
    return DocumentParserService(None).save_upload_file(upload_file)


def create_uploaded_document(
    db: Session,
    filename: str,
    file_type: str,
    stored_path: Path,
    *,
    title: str | None = None,
    author: str | None = None,
    publisher: str | None = None,
    publication_year: int | None = None,
    doc_type: str | None = None,
    bibliography: str | None = None,
) -> Document:
    return DocumentParserService(db).create_uploaded_document(
        filename=filename,
        file_type=file_type,
        stored_path=stored_path,
        title=title,
        author=author,
        publisher=publisher,
        publication_year=publication_year,
        doc_type=doc_type,
        bibliography=bibliography,
    )


def extract_pdf_text(file_path: Path) -> str:
    return DocumentParserService(None).extract_pdf_text(file_path)


def extract_docx_text(file_path: Path) -> str:
    return DocumentParserService(None).extract_docx_text(file_path)


def extract_text(file_path: Path, file_type: str) -> str:
    return DocumentParserService(None).extract_text(file_path, file_type)


def parse_document(db: Session, document: Document) -> dict[str, int]:
    return DocumentParserService(db).parse_document(document)


def load_document_from_path(
    db: Session,
    file_path: str,
    *,
    title: str | None = None,
    author: str | None = None,
    publisher: str | None = None,
    publication_year: int | None = None,
    doc_type: str | None = None,
    bibliography: str | None = None,
) -> tuple[Document, dict[str, int]]:
    return DocumentParserService(db).load_document_from_path(
        file_path=file_path,
        title=title,
        author=author,
        publisher=publisher,
        publication_year=publication_year,
        doc_type=doc_type,
        bibliography=bibliography,
    )

