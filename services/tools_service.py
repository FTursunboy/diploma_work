import hashlib
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import Document, DocumentNgram, Paragraph, Sentence, Word
from splitter import split_words


def _ngram_hash(ngram: str) -> str:
    return hashlib.sha256(ngram.encode("utf-8")).hexdigest()


class WordlistService:
    def __init__(self, db: Session):
        self._db = db

    def wordlist(
        self,
        *,
        document_id: int | None,
        min_freq: int,
        limit: int,
        sort: str,
    ) -> dict:
        word_col = func.lower(Word.word).label("word")
        count_col = func.count(Word.id).label("count")
        statement = select(word_col, count_col).join(Document, Document.id == Word.document_id)
        statement = statement.where(Document.deleted_at.is_(None))
        if document_id is not None:
            statement = statement.where(Word.document_id == document_id)
        statement = statement.group_by(word_col).having(func.count(Word.id) >= min_freq)
        if sort == "alpha":
            statement = statement.order_by(word_col.asc())
        else:
            statement = statement.order_by(count_col.desc(), word_col.asc())
        rows = self._db.execute(statement.limit(limit)).all()
        items = [{"word": word, "count": int(count)} for word, count in rows]
        return {
            "document_id": document_id,
            "min_freq": min_freq,
            "limit": limit,
            "sort": sort,
            "items": items,
            "shown": len(items),
        }


