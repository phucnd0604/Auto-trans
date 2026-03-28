from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from threading import RLock

from autotrans.utils.text import normalize_text


@dataclass(slots=True)
class TranslationCacheEntry:
    translated_text: str
    provider: str


class TranslationCache:
    def __init__(self, db_path: Path | None = None) -> None:
        self._entries: dict[str, TranslationCacheEntry] = {}
        self.hits = 0
        self._db_path: Path | None = None
        self._conn: sqlite3.Connection | None = None
        self._lock = RLock()
        if db_path is not None:
            self.set_persistent_path(db_path)

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
        with self._lock:
            entry = self._entries.get(key)
            if entry is None and self._conn is not None:
                row = self._conn.execute(
                    "SELECT translated_text, provider FROM translations WHERE cache_key = ?",
                    (key,),
                ).fetchone()
                if row is not None:
                    entry = TranslationCacheEntry(translated_text=row[0], provider=row[1])
                    self._entries[key] = entry
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
        entry = TranslationCacheEntry(
            translated_text=translated_text,
            provider=provider,
        )
        with self._lock:
            self._entries[key] = entry
            if self._conn is not None:
                self._conn.execute(
                    """
                    INSERT INTO translations(cache_key, translated_text, provider)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        translated_text = excluded.translated_text,
                        provider = excluded.provider
                    """,
                    (key, translated_text, provider),
                )
                self._conn.commit()

    def set_persistent_path(self, db_path: Path) -> None:
        with self._lock:
            if self._db_path == db_path and self._conn is not None:
                return
            if self._conn is not None:
                self._conn.close()
            self._db_path = db_path
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    cache_key TEXT PRIMARY KEY,
                    translated_text TEXT NOT NULL,
                    provider TEXT NOT NULL
                )
                """
            )
            self._conn.commit()
            print(f"[AutoTrans] Cache DB: {db_path}", flush=True)
