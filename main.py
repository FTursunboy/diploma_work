from pathlib import Path

from collections import Counter, defaultdict

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import re

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from auth import (
    ALL_ROLES,
    AuthError,
    ROLE_ADMIN,
    ROLE_MODERATOR,
    ROLE_USER,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from database import Document, Paragraph, Sentence, User, Word, get_db, init_db
from parser import create_uploaded_document, load_document_from_path, parse_document, save_upload_file
from search import search_paragraph, search_phrase, search_sentence, search_word


init_db()
app = FastAPI(title="Book Parser API")

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

auth_scheme = HTTPBearer(auto_error=False)


def serve_web_page(filename: str) -> FileResponse:
    path = WEB_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Страница не найдена.")
    return FileResponse(str(path), media_type="text/html")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=401, detail="Не авторизован.")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload.get("sub") or 0)
    except (AuthError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=str(exc) or "Не авторизован.") from exc

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден.")
    return user


def require_roles(*roles: str):
    allowed = set(roles)

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Недостаточно прав.")
        return user

    return _dep


require_moderator = require_roles(ROLE_MODERATOR, ROLE_ADMIN)
require_admin = require_roles(ROLE_ADMIN)


class FilePathRequest(BaseModel):
    file_path: str
    title: str | None = None
    author: str | None = None
    publisher: str | None = None
    publication_year: int | None = None
    doc_type: str | None = None
    bibliography: str | None = None


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RoleUpdateRequest(BaseModel):
    role: str


@app.get("/login", include_in_schema=False)
def login_page():
    return serve_web_page("login.html")


@app.get("/register", include_in_schema=False)
def register_page():
    return serve_web_page("register.html")


@app.get("/viewer", include_in_schema=False)
def viewer_page():
    return serve_web_page("viewer.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return serve_web_page("admin.html")


@app.get("/", include_in_schema=False)
def root(request: Request):
    accept = request.headers.get("accept", "")
    index_file = WEB_DIR / "index.html"
    if "text/html" in accept and index_file.exists():
        return FileResponse(str(index_file), media_type="text/html")
    return {"message": "Book Parser API is running"}


@app.post("/auth/register")
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    email = (payload.email or "").strip().lower()
    if len(email) > 255:
        raise HTTPException(status_code=400, detail="E-mail слишком длинный.")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="Некорректный e-mail.")

    existing = db.scalar(select(User).where((User.email == email) | (User.username == email)))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Пользователь с таким e-mail уже существует.")

    # Bootstrap: the first registered user becomes admin.
    users_count = db.scalar(select(func.count(User.id)))
    role = ROLE_ADMIN if int(users_count or 0) == 0 else ROLE_USER

    try:
        pwd_hash = hash_password(payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = User(username=email, email=email, password_hash=pwd_hash, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user_id=user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email or user.username,
            "role": user.role,
            "created_at": user.created_at,
        },
    }


@app.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    email = (payload.email or "").strip().lower()
    user = db.scalar(select(User).where((User.email == email) | (User.username == email)))
    if user is None or not verify_password(payload.password or "", user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный e-mail или пароль.")

    token = create_access_token(user_id=user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email or user.username,
            "role": user.role,
            "created_at": user.created_at,
        },
    }


@app.get("/auth/me")
def me(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "id": current_user.id,
        "email": current_user.email or current_user.username,
        "role": current_user.role,
        "created_at": current_user.created_at,
    }


@app.get("/admin/users")
def admin_list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[dict]:
    users = db.scalars(select(User).order_by(User.created_at.desc(), User.id.desc())).all()
    return [
        {"id": u.id, "email": u.email or u.username, "role": u.role, "created_at": u.created_at} for u in users
    ]


@app.put("/admin/users/{user_id}/role")
def admin_set_user_role(
    user_id: int,
    payload: RoleUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    role = (payload.role or "").strip().lower()
    if role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail=f"Недопустимая роль. Доступно: {', '.join(sorted(ALL_ROLES))}.")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")

    user.role = role
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email or user.username, "role": user.role, "created_at": user.created_at}


@app.post("/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    author: str | None = Form(None),
    doc_type: str | None = Form(None),
    publication_year: int | None = Form(None),
    publisher: str | None = Form(None),
    bibliography: str | None = Form(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Номи файл ҳатмист.")

    try:
        file_type, stored_path = save_upload_file(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document = create_uploaded_document(
        db,
        file.filename,
        file_type,
        stored_path,
        title=(title or "").strip() or None,
        author=(author or "").strip() or None,
        publisher=(publisher or "").strip() or None,
        publication_year=publication_year,
        doc_type=(doc_type or "").strip() or None,
        bibliography=(bibliography or "").strip() or None,
    )
    counts = parse_document(db, document)
    db.refresh(document)

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
        "status": document.status,
        "full_text": document.full_text,
        "error_message": document.error_message,
        "paragraphs_count": counts["paragraphs"],
        "sentences_count": counts["sentences"],
        "words_count": counts["words"],
    }


@app.post("/documents/from-path")
def upload_document_from_path(
    payload: FilePathRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_moderator),
) -> dict:
    try:
        document, counts = load_document_from_path(
            db,
            payload.file_path,
            title=(payload.title or "").strip() or None,
            author=(payload.author or "").strip() or None,
            publisher=(payload.publisher or "").strip() or None,
            publication_year=payload.publication_year,
            doc_type=(payload.doc_type or "").strip() or None,
            bibliography=(payload.bibliography or "").strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        "status": document.status,
        "full_text": document.full_text,
        "error_message": document.error_message,
        "paragraphs_count": counts["paragraphs"],
        "sentences_count": counts["sentences"],
        "words_count": counts["words"],
    }


@app.get("/documents")
def list_documents(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[dict]:
    documents = db.scalars(select(Document).order_by(Document.created_at.desc())).all()
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
            "status": document.status,
            "full_text": document.full_text,
            "error_message": document.error_message,
        }
        for document in documents
    ]


