from pathlib import Path

from collections import Counter, defaultdict

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from database import Document, Paragraph, Sentence, Word, get_db, init_db
from parser import create_uploaded_document, load_document_from_path, parse_document, save_upload_file
from search import search_paragraph, search_phrase, search_sentence, search_word


init_db()
app = FastAPI(title="Book Parser API")

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class FilePathRequest(BaseModel):
    file_path: str


@app.get("/", include_in_schema=False)
def root(request: Request):
    accept = request.headers.get("accept", "")
    index_file = WEB_DIR / "index.html"
    if "text/html" in accept and index_file.exists():
        return FileResponse(str(index_file), media_type="text/html")
    return {"message": "Book Parser API is running"}


@app.post("/documents/upload")
def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Номи файл ҳатмист.")

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
        raise HTTPException(status_code=404, detail="Файл ёфт нашуд.")

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


@app.get("/documents/{document_id}/file")
def download_document_file(document_id: int, db: Session = Depends(get_db)) -> FileResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Файл ёфт нашуд.")

    stored_path = Path(document.stored_path)
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Файли аслӣ ёфт нашуд.")

    media_type = "application/octet-stream"
    if document.file_type == ".pdf":
        media_type = "application/pdf"
    elif document.file_type == ".docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return FileResponse(str(stored_path), filename=document.filename, media_type=media_type)


@app.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)) -> dict[str, int | str]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Файл ёфт нашуд.")

    stored_path = document.stored_path
    db.delete(document)
    db.commit()

    if stored_path:
        try:
            Path(stored_path).unlink(missing_ok=True)
        except Exception:
            pass

    return {"status": "deleted", "id": document_id}


@app.get("/search")
def search(
    query: str = Query(..., min_length=1),
    target: str = Query("phrase", pattern="^(word|sentence|paragraph|phrase)$"),
    exact: bool = Query(False),
    mode: str | None = Query(None, pattern="^(exact|partial)$"),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
) -> dict:
    if target == "word":
        results = search_word(db, query, exact=exact, mode=mode, document_id=document_id)
    elif target == "sentence":
        results = search_sentence(db, query, document_id=document_id)
    elif target == "paragraph":
        results = search_paragraph(db, query, document_id=document_id)
    else:
        results = search_phrase(db, query, document_id=document_id)

    return {"query": query, "target": target, "total": len(results), "results": results}


@app.get("/search/word")
def api_search_word(
    query: str = Query(..., min_length=1),
    exact: bool = Query(False),
    mode: str | None = Query(None, pattern="^(exact|partial)$"),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
) -> dict:
    results = search_word(db, query, exact=exact, mode=mode, document_id=document_id)
    return {"query": query, "total": len(results), "results": results}


@app.get("/search/sentence")
def api_search_sentence(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
) -> dict:
    results = search_sentence(db, query, document_id=document_id)
    return {"query": query, "total": len(results), "results": results}


@app.get("/search/paragraph")
def api_search_paragraph(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
) -> dict:
    results = search_paragraph(db, query, document_id=document_id)
    return {"query": query, "total": len(results), "results": results}


@app.get("/search/phrase")
def api_search_phrase(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
) -> dict:
    results = search_phrase(db, query, document_id=document_id)
    return {"query": query, "total": len(results), "results": results}


@app.get("/tools/wordlist")
def tool_wordlist(
    document_id: int | None = Query(None, gt=0),
    min_freq: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=2000),
    sort: str = Query("freq", pattern="^(freq|alpha)$"),
    db: Session = Depends(get_db),
) -> dict:
    word_col = func.lower(Word.word).label("word")
    count_col = func.count(Word.id).label("count")
    statement = select(word_col, count_col)
    if document_id is not None:
        statement = statement.where(Word.document_id == document_id)
    statement = statement.group_by(word_col).having(func.count(Word.id) >= min_freq)
    if sort == "alpha":
        statement = statement.order_by(word_col.asc())
    else:
        statement = statement.order_by(count_col.desc(), word_col.asc())
    rows = db.execute(statement.limit(limit)).all()
    items = [{"word": word, "count": int(count)} for word, count in rows]
    return {
        "document_id": document_id,
        "min_freq": min_freq,
        "limit": limit,
        "sort": sort,
        "items": items,
        "shown": len(items),
    }


