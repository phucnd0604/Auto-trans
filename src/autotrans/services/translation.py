from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Protocol

from autotrans.config import AppConfig
from autotrans.models import OCRBox, QualityMode, TranslationResult
from autotrans.utils.text import normalize_text


class TranslatorProvider(Protocol):
    name: str

    def translate_batch(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
        mode: QualityMode,
    ) -> list[TranslationResult]:
        ...


class LocalEchoTranslator:
    name = "local-fallback"

    def translate_batch(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
        mode: QualityMode,
    ) -> list[TranslationResult]:
        started = time.perf_counter()
        results: list[TranslationResult] = []
        for item in items:
            translated = self._basic_translate(item.source_text)
            results.append(
                TranslationResult(
                    source_text=item.source_text,
                    translated_text=translated,
                    provider=self.name,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
        return results

    @staticmethod
    def _basic_translate(text: str) -> str:
        normalized = normalize_text(text)
        dictionary = {
            "quest accepted": "Nhiem vu da nhan",
            "start adventure": "Bat dau cuoc phieu luu",
            "buy": "Mua",
            "sell": "Ban",
            "new thread": "Cuoc tro chuyen moi",
            "options": "Tuy chon",
            "audio game": "Am thanh va tro choi",
            "gamepad": "Tay cam",
            "game": "Tro choi",
            "audio": "Am thanh",
            "display": "Hien thi",
            "graphics": "Do hoa",
            "mouse&keyboard": "Chuot va ban phim",
            "mouse & keyboard": "Chuot va ban phim",
            "accessibility": "Tro nang truy cap",
            "privacy settings": "Cai dat quyen rieng tu",
            "esc exit": "ESC Thoat",
            "restartfromlastcheckpoint": "Choi lai tu diem luu gan nhat",
            "restart from last checkpoint": "Choi lai tu diem luu gan nhat",
            "exittotitle screen": "Thoat ve man hinh tieu de",
            "exit to title screen": "Thoat ve man hinh tieu de",
            "savegame": "Luu game",
            "save game": "Luu game",
            "quitgame": "Thoat game",
            "quit game": "Thoat game",
            "enterlegendsmode": "Vao che do Legends",
            "enter legends mode": "Vao che do Legends",
            "taptobreakdefenseand": "Nhan de pha phong thu va",
            "then toquick attack 0/4 staggerenemy": "sau do tan cong nhanh 0/4 lam choang ke dich",
            "taptobreakdefenseand then toquick attack 0/4 staggerenemy": "Nhan de pha phong thu, sau do tan cong nhanh 0/4 lam choang ke dich",
            "tap to break defense and then to quick attack 0/4 stagger enemy": "Nhan de pha phong thu, sau do tan cong nhanh 0/4 lam choang ke dich",
            "lord shimura: break my block with a heavy attack, then strike quickly.": "Lord Shimura: Hay pha the do cua ta bang don manh, roi ra don that nhanh.",
        }
        translated = dictionary.get(normalized.lower())
        if translated:
            return translated
        return normalized


class HybridLocalTranslator:
    name = "local-hybrid"

    _GLOSSARY = {
        "quest accepted": "Nhiem vu da nhan",
        "start adventure": "Bat dau cuoc phieu luu",
        "buy": "Mua",
        "sell": "Ban",
        "new thread": "Cuoc tro chuyen moi",
        "options": "Tuy chon",
        "gamepad": "Tay cam",
        "game": "Tro choi",
        "audio": "Am thanh",
        "display": "Hien thi",
        "graphics": "Do hoa",
        "mouse & keyboard": "Chuot va ban phim",
        "mouse keyboard": "Chuot va ban phim",
        "accessibility": "Tro nang truy cap",
        "privacy settings": "Cai dat quyen rieng tu",
        "esc exit": "ESC Thoat",
        "show on map": "Hien tren ban do",
        "sort by most recent": "Sap xep theo moi nhat",
        "show on map sort by most recent": "Hien tren ban do Sap xep theo moi nhat",
        "map journal": "Ban do va nhat ky",
        "completed tales": "Nhiem vu da hoan thanh",
        "major legend": "Truyen thuyet lon",
        "hammer and forge": "Bua va lo ren",
        "the tale of ryuzo": "Truyen ve Ryuzo",
        "act 1 rescue lord shimura": "Hoi 1 Giai cuu Lord Shimura",
        "forge a tool to climb the walls of castle kaneda": "Che tao cong cu de leo tuong thanh Castle Kaneda",
        "go to the town of komatsu forge": "Di den thi tran Komatsu Forge",
        "restart from last checkpoint": "Choi lai tu diem luu gan nhat",
        "save game": "Luu game",
        "enter legends mode": "Vao che do Legends",
        "exit to title screen": "Thoat ve man hinh tieu de",
        "quit game": "Thoat game",
        "audio game": "Am thanh va tro choi",
        "lord shimura: break my block with a heavy attack, then strike quickly.": "Lord Shimura: Hay pha the do cua ta bang don manh, roi ra don that nhanh.",
        "tap to break defense and then to quick attack 0/4 stagger enemy": "Nhan de pha phong thu, sau do tan cong nhanh 0/4 lam choang ke dich",
        "yuna's brother is finally safe, but we had to split up after our escape.": "Anh em cua Yuna cuoi cung da an toan, nhung chung toi buoc phai tach ra sau cuoc tau thoat.",
    }
    _COMPACT_RE = re.compile(r"[^a-z0-9]+")

    def __init__(self, delegate: TranslatorProvider | None = None) -> None:
        self._delegate = delegate
        self._compact_glossary = {
            self._compact_key(source): target for source, target in self._GLOSSARY.items()
        }

    @classmethod
    def _compact_key(cls, text: str) -> str:
        return cls._COMPACT_RE.sub("", normalize_text(text).lower())

    def _lookup_glossary(self, text: str) -> str | None:
        normalized = normalize_text(text).lower()
        translated = self._GLOSSARY.get(normalized)
        if translated:
            return translated
        return self._compact_glossary.get(self._compact_key(normalized))

    def _replace_known_phrases(self, text: str) -> str | None:
        normalized = normalize_text(text)
        lowered = normalized.lower()
        replaced = normalized
        changed = False
        for source, target in sorted(self._GLOSSARY.items(), key=lambda item: len(item[0]), reverse=True):
            if " " not in source:
                continue
            position = lowered.find(source)
            if position == -1:
                continue
            replaced = replaced[:position] + target + replaced[position + len(source):]
            lowered = replaced.lower()
            changed = True
        return replaced if changed else None

    @staticmethod
    def _looks_glued_ui_text(text: str) -> bool:
        normalized = normalize_text(text)
        compact = normalized.replace(" ", "")
        return len(compact) >= 10 and compact.upper() == compact and " " not in normalized

    @staticmethod
    def _looks_broken_translation(text: str) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return True
        compact = normalized.replace(" ", "")
        if len(compact) >= 12 and len(set(compact)) <= 2:
            return True
        tokens = normalized.split()
        if len(tokens) >= 4:
            counts = Counter(tokens)
            if counts.most_common(1)[0][1] / len(tokens) >= 0.6:
                return True
        return False

    def _should_use_delegate(self, text: str) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        if self._looks_glued_ui_text(normalized):
            return False
        return len(normalized) >= 12 or " " in normalized or ":" in normalized

    def translate_batch(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
        mode: QualityMode,
    ) -> list[TranslationResult]:
        started = time.perf_counter()
        results: list[TranslationResult] = []
        pending: list[OCRBox] = []
        pending_index: list[int] = []

        for index, item in enumerate(items):
            translated = self._lookup_glossary(item.source_text)
            if translated is not None:
                results.append(
                    TranslationResult(
                        source_text=item.source_text,
                        translated_text=translated,
                        provider=self.name,
                        latency_ms=(time.perf_counter() - started) * 1000,
                    )
                )
                continue

            partial = self._replace_known_phrases(item.source_text)
            if partial is not None:
                results.append(
                    TranslationResult(
                        source_text=item.source_text,
                        translated_text=partial,
                        provider=self.name,
                        latency_ms=(time.perf_counter() - started) * 1000,
                    )
                )
                continue

            if self._delegate is not None and self._should_use_delegate(item.source_text):
                pending.append(
                    OCRBox(
                        id=item.id,
                        source_text=normalize_text(item.source_text),
                        confidence=item.confidence,
                        bbox=item.bbox,
                        language_hint=item.language_hint,
                        line_id=item.line_id,
                    )
                )
                pending_index.append(index)
                results.append(
                    TranslationResult(
                        source_text=item.source_text,
                        translated_text="",
                        provider=self.name,
                        latency_ms=0.0,
                    )
                )
                continue

            results.append(
                TranslationResult(
                    source_text=item.source_text,
                    translated_text=normalize_text(item.source_text),
                    provider=self.name,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )

        if pending and self._delegate is not None:
            delegated = self._delegate.translate_batch(
                pending,
                source_lang=source_lang,
                target_lang=target_lang,
                mode=mode,
            )
            for slot, item, translated in zip(pending_index, pending, delegated, strict=False):
                final_text = normalize_text(translated.translated_text)
                if self._looks_broken_translation(final_text):
                    final_text = self._lookup_glossary(item.source_text) or normalize_text(item.source_text)
                results[slot] = TranslationResult(
                    source_text=items[slot].source_text,
                    translated_text=final_text,
                    provider=getattr(self._delegate, "name", self.name),
                    latency_ms=translated.latency_ms,
                )

        return results


class CTranslate2Translator:
    name = "local"

    def __init__(self, config: AppConfig) -> None:
        import ctranslate2
        import sentencepiece as spm
        from huggingface_hub import snapshot_download

        model_dir = config.local_model_dir
        if model_dir is None:
            model_dir = Path(
                snapshot_download(
                    repo_id=config.local_model_repo,
                    allow_patterns=[
                        "model.bin",
                        "config.json",
                        "shared_vocabulary.txt",
                        "shared_vocabulary.json",
                        "source_vocabulary.txt",
                        "target_vocabulary.txt",
                        "source.spm",
                        "target.spm",
                        "tokenizer_config.json",
                    ],
                )
            )
        self._model_dir = Path(model_dir)
        self._source_sp = spm.SentencePieceProcessor()
        self._target_sp = spm.SentencePieceProcessor()
        if not self._source_sp.load(str(self._model_dir / "source.spm")):
            raise RuntimeError("Unable to load source.spm for local translator")
        if not self._target_sp.load(str(self._model_dir / "target.spm")):
            raise RuntimeError("Unable to load target.spm for local translator")

        self._ensure_vocab_files()

        self._translator = ctranslate2.Translator(
            str(self._model_dir),
            device=config.local_device,
            inter_threads=config.local_inter_threads,
            intra_threads=config.local_intra_threads,
        )
        self._warmup()

    def _ensure_vocab_files(self) -> None:
        shared_txt = self._model_dir / "shared_vocabulary.txt"
        if shared_txt.exists():
            return

        shared_json = self._model_dir / "shared_vocabulary.json"
        if shared_json.exists():
            with shared_json.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                pieces = [piece for piece, _ in sorted(data.items(), key=lambda item: item[1])]
            else:
                pieces = list(data)
        else:
            pieces = [self._source_sp.id_to_piece(i) for i in range(self._source_sp.get_piece_size())]

        shared_txt.write_text("\n".join(pieces) + "\n", encoding="utf-8")

    def _warmup(self) -> None:
        try:
            self._translate_texts(["start game"])
        except Exception:
            pass

    def _translate_texts(self, texts: list[str]) -> list[str]:
        tokenized = [self._source_sp.encode(normalize_text(text), out_type=str) for text in texts]
        results = self._translator.translate_batch(
            tokenized,
            beam_size=1,
            max_decoding_length=128,
            return_scores=False,
            repetition_penalty=1.0,
            disable_unk=True,
        )
        outputs: list[str] = []
        for result in results:
            hypothesis = result.hypotheses[0] if result.hypotheses else []
            decoded = self._target_sp.decode(hypothesis)
            outputs.append(normalize_text(decoded))
        return outputs

    def translate_batch(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
        mode: QualityMode,
    ) -> list[TranslationResult]:
        started = time.perf_counter()
        texts = [item.source_text for item in items]
        translated_texts = self._translate_texts(texts)
        results: list[TranslationResult] = []
        for item, translated in zip(items, translated_texts, strict=False):
            results.append(
                TranslationResult(
                    source_text=item.source_text,
                    translated_text=translated or item.source_text,
                    provider=self.name,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
        return results


class OpenAITranslator:
    name = "cloud"
    _LEADING_NUMBER_RE = re.compile(r"^\s*[\"'`]*\s*\d+[\.\):\-]\s*")
    _LEADING_BULLET_RE = re.compile(r"^\s*[\"'`]*\s*[-*]+\s*")

    def __init__(
        self,
        model: str = "gpt-5-mini",
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 2.5,
        verbose: bool = False,
        max_logged_items: int = 6,
    ) -> None:
        from openai import OpenAI

        client_kwargs: dict[str, str] = {}
        if base_url:
            client_kwargs["base_url"] = base_url
        if api_key:
            client_kwargs["api_key"] = api_key
        self._client = OpenAI(**client_kwargs)
        self._model = model
        self._timeout_s = timeout_s
        self._verbose = verbose
        self._max_logged_items = max_logged_items

    @classmethod
    def _sanitize_line(cls, text: str) -> str:
        cleaned = normalize_text(text)
        cleaned = cls._LEADING_NUMBER_RE.sub("", cleaned)
        cleaned = cls._LEADING_BULLET_RE.sub("", cleaned)
        cleaned = cleaned.strip(" \"'`")
        return normalize_text(cleaned)

    def translate_batch(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
        mode: QualityMode,
    ) -> list[TranslationResult]:
        started = time.perf_counter()
        prompt_lines = [
            "You are translating OCR text from a video game UI into natural Vietnamese.",
            "Rules:",
            "- Return exactly one translated line per input line, in the same order.",
            "- Keep proper nouns like names, places, factions, and item names when appropriate.",
            "- Translate menu labels, quest objectives, and subtitles naturally and concisely.",
            "- Do not explain, do not add notes, and do not number lines.",
            "- If OCR text is messy, preserve the readable intent and avoid hallucinating extra content.",
            "",
            "Input lines:",
        ]
        prompt_lines.extend(f"{index + 1}. {item.source_text}" for index, item in enumerate(items))
        response = self._client.responses.create(
            model=self._model,
            input="\n".join(prompt_lines),
            timeout=self._timeout_s,
        )
        output_text = getattr(response, "output_text", "").strip()
        translated_lines = [
            self._sanitize_line(line)
            for line in output_text.splitlines()
            if self._sanitize_line(line)
        ]
        results: list[TranslationResult] = []
        for index, item in enumerate(items):
            translated = translated_lines[index] if index < len(translated_lines) else item.source_text
            results.append(
                TranslationResult(
                    source_text=item.source_text,
                    translated_text=translated,
                    provider=self.name,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
        if self._verbose:
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(
                f"[AutoTrans][{self._model}] translated {len(items)} item(s) in {elapsed_ms:.0f}ms",
                flush=True,
            )
            for item, result in list(zip(items, results, strict=False))[: self._max_logged_items]:
                print(
                    f"[AutoTrans][{self._model}] {normalize_text(item.source_text)!r} -> {normalize_text(result.translated_text)!r}",
                    flush=True,
                )
        return results

def build_default_local_translator(config: AppConfig) -> TranslatorProvider:
    if not config.local_model_enabled:
        return HybridLocalTranslator(delegate=None)

    try:
        delegate = CTranslate2Translator(config)
        return HybridLocalTranslator(delegate=delegate)
    except Exception:
        return HybridLocalTranslator(delegate=None)





