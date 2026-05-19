import os

from splitter import normalize_text, split_paragraphs


DEFAULT_MAX_CHUNK_TOKENS = 800
DEFAULT_MIN_CHUNK_CHARS = 80


def _estimated_tokens(text: str) -> int:
    # A lightweight approximation is enough here; it keeps chunks in the target range
    # without adding a tokenizer dependency to the diploma project.
    words = len((text or "").split())
    chars = len(text or "")
    return max(words, chars // 4)


def max_chunk_tokens() -> int:
    raw = os.getenv("EMBEDDING_MAX_CHUNK_TOKENS", str(DEFAULT_MAX_CHUNK_TOKENS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_CHUNK_TOKENS
    return min(1000, max(500, value))


def split_text_chunks(text: str, *, max_tokens: int | None = None) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    limit = max_tokens or max_chunk_tokens()
    paragraphs = split_paragraphs(normalized)
    if not paragraphs:
        paragraphs = [" ".join(normalized.split())]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        chunk = "\n\n".join(current).strip()
        if chunk:
            chunks.append(chunk)
        current = []
        current_tokens = 0

    for paragraph in paragraphs:
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue

        tokens = _estimated_tokens(paragraph)
        if tokens > limit:
            flush()
            words = paragraph.split()
            part: list[str] = []
            part_tokens = 0
            for word in words:
                token_cost = _estimated_tokens(word)
                if part and part_tokens + token_cost > limit:
                    chunks.append(" ".join(part))
                    part = []
                    part_tokens = 0
                part.append(word)
                part_tokens += token_cost
            if part:
                chunks.append(" ".join(part))
            continue

        if current and current_tokens + tokens > limit:
            flush()
        current.append(paragraph)
        current_tokens += tokens

    flush()
    return [chunk for chunk in chunks if len(chunk) >= DEFAULT_MIN_CHUNK_CHARS]
