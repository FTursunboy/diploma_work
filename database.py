from collections.abc import Generator
from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
DB_DIR = STORAGE_DIR / "db"
DATABASE_PATH = DB_DIR / "books.db"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DATABASE_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="uploaded", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