class ConcordanceService:
    def __init__(self, db: Session):
        self._db = db

    def concordance(
        self,
        *,
        query: str,
        document_id: int | None,
        mode: str,
        window: int,
        limit: int,
    ) -> dict:
        normalized = (query or "").strip()
        if not normalized:
            return {"query": query, "total": 0, "items": []}

        query_tokens = [(token or "").strip().lower() for token in split_words(normalized) if (token or "").strip()]
        if not query_tokens:
            return {"query": query, "mode": mode, "total": 0, "items": []}

        first_token = query_tokens[0]
        if mode == "exact":
            condition = func.lower(Word.word) == first_token
        else:
            condition = func.lower(Word.word).like(f"%{first_token}%")

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
            .where(Document.deleted_at.is_(None), condition)
            .order_by(Document.filename, Paragraph.paragraph_index, Sentence.sentence_index, Word.word_index)
        )
        if document_id is not None:
            hit_stmt = hit_stmt.where(Word.document_id == document_id)

        hits = self._db.execute(hit_stmt).all()
        if not hits:
            return {"query": query, "mode": mode, "total": 0, "items": []}

        sentence_ids = sorted({int(row.sentence_id) for row in hits})
        words_stmt = (
            select(Word.sentence_id, Word.word_index, Word.word)
            .where(Word.sentence_id.in_(sentence_ids))
            .order_by(Word.sentence_id, Word.word_index)
        )
        words_rows = self._db.execute(words_stmt).all()

        words_by_sentence: dict[int, list[tuple[int, str]]] = defaultdict(list)
        pos_by_sentence: dict[int, dict[int, int]] = defaultdict(dict)
        for sentence_id, word_index, word in words_rows:
            sid = int(sentence_id)
            widx = int(word_index)
            pos_by_sentence[sid][widx] = len(words_by_sentence[sid])
            words_by_sentence[sid].append((widx, word))

        items: list[dict] = []
        for row in hits:
            if len(items) >= limit:
                break
            sentence_id = int(row.sentence_id)
            word_index = int(row.word_index)
            words = words_by_sentence.get(sentence_id, [])
            pos = pos_by_sentence.get(sentence_id, {}).get(word_index)
            if pos is None:
                continue

            end_pos = pos + len(query_tokens)
            if end_pos > len(words):
                continue

            candidate_words = [str(word or "") for _, word in words[pos:end_pos]]
            candidate_tokens = [word.strip().lower() for word in candidate_words]
            if mode == "exact":
                matched = candidate_tokens == query_tokens
            else:
                matched = all(query_tokens[index] in candidate_tokens[index] for index in range(len(query_tokens)))
            if not matched:
                continue

            left = " ".join(w for _, w in words[max(0, pos - window) : pos])
            match = " ".join(candidate_words)
            right = " ".join(w for _, w in words[end_pos : end_pos + window])
            items.append(
                {
                    "document_id": int(row.document_id),
                    "filename": row.filename,
                    "paragraph_index": int(row.paragraph_index) if row.paragraph_index is not None else None,
                    "sentence_index": int(row.sentence_index) if row.sentence_index is not None else None,
                    "left": left,
                    "match": match,
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


class NgramsService:
    def __init__(self, db: Session):
        self._db = db

    def ngrams(
        self,
        *,
        n: int,
        document_id: int | None,
        min_freq: int,
        limit: int,
    ) -> dict:
        self.ensure_materialized(document_id=document_id)

        if document_id is not None:
            stmt = (
                select(DocumentNgram.ngram, DocumentNgram.count)
                .join(Document, Document.id == DocumentNgram.document_id)
                .where(
                    Document.deleted_at.is_(None),
                    DocumentNgram.document_id == document_id,
                    DocumentNgram.n == n,
                    DocumentNgram.count >= min_freq,
                )
                .order_by(DocumentNgram.count.desc(), DocumentNgram.ngram.asc())
                .limit(limit)
            )
            rows = self._db.execute(stmt).all()
            items = [{"ngram": ngram, "count": int(count)} for ngram, count in rows]
        else:
            count_col = func.sum(DocumentNgram.count).label("count")
            stmt = (
                select(DocumentNgram.ngram, count_col)
                .join(Document, Document.id == DocumentNgram.document_id)
                .where(Document.deleted_at.is_(None), DocumentNgram.n == n)
                .group_by(DocumentNgram.ngram)
                .having(count_col >= min_freq)
                .order_by(count_col.desc(), DocumentNgram.ngram.asc())
                .limit(limit)
            )
            rows = self._db.execute(stmt).all()
            items = [{"ngram": ngram, "count": int(count)} for ngram, count in rows]

        return {
            "n": n,
            "document_id": document_id,
            "min_freq": min_freq,
            "limit": limit,
            "shown": len(items),
            "items": items,
        }

    def ensure_materialized(self, *, document_id: int | None) -> None:
        if document_id is not None:
            ngram_count = self._db.scalar(
                select(func.count(DocumentNgram.id))
                .join(Document, Document.id == DocumentNgram.document_id)
                .where(Document.deleted_at.is_(None), DocumentNgram.document_id == document_id)
            )
            if int(ngram_count or 0) > 0:
                return

            word_count = self._db.scalar(
                select(func.count(Word.id))
                .join(Document, Document.id == Word.document_id)
                .where(Document.deleted_at.is_(None), Word.document_id == document_id)
            )
            if int(word_count or 0) > 0:
                self.rebuild_for_document(document_id=document_id)
            return

        word_doc_ids = set(
            self._db.scalars(
                select(Word.document_id)
                .join(Document, Document.id == Word.document_id)
                .where(Document.deleted_at.is_(None))
                .group_by(Word.document_id)
            ).all()
        )
        ngram_doc_ids = set(
            self._db.scalars(
                select(DocumentNgram.document_id)
                .join(Document, Document.id == DocumentNgram.document_id)
                .where(Document.deleted_at.is_(None))
                .group_by(DocumentNgram.document_id)
            ).all()
        )
        for missing_document_id in sorted(word_doc_ids - ngram_doc_ids):
            self.rebuild_for_document(document_id=int(missing_document_id))

    def rebuild_for_document(self, *, document_id: int) -> int:
        stmt = (
            select(Word.sentence_id, Word.word_index, Word.word)
            .join(Document, Document.id == Word.document_id)
            .where(Document.deleted_at.is_(None), Word.document_id == document_id)
        )
        stmt = stmt.order_by(Word.sentence_id, Word.word_index)
        rows = self._db.execute(stmt).all()

        counts: defaultdict[tuple[int, str], int] = defaultdict(int)
        current_sentence = None
        buffer: list[str] = []

        def flush_sentence() -> None:
            if len(buffer) < 2:
                return
            for size in range(2, 6):
                if len(buffer) < size:
                    continue
                for index in range(0, len(buffer) - size + 1):
                    ngram = " ".join(buffer[index : index + size])
                    counts[(size, ngram)] += 1

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

        self._db.query(DocumentNgram).filter(DocumentNgram.document_id == document_id).delete()
        for (size, ngram), count in counts.items():
            self._db.add(
                DocumentNgram(
                    document_id=document_id,
                    n=size,
                    ngram=ngram,
                    ngram_hash=_ngram_hash(ngram),
                    count=int(count),
                )
            )
        self._db.commit()
        return len(counts)


class NgramSearchService:
    def __init__(self, db: Session):
        self._db = db

    def search(
        self,
        *,
        query: str,
        document_id: int | None,
        mode: str,
        limit: int,
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
        NgramsService(self._db).ensure_materialized(document_id=document_id)

        if mode == "partial":
            counts_by_doc, total = self._search_partial(tokens=tokens, n=n, document_id=document_id)
        else:
            counts_by_doc, total = self._search_exact(normalized=normalized.lower(), n=n, document_id=document_id)

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
        docs = self._db.execute(select(Document.id, Document.filename, Document.title).where(Document.id.in_(doc_ids))).all()
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

    def _search_exact(self, *, normalized: str, n: int, document_id: int | None) -> tuple[dict[int, int], int]:
        stmt = select(DocumentNgram.document_id, DocumentNgram.count).where(
            DocumentNgram.n == n,
            DocumentNgram.ngram_hash == _ngram_hash(normalized),
            DocumentNgram.ngram == normalized,
        )
        stmt = stmt.join(Document, Document.id == DocumentNgram.document_id).where(Document.deleted_at.is_(None))
        if document_id is not None:
            stmt = stmt.where(DocumentNgram.document_id == document_id)
        rows = self._db.execute(stmt).all()

        counts_by_doc: dict[int, int] = defaultdict(int)
        total = 0
        for doc_id, count in rows:
            counts_by_doc[int(doc_id)] += int(count)
            total += int(count)
        return counts_by_doc, total

    def _search_partial(self, *, tokens: list[str], n: int, document_id: int | None) -> tuple[dict[int, int], int]:
        stmt = (
            select(DocumentNgram.document_id, DocumentNgram.ngram, DocumentNgram.count)
            .join(Document, Document.id == DocumentNgram.document_id)
            .where(Document.deleted_at.is_(None), DocumentNgram.n == n)
        )
        if document_id is not None:
            stmt = stmt.where(DocumentNgram.document_id == document_id)
        for token in tokens:
            stmt = stmt.where(DocumentNgram.ngram.like(f"%{token}%"))

        counts_by_doc: dict[int, int] = defaultdict(int)
        total = 0
        for doc_id, ngram, count in self._db.execute(stmt).all():
            parts = str(ngram or "").split(" ")
            if len(parts) != n:
                continue
            if all(tokens[index] in parts[index] for index in range(n)):
                counts_by_doc[int(doc_id)] += int(count)
                total += int(count)
        return counts_by_doc, total
