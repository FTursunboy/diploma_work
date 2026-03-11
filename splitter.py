import re


PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"\b[\w'-]+\b", flags=re.UNICODE)


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def split_paragraphs(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    parts = PARAGRAPH_SPLIT_RE.split(normalized)
    paragraphs: list[str] = []
    for part in parts:
        cleaned = " ".join(line.strip() for line in part.splitlines() if line.strip())
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


def split_sentences(paragraph_text: str) -> list[str]:
    parts = SENTENCE_SPLIT_RE.split(paragraph_text.strip())
    return [part.strip() for part in parts if part.strip()]


def split_words(sentence_text: str) -> list[str]:
    return [word for word in WORD_RE.findall(sentence_text) if word]
