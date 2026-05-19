from .base import BaseSearchService
from .paragraph import ParagraphSearchService
from .sentence import SentenceSearchService


class PhraseSearchService(BaseSearchService):
    def search(
        self,
        *,
        query: str,
        document_id: int | None = None,
    ) -> list[dict[str, int | str | None]]:
        normalized = (query or "").strip()
        if not normalized:
            return []

        results: list[dict[str, int | str | None]] = []
        results.extend(SentenceSearchService(self._db).search(query=normalized, document_id=document_id))
        results.extend(ParagraphSearchService(self._db).search(query=normalized, document_id=document_id))
        return results

