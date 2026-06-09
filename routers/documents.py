from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from database import get_db
from routers.dependencies import get_current_user, require_admin, require_moderator
from routers.schemas import FilePathRequest
from services.document_parser_service import DocumentParserService, start_document_processing_job
from services.document_service import DocumentService


router = APIRouter()


@router.post("/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    author: str | None = Form(None),
    doc_type: str | None = Form(None),
    publication_year: int | None = Form(None),
    publisher: str | None = Form(None),
    bibliography: str | None = Form(None),
    db: Session = Depends(get_db),
    _=Depends(require_moderator),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Номи файл ҳатмист.")

    parser = DocumentParserService(db)
    try:
        file_type, stored_path = parser.save_upload_file(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document = parser.create_uploaded_document(
        filename=file.filename,
        file_type=file_type,
        stored_path=stored_path,
        title=(title or "").strip() or None,
        author=(author or "").strip() or None,
        publisher=(publisher or "").strip() or None,
        publication_year=publication_year,
        doc_type=(doc_type or "").strip() or None,
        bibliography=(bibliography or "").strip() or None,
    )
    document.status = "processing"
    document.ai_status = "pending"
    db.add(document)
    db.commit()
    db.refresh(document)
    start_document_processing_job(document.id)

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
        "paragraphs_count": 0,
        "sentences_count": 0,
        "words_count": 0,
        "chunks_count": 0,
    }


@router.post("/documents/from-path")
def upload_document_from_path(
    payload: FilePathRequest,
    db: Session = Depends(get_db),
    _=Depends(require_moderator),
) -> dict:
    parser = DocumentParserService(db)
    try:
        document, counts = parser.load_document_from_path(
            file_path=payload.file_path,
            title=(payload.title or "").strip() or None,
            author=(payload.author or "").strip() or None,
            publisher=(payload.publisher or "").strip() or None,
            publication_year=payload.publication_year,
            doc_type=(payload.doc_type or "").strip() or None,
            bibliography=(payload.bibliography or "").strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    document.status = "processing"
    document.ai_status = "pending"
    db.add(document)
    db.commit()
    db.refresh(document)
    start_document_processing_job(document.id)
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
        "paragraphs_count": counts["paragraphs"],
        "sentences_count": counts["sentences"],
        "words_count": counts["words"],
        "chunks_count": counts.get("chunks", 0),
    }


@router.get("/documents")
def list_documents(db: Session = Depends(get_db), _=Depends(get_current_user)) -> list[dict]:
    return DocumentService(db).list_documents()


@router.get("/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)) -> dict:
    return DocumentService(db).get_document_detail(document_id=document_id)


@router.get("/documents/{document_id}/file")
def download_document_file(
    document_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> FileResponse:
    stored_path, filename, media_type = DocumentService(db).get_download_info(document_id=document_id)
    return FileResponse(str(Path(stored_path)), filename=filename, media_type=media_type)


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
) -> dict[str, int | str]:
    DocumentService(db).mark_document_deleting(document_id=document_id)
    return {"status": "deleted", "id": document_id}
