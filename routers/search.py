from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from routers.dependencies import get_current_user
from routers.schemas import SemanticSearchRequest
from services.search import ParagraphSearchService, PhraseSearchService, SentenceSearchService, WordSearchService
from services.vector_search_service import VectorSearchService


router = APIRouter()


@router.get("/search")
def search(
    query: str = Query(..., min_length=1),
    target: str = Query("phrase", pattern="^(word|sentence|paragraph|phrase|semantic)$"),
    exact: bool = Query(False),
    mode: str | None = Query(None, pattern="^(exact|partial)$"),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    if target == "word":
        results = WordSearchService(db).search(query=query, exact=exact, mode=mode, document_id=document_id)
    elif target == "sentence":
        results = SentenceSearchService(db).search(query=query, document_id=document_id)
    elif target == "paragraph":
        results = ParagraphSearchService(db).search(query=query, document_id=document_id)
    elif target == "semantic":
        try:
            semantic_results = VectorSearchService(db).search(
                query=query,
                document_id=document_id,
                limit=10,
                user_id=current_user.id,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Semantic search unavailable: {exc}") from exc
        return {"query": query, "target": target, "total": len(semantic_results), "results": semantic_results}
    else:
        results = PhraseSearchService(db).search(query=query, document_id=document_id)

    return {"query": query, "target": target, "total": len(results), "results": results}


@router.get("/search/word")
def api_search_word(
    query: str = Query(..., min_length=1),
    exact: bool = Query(False),
    mode: str | None = Query(None, pattern="^(exact|partial)$"),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> dict:
    results = WordSearchService(db).search(query=query, exact=exact, mode=mode, document_id=document_id)
    return {"query": query, "total": len(results), "results": results}


@router.get("/search/sentence")
def api_search_sentence(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> dict:
    results = SentenceSearchService(db).search(query=query, document_id=document_id)
    return {"query": query, "total": len(results), "results": results}


@router.get("/search/paragraph")
def api_search_paragraph(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> dict:
    results = ParagraphSearchService(db).search(query=query, document_id=document_id)
    return {"query": query, "total": len(results), "results": results}


@router.get("/search/phrase")
def api_search_phrase(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> dict:
    results = PhraseSearchService(db).search(query=query, document_id=document_id)
    return {"query": query, "total": len(results), "results": results}


@router.post("/search/semantic")
def api_search_semantic(
    payload: SemanticSearchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    limit = min(50, max(1, int(payload.limit or 10)))
    document_id = payload.document_id if payload.document_id and payload.document_id > 0 else None
    try:
        return VectorSearchService(db).search(
            query=payload.query,
            document_id=document_id,
            limit=limit,
            user_id=current_user.id,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Semantic search unavailable: {exc}") from exc
