from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from database import Document, get_db, init_db
from parser import create_uploaded_document, load_document_from_path, parse_document, save_upload_file
from search import search_paragraph, search_phrase, search_sentence, search_word


init_db()
app = FastAPI(title="Book Parser API")


class FilePathRequest(BaseModel):
    file_path: str


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Book Parser API is running"}


@app.post("/documents/upload")
def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Имя файла обязательно.")

    try:
        file_type, stored_path = save_upload_file(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document = create_uploaded_document(db, file.filename, file_type, stored_path)
    counts = parse_document(db, document)
    db.refresh(document)

    return {
        "id": document.id,
        "filename": document.filename,
        "file_type": document.file_type,
        "status": document.status,
        "full_text": document.full_text,
        "error_message": document.error_message,
        "paragraphs_count": counts["paragraphs"],
        "sentences_count": counts["sentences"],
        "words_count": counts["words"],
    }


@app.post("/documents/from-path")
def upload_document_from_path(payload: FilePathRequest, db: Session = Depends(get_db)) -> dict:
    try:
        document, counts = load_document_from_path(db, payload.file_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "id": document.id,
        "filename": document.filename,
        "file_type": document.file_type,
        "status": document.status,
        "full_text": document.full_text,
        "error_message": document.error_message,
        "paragraphs_count": counts["paragraphs"],
        "sentences_count": counts["sentences"],
        "words_count": counts["words"],
    }


@app.get("/documents")
def list_documents(db: Session = Depends(get_db)) -> list[dict]:
    documents = db.scalars(select(Document).order_by(Document.created_at.desc())).all()
    return [
        {
            "id": document.id,
            "filename": document.filename,
            "file_type": document.file_type,
            "status": document.status,
            "full_text": document.full_text,
            "error_message": document.error_message,
        }
        for document in documents
    ]


@app.get("/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    statement = (
        select(Document)
        .where(Document.id == document_id)
        .options(
            selectinload(Document.paragraphs),
            selectinload(Document.sentences),
            selectinload(Document.words),
        )
    )
    document = db.scalar(statement)
    if document is None:
        raise HTTPException(status_code=404, detail="Документ не найден.")

    paragraph_map = {paragraph.id: paragraph.paragraph_index for paragraph in document.paragraphs}
    sentence_map = {sentence.id: sentence.sentence_index for sentence in document.sentences}

    return {
        "id": document.id,
        "filename": document.filename,
        "file_type": document.file_type,
        "status": document.status,
        "full_text": document.full_text,
        "error_message": document.error_message,
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


@app.get("/search")
def search(
    query: str = Query(..., min_length=1),
    target: str = Query("phrase", pattern="^(word|sentence|paragraph|phrase)$"),
    exact: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    if target == "word":
        results = search_word(db, query, exact=exact)
    elif target == "sentence":
        results = search_sentence(db, query)
    elif target == "paragraph":
        results = search_paragraph(db, query)
    else:
        results = search_phrase(db, query)

    return {"query": query, "target": target, "total": len(results), "results": results}


@app.get("/search/word")
def api_search_word(
    query: str = Query(..., min_length=1),
    exact: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    results = search_word(db, query, exact=exact)
    return {"query": query, "total": len(results), "results": results}


@app.get("/search/sentence")
def api_search_sentence(query: str = Query(..., min_length=1), db: Session = Depends(get_db)) -> dict:
    results = search_sentence(db, query)
    return {"query": query, "total": len(results), "results": results}


@app.get("/search/paragraph")
def api_search_paragraph(query: str = Query(..., min_length=1), db: Session = Depends(get_db)) -> dict:
    results = search_paragraph(db, query)
    return {"query": query, "total": len(results), "results": results}


@app.get("/search/phrase")
def api_search_phrase(query: str = Query(..., min_length=1), db: Session = Depends(get_db)) -> dict:
    results = search_phrase(db, query)
    return {"query": query, "total": len(results), "results": results}