@app.get("/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
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
        "title": document.title,
        "author": document.author,
        "publisher": document.publisher,
        "publication_year": document.publication_year,
        "doc_type": document.doc_type,
        "bibliography": document.bibliography,
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
def download_document_file(
    document_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> FileResponse:
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
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict[str, int | str]:
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
    _: User = Depends(get_current_user),
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
    _: User = Depends(get_current_user),
) -> dict:
    results = search_word(db, query, exact=exact, mode=mode, document_id=document_id)
    return {"query": query, "total": len(results), "results": results}


@app.get("/search/sentence")
def api_search_sentence(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    results = search_sentence(db, query, document_id=document_id)
    return {"query": query, "total": len(results), "results": results}


@app.get("/search/paragraph")
def api_search_paragraph(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    results = search_paragraph(db, query, document_id=document_id)
    return {"query": query, "total": len(results), "results": results}


@app.get("/search/phrase")
def api_search_phrase(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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
    _: User = Depends(get_current_user),
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
    _: User = Depends(get_current_user),
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
    _: User = Depends(get_current_user),
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


@app.get("/tools/ngram-search")
def tool_ngram_search(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    mode: str = Query("exact", pattern="^(exact|partial)$"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    normalized = " ".join((query or "").strip().split())
    if not normalized:
        return {"query": query, "n": 0, "document_id": document_id, "mode": mode, "total": 0, "items": []}

    tokens = [t.strip().lower() for t in normalized.split(" ") if t.strip()]
    if len(tokens) < 2:
        raise HTTPException(status_code=400, detail="Введите минимум 2 слова для поиска n-gram.")
    if len(tokens) > 5:
        raise HTTPException(status_code=400, detail="Максимум 5 слов (n<=5).")

    n = len(tokens)

    stmt = select(Word.document_id, Word.sentence_id, Word.word_index, Word.word)
    if document_id is not None:
        stmt = stmt.where(Word.document_id == document_id)
    stmt = stmt.order_by(Word.document_id, Word.sentence_id, Word.word_index)
    rows = db.execute(stmt).all()

    counts_by_doc: dict[int, int] = defaultdict(int)
    total = 0

    current_doc = None
    current_sentence = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal total
        if not buffer:
            return
        if len(buffer) < n:
            return

        if mode == "partial":
            for i in range(0, len(buffer) - n + 1):
                ok = True
                for j in range(n):
                    if tokens[j] not in buffer[i + j]:
                        ok = False
                        break
                if ok and current_doc is not None:
                    counts_by_doc[int(current_doc)] += 1
                    total += 1
        else:
            target = tuple(tokens)
            for i in range(0, len(buffer) - n + 1):
                if tuple(buffer[i : i + n]) == target and current_doc is not None:
                    counts_by_doc[int(current_doc)] += 1
                    total += 1

    for doc_id, sentence_id, _, word in rows:
        if current_doc is None:
            current_doc = int(doc_id)
            current_sentence = int(sentence_id)

        if int(doc_id) != int(current_doc) or int(sentence_id) != int(current_sentence):
            flush()
            buffer = []
            current_doc = int(doc_id)
            current_sentence = int(sentence_id)

        token = (word or "").strip().lower()
        if token:
            buffer.append(token)

    flush()

    if not counts_by_doc:
        return {
            "query": normalized,
            "n": n,
            "document_id": document_id,
            "mode": mode,
            "total": 0,
            "items": [],
        }

    doc_ids = sorted(counts_by_doc.keys())
    docs = db.execute(select(Document.id, Document.filename, Document.title).where(Document.id.in_(doc_ids))).all()
    doc_meta = {int(did): {"filename": fn, "title": title} for did, fn, title in docs}

    items = [
        {
            "document_id": did,
            "filename": doc_meta.get(did, {}).get("filename"),
            "title": doc_meta.get(did, {}).get("title"),
            "count": int(counts_by_doc[did]),
        }
        for did in doc_ids
    ]
    items.sort(key=lambda x: (-int(x["count"]), str(x.get("title") or x.get("filename") or "")))
    items = items[:limit]

    return {
        "query": normalized,
        "n": n,
        "document_id": document_id,
        "mode": mode,
        "total": int(total),
        "items": items,
        "shown": len(items),
    }
