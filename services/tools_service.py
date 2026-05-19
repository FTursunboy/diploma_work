from collections import Counter, defaultdict

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import Document, Paragraph, Sentence, Word


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
        statement = select(word_col, count_col)
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
        stmt = select(Word.sentence_id, Word.word_index, Word.word)
        if document_id is not None:
            stmt = stmt.where(Word.document_id == document_id)
        stmt = stmt.order_by(Word.sentence_id, Word.word_index)
        rows = self._db.execute(stmt).all()

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

        stmt = select(Word.document_id, Word.sentence_id, Word.word_index, Word.word)
        if document_id is not None:
            stmt = stmt.where(Word.document_id == document_id)
        stmt = stmt.order_by(Word.document_id, Word.sentence_id, Word.word_index)
        rows = self._db.execute(stmt).all()

        counts_by_doc: dict[int, int] = defaultdict(int)
        total = 0

        current_doc = None
        current_sentence = None
        buffer: list[str] = []

        def flush() -> None:
            nonlocal total
            if not buffer or len(buffer) < n:
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

