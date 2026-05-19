from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from routers.dependencies import get_current_user
from services.tools_service import ConcordanceService, NgramSearchService, NgramsService, WordlistService


router = APIRouter()


@router.get("/tools/wordlist")
def tool_wordlist(
    document_id: int | None = Query(None, gt=0),
    min_freq: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=2000),
    sort: str = Query("freq", pattern="^(freq|alpha)$"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> dict:
    return WordlistService(db).wordlist(document_id=document_id, min_freq=min_freq, limit=limit, sort=sort)


@router.get("/tools/concordance")
def tool_concordance(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    mode: str = Query("partial", pattern="^(exact|partial)$"),
    window: int = Query(5, ge=1, le=25),
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> dict:
    return ConcordanceService(db).concordance(
        query=query,
        document_id=document_id,
        mode=mode,
        window=window,
        limit=limit,
    )


@router.get("/tools/ngrams")
def tool_ngrams(
    n: int = Query(2, ge=2, le=5),
    document_id: int | None = Query(None, gt=0),
    min_freq: int = Query(2, ge=1),
    limit: int = Query(100, ge=1, le=2000),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> dict:
    return NgramsService(db).ngrams(n=n, document_id=document_id, min_freq=min_freq, limit=limit)


@router.get("/tools/ngram-search")
def tool_ngram_search(
    query: str = Query(..., min_length=1),
    document_id: int | None = Query(None, gt=0),
    mode: str = Query("exact", pattern="^(exact|partial)$"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> dict:
    return NgramSearchService(db).search(query=query, document_id=document_id, mode=mode, limit=limit)

