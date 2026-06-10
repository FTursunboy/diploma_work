import argparse

from sqlalchemy import or_, select

from database import Document, SessionLocal, init_db
from services.document_parser_service import DocumentParserService


def _get_failed_document_ids(document_id: int | None, limit: int | None) -> list[int]:
    db = SessionLocal()
    try:
        statement = (
            select(Document.id)
            .where(
                Document.deleted_at.is_(None),
                or_(Document.status == "error", Document.ai_status == "error"),
            )
            .order_by(Document.id)
        )
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        if limit is not None:
            statement = statement.limit(limit)
        return [int(value) for value in db.scalars(statement).all()]
    finally:
        db.close()


def _reset_document(document_id: int, *, ai_only: bool) -> tuple[str, str]:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None or document.deleted_at is not None:
            return "missing", "document not found"

        if ai_only or document.status == "parsed":
            document.status = "parsed"
            document.ai_status = "pending"
        else:
            document.status = "uploaded"
            document.ai_status = "pending"
        document.error_message = None
        db.add(document)
        db.commit()
        return document.status, document.ai_status
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _process_document(document_id: int, *, ai_only: bool) -> None:
    db = SessionLocal()
    try:
        service = DocumentParserService(db)
        document = db.get(Document, document_id)
        if ai_only or document is None or document.status == "parsed":
            service.run_ai_processing_for_document(document_id=document_id)
        else:
            service.run_full_processing_for_document(document_id=document_id)
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry documents that failed during parsing or AI indexing.")
    parser.add_argument("--document-id", type=int, default=None, help="Retry only one document id.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of failed documents to retry.")
    parser.add_argument("--ai-only", action="store_true", help="Retry only AI/embedding processing.")
    parser.add_argument(
        "--process",
        action="store_true",
        help="Process documents immediately. Without this flag the script only resets statuses for app startup resume.",
    )
    args = parser.parse_args()

    init_db()
    document_ids = _get_failed_document_ids(document_id=args.document_id, limit=args.limit)
    if not document_ids:
        print("No failed documents found.")
        return

    print(f"Found failed documents: {', '.join(str(value) for value in document_ids)}")
    for document_id in document_ids:
        status, ai_status = _reset_document(document_id, ai_only=args.ai_only)
        print(f"document_id={document_id} reset status={status} ai_status={ai_status}")
        if args.process:
            print(f"document_id={document_id} processing started")
            _process_document(document_id, ai_only=args.ai_only or status == "parsed")
            print(f"document_id={document_id} processing finished")


if __name__ == "__main__":
    main()
