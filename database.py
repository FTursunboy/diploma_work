from collections.abc import Generator
from datetime import datetime
from pathlib import Path
import os

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, func, inspect, select, text
from sqlalchemy.dialects import mysql as mysql_dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
DB_DIR = STORAGE_DIR / "db"
DATABASE_PATH = DB_DIR / "books.db"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL")

# If DATABASE_URL is set (for example, postgres via docker), use it.
# Otherwise, fallback to local SQLite file used before.
if DATABASE_URL:
    # Use the provided URL (container will install psycopg2-binary)
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
else:
    engine = create_engine(f"sqlite:///{DATABASE_PATH}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    bibliography: Mapped[str | None] = mapped_column(
        Text().with_variant(mysql_dialect.MEDIUMTEXT(), "mysql"),
        nullable=True,
    )
    # full_text can be very large; use MEDIUMTEXT on MySQL to avoid "Data too long" errors
    full_text: Mapped[str | None] = mapped_column(
        Text().with_variant(mysql_dialect.MEDIUMTEXT(), "mysql"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="uploaded", nullable=False)
    error_message: Mapped[str | None] = mapped_column(
        Text().with_variant(mysql_dialect.MEDIUMTEXT(), "mysql"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    paragraphs: Mapped[list["Paragraph"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Paragraph.paragraph_index",
    )
    sentences: Mapped[list["Sentence"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by=lambda: (Sentence.paragraph_id, Sentence.sentence_index),
    )
    words: Mapped[list["Word"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Word.word_index",
    )


class Paragraph(Base):
    __tablename__ = "paragraphs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="paragraphs")
    sentences: Mapped[list["Sentence"]] = relationship(
        back_populates="paragraph",
        cascade="all, delete-orphan",
        order_by="Sentence.sentence_index",
    )


class Sentence(Base):
    __tablename__ = "sentences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    paragraph_id: Mapped[int] = mapped_column(ForeignKey("paragraphs.id"), nullable=False, index=True)
    sentence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="sentences")
    paragraph: Mapped["Paragraph"] = relationship(back_populates="sentences")
    words: Mapped[list["Word"]] = relationship(
        back_populates="sentence",
        cascade="all, delete-orphan",
        order_by="Word.word_index",
    )


class Word(Base):
    __tablename__ = "words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    sentence_id: Mapped[int] = mapped_column(ForeignKey("sentences.id"), nullable=False, index=True)
    word_index: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    document: Mapped["Document"] = relationship(back_populates="words")
    sentence: Mapped["Sentence"] = relationship(back_populates="words")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_document_columns()
    _ensure_user_columns()
    _seed_admin_user()


def _ensure_document_columns() -> None:
    """Lightweight migration for additive columns (no Alembic in this repo)."""
    inspector = inspect(engine)
    try:
        cols = {c["name"] for c in inspector.get_columns("documents")}
    except Exception:
        return

    missing = []
    for name in ("title", "author", "publisher", "publication_year", "doc_type", "bibliography"):
        if name not in cols:
            missing.append(name)

    if not missing:
        return

    ddl_by_col = {
        "title": "ALTER TABLE documents ADD COLUMN title VARCHAR(255) NULL",
        "author": "ALTER TABLE documents ADD COLUMN author VARCHAR(255) NULL",
        "publisher": "ALTER TABLE documents ADD COLUMN publisher VARCHAR(255) NULL",
        "publication_year": "ALTER TABLE documents ADD COLUMN publication_year INTEGER NULL",
        "doc_type": "ALTER TABLE documents ADD COLUMN doc_type VARCHAR(80) NULL",
        "bibliography": "ALTER TABLE documents ADD COLUMN bibliography TEXT NULL",
    }

    with engine.begin() as conn:
        for col in missing:
            stmt = ddl_by_col.get(col)
            if not stmt:
                continue
            conn.execute(text(stmt))


def _ensure_user_columns() -> None:
    inspector = inspect(engine)
    try:
        cols = {c["name"] for c in inspector.get_columns("users")}
    except Exception:
        return

    if "email" in cols:
        return

    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255) NULL"))
        except Exception:
            return

        # Best-effort index/constraint (varies by DB).
        try:
            conn.execute(text("CREATE INDEX ix_users_email ON users (email)"))
        except Exception:
            pass


def _seed_admin_user() -> None:
    seed = (os.getenv("AUTH_SEED_ADMIN", "1") or "").strip().lower()
    if seed in {"0", "false", "no", "off"}:
        return

    admin_email = (os.getenv("ADMIN_EMAIL", "admin@local") or "").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "admin12345") or ""
    reset_pwd = (os.getenv("AUTH_SEED_ADMIN_RESET_PASSWORD", "0") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if not admin_email:
        return

    try:
        from auth import hash_password
    except Exception:
        return

    db = SessionLocal()
    try:
        has_admin = db.scalar(select(func.count(User.id)).where(User.role == "admin"))
        if int(has_admin or 0) > 0:
            return

        user = db.scalar(select(User).where((User.email == admin_email) | (User.username == admin_email)))
        if user is None:
            user = User(
                username=admin_email,
                email=admin_email,
                password_hash=hash_password(admin_password),
                role="admin",
            )
            db.add(user)
            db.commit()
            return

        user.role = "admin"
        if reset_pwd:
            user.password_hash = hash_password(admin_password)
        db.add(user)
        db.commit()
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
