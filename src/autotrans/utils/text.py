from __future__ import annotations

import re
from collections import Counter


_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[A-Za-z0-9']+")


def normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text or "").strip()


def tokenize_words(text: str) -> list[str]:
    return _WORD_RE.findall(normalize_text(text).lower())


def is_probably_garbage_text(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return True

    tokens = tokenize_words(normalized)
    if not tokens:
        return True

    if len(tokens) >= 5:
        counts = Counter(tokens)
        most_common = counts.most_common(1)[0][1]
        if most_common / len(tokens) >= 0.45:
            return True

    if len(tokens) >= 6 and len(set(tokens)) <= 2:
        return True

    short_tokens = sum(1 for token in tokens if len(token) <= 2)
    if len(tokens) >= 6 and short_tokens / len(tokens) >= 0.7:
        return True

    if len(normalized) >= 18:
        compact = normalized.lower().replace(" ", "")
        unique_chars = len(set(compact))
        if unique_chars <= 4:
            return True

    return False