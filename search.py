from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import Document, Paragraph, Sentence, Word


def _result_row(
    document_id: int,
    text: str,
    paragraph_index: int | None,
    sentence_index: int | None,
) -> dict[str, int | str | None]:
    return {
        "document_id": document_id,
        "text": text,
        "paragraph_index": paragraph_index,
        "sentence_index": sentence_index,
    }


def search_word(db: Session, query: str, exact: bool = False) -> list[dict[str, int | str | None]]:
    normalized = query.strip()
    if not normalized:
        return []

    if exact:
        condition = func.lower(Word.word) == normalized.lower()
        match_type = "word_exact"
    else:
        condition = Word.word.ilike(f"%{normalized}%")
        match_type = "word_partial"

    statement = (
        select(Document.id, Word.word, Paragraph.paragraph_index, Sentence.sentence_index)
        .join(Word, Word.document_id == Document.id)
        .join(Sentence, Sentence.id == Word.sentence_id)
        .join(Paragraph, Paragraph.id == Sentence.paragraph_id)
        .where(condition)
        .order_by(Document.filename, Paragraph.paragraph_index, Sentence.sentence_index, Word.word_index)
    )
    rows = db.execute(statement).all()
    return [
        _result_row(document_id, word, paragraph_index, sentence_index)
        for document_id, word, paragraph_index, sentence_index in rows
    ]


def search_sentence(db: Session, query: str) -> list[dict[str, int | str | None]]:
    normalized = query.strip()
    if not normalized:
        return []

    statement = (
        select(Document.id, Sentence.text, Paragraph.paragraph_index, Sentence.sentence_index)
        .join(Sentence, Sentence.document_id == Document.id)
        .join(Paragraph, Paragraph.id == Sentence.paragraph_id)
        .where(Sentence.text.ilike(f"%{normalized}%"))
        .order_by(Document.filename, Paragraph.paragraph_index, Sentence.sentence_index)
    )
    rows = db.execute(statement).all()
    return [
        _result_row(document_id, text, paragraph_index, sentence_index)
        for document_id, text, paragraph_index, sentence_index in rows
    ]


def search_paragraph(db: Session, query: str) -> list[dict[str, int | str | None]]:
    normalized = query.strip()
    if not normalized:
        return []

    statement = (
        select(Document.id, Paragraph.text, Paragraph.paragraph_index)
        .join(Paragraph, Paragraph.document_id == Document.id)
        .where(Paragraph.text.ilike(f"%{normalized}%"))
        .order_by(Document.filename, Paragraph.paragraph_index)
    )
    rows = db.execute(statement).all()
    return [
        _result_row(document_id, text, paragraph_index, None)
        for document_id, text, paragraph_index in rows
    ]


def search_phrase(db: Session, query: str) -> list[dict[str, int | str | None]]:
    normalized = query.strip()
    if not normalized:
        return []

    results: list[dict[str, int | str | None]] = []

    for item in search_sentence(db, normalized):
        results.append(item)

    for item in search_paragraph(db, normalized):
        results.append(item)

    return results
