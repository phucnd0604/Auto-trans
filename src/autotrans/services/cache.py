from __future__ import annotations

from dataclasses import dataclass

from autotrans.utils.text import normalize_text


@dataclass(slots=True)
class TranslationCacheEntry:
    translated_text: str
    provider: str


class TranslationCache:
    def __init__(self) -> None:
        self._entries: dict[str, TranslationCacheEntry] = {}
        self.hits = 0

    @staticmethod
    def make_key(
        text: str,
        source_lang: str,
        target_lang: str,
        glossary_version: str,
    ) -> str:
        normalized = normalize_text(text)
        return f"{source_lang}:{target_lang}:{glossary_version}:{normalized}"

    def get(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        glossary_version: str,
    ) -> TranslationCacheEntry | None:
        key = self.make_key(text, source_lang, target_lang, glossary_version)
        entry = self._entries.get(key)
        if entry is not None:
            self.hits += 1
        return entry

    def put(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        glossary_version: str,
        translated_text: str,
        provider: str,
    ) -> None:
        key = self.make_key(text, source_lang, target_lang, glossary_version)
        self._entries[key] = TranslationCacheEntry(
            translated_text=translated_text,
            provider=provider,
        )