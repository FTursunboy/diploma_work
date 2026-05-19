from sqlalchemy.orm import Session

from services.search import ParagraphSearchService, PhraseSearchService, SentenceSearchService, WordSearchService
from services.vector_search_service import VectorSearchService


def search_word(
    db: Session,
    query: str,
    exact: bool = False,
    mode: str | None = None,
    document_id: int | None = None,
) -> list[dict[str, int | str | None]]:
    return WordSearchService(db).search(query=query, exact=exact, mode=mode, document_id=document_id)


def search_sentence(
    db: Session,
    query: str,
    document_id: int | None = None,
) -> list[dict[str, int | str | None]]:
    return SentenceSearchService(db).search(query=query, document_id=document_id)


def search_paragraph(
    db: Session,
    query: str,
    document_id: int | None = None,
) -> list[dict[str, int | str | None]]:
    return ParagraphSearchService(db).search(query=query, document_id=document_id)


def search_phrase(
    db: Session,
    query: str,
    document_id: int | None = None,
) -> list[dict[str, int | str | None]]:
    return PhraseSearchService(db).search(query=query, document_id=document_id)


def search_semantic(
    db: Session,
    query: str,
    document_id: int | None = None,
    limit: int = 10,
) -> list[dict[str, int | float | str | None]]:
    return VectorSearchService(db).search(query=query, document_id=document_id, limit=limit)