@app.get("/tools/concordance")
def tool_concordance(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    mode: str = Query("partial", pattern="^(exact|partial)$"),
    window: int = Query(5, ge=1, le=25),
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> dict:
    normalized = query.strip()
    if not normalized:
        return {"query": query, "total": 0, "items": []}

    q = normalized.lower()
    if mode == "exact":
        condition = func.lower(Word.word) == q
    else:
        condition = func.lower(Word.word).like(f"%{q}%")

    hit_stmt = (
        select(
            Word.sentence_id,
            Word.word_index,
            Word.word,
            Document.id.label("document_id"),
            Document.filename,
            Paragraph.paragraph_index,
            Sentence.sentence_index,
        )
        .join(Sentence, Sentence.id == Word.sentence_id)
        .join(Paragraph, Paragraph.id == Sentence.paragraph_id)
        .join(Document, Document.id == Word.document_id)
        .where(condition)
        .order_by(Document.filename, Paragraph.paragraph_index, Sentence.sentence_index, Word.word_index)
        .limit(limit)
    )
    if document_id is not None:
        hit_stmt = hit_stmt.where(Word.document_id == document_id)

    hits = db.execute(hit_stmt).all()
    if not hits:
        return {"query": query, "mode": mode, "total": 0, "items": []}

    sentence_ids = sorted({row.sentence_id for row in hits})
    words_stmt = (
        select(Word.sentence_id, Word.word_index, Word.word)
        .where(Word.sentence_id.in_(sentence_ids))
        .order_by(Word.sentence_id, Word.word_index)
    )
    words_rows = db.execute(words_stmt).all()

    words_by_sentence: dict[int, list[tuple[int, str]]] = defaultdict(list)
    pos_by_sentence: dict[int, dict[int, int]] = defaultdict(dict)
    for sentence_id, word_index, word in words_rows:
        pos_by_sentence[int(sentence_id)][int(word_index)] = len(words_by_sentence[int(sentence_id)])
        words_by_sentence[int(sentence_id)].append((int(word_index), word))

    items: list[dict] = []
    for row in hits:
        sentence_id = int(row.sentence_id)
        word_index = int(row.word_index)
        words = words_by_sentence.get(sentence_id, [])
        pos = pos_by_sentence.get(sentence_id, {}).get(word_index)
        if pos is None:
            continue
        left = " ".join(w for _, w in words[max(0, pos - window) : pos])
        right = " ".join(w for _, w in words[pos + 1 : pos + 1 + window])
        items.append(
            {
                "document_id": int(row.document_id),
                "filename": row.filename,
                "paragraph_index": int(row.paragraph_index) if row.paragraph_index is not None else None,
                "sentence_index": int(row.sentence_index) if row.sentence_index is not None else None,
                "left": left,
                "match": row.word,
                "right": right,
            }
        )

    return {
        "query": query,
        "mode": mode,
        "window": window,
        "limit": limit,
        "document_id": document_id,
        "total": len(items),
        "items": items,
    }


@app.get("/tools/ngrams")
def tool_ngrams(
    n: int = Query(2, ge=2, le=5),
    document_id: int | None = Query(None, gt=0),
    min_freq: int = Query(2, ge=1),
    limit: int = Query(100, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Word.sentence_id, Word.word_index, Word.word)
    if document_id is not None:
        stmt = stmt.where(Word.document_id == document_id)
    stmt = stmt.order_by(Word.sentence_id, Word.word_index)
    rows = db.execute(stmt).all()

    counts: Counter[tuple[str, ...]] = Counter()
    current_sentence = None
    buffer: list[str] = []

    def flush_sentence() -> None:
        if len(buffer) < n:
            return
        for i in range(0, len(buffer) - n + 1):
            counts[tuple(buffer[i : i + n])] += 1

    for sentence_id, _, word in rows:
        if current_sentence is None:
            current_sentence = sentence_id
        if sentence_id != current_sentence:
            flush_sentence()
            buffer = []
            current_sentence = sentence_id
        token = (word or "").strip().lower()
        if token:
            buffer.append(token)
    flush_sentence()

    items = [
        {"ngram": " ".join(key), "count": int(count)}
        for key, count in counts.most_common()
        if count >= min_freq
    ][:limit]

    return {
        "n": n,
        "document_id": document_id,
        "min_freq": min_freq,
        "limit": limit,
        "shown": len(items),
        "items": items,
    }
