from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Protocol

import httpx

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

    def translate_screen_blocks(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
    ) -> list[TranslationResult]:
        ...


class CTranslate2Translator:
    name = "local-ctranslate2"
    _MODEL_PATTERNS = [
        "*.json",
        "*.txt",
        "*.spm",
        "*.model",
        "model.bin",
        "shared_vocabulary.json",
        "shared_vocabulary.txt",
        "source_vocabulary.txt",
        "target_vocabulary.txt",
    ]

    def __init__(self, config: AppConfig) -> None:
        import ctranslate2
        import sentencepiece as spm
        from huggingface_hub import snapshot_download

        self._model_dir = Path(config.local_model_dir)
        self._model_dir.mkdir(parents=True, exist_ok=True)
        if not any(self._model_dir.iterdir()):
            snapshot_download(
                repo_id=config.local_model_repo,
                local_dir=str(self._model_dir),
                allow_patterns=self._MODEL_PATTERNS,
            )
        self._cleanup_stale_vocab_files()

        source_tokenizer_path = self._find_first_existing(
            "source.spm",
            "source.model",
            "src.spm.model",
            "sentencepiece.model",
            "spm.model",
        )
        target_tokenizer_path = self._find_first_existing(
            "target.spm",
            "target.model",
            "tgt.spm.model",
            source_tokenizer_path.name if source_tokenizer_path is not None else "sentencepiece.model",
        )
        if source_tokenizer_path is None or target_tokenizer_path is None:
            raise RuntimeError(f"CTranslate2 tokenizer files not found in {self._model_dir}")

        self._source_sp = spm.SentencePieceProcessor(model_file=str(source_tokenizer_path))
        self._target_sp = spm.SentencePieceProcessor(model_file=str(target_tokenizer_path))
        self._translator = ctranslate2.Translator(
            str(self._model_dir),
            device=config.local_model_device,
            compute_type=config.local_model_compute_type,
            inter_threads=config.local_inter_threads,
            intra_threads=config.local_intra_threads,
        )

    def _find_first_existing(self, *names: str) -> Path | None:
        for name in names:
            candidate = self._model_dir / name
            if candidate.exists():
                return candidate
        return None

    def _cleanup_stale_vocab_files(self) -> None:
        shared_txt = self._model_dir / "shared_vocabulary.txt"
        shared_json = self._model_dir / "shared_vocabulary.json"
        source_vocab = self._model_dir / "source_vocabulary.json"
        target_vocab = self._model_dir / "target_vocabulary.json"
        if shared_txt.exists() and not shared_json.exists() and source_vocab.exists() and target_vocab.exists():
            shared_txt.unlink()

    def _translate_texts(self, texts: list[str]) -> list[str]:
        tokenized = [self._source_sp.encode(normalize_text(text), out_type=str) for text in texts]
        results = self._translator.translate_batch(
            tokenized,
            beam_size=1,
            max_decoding_length=128,
            return_scores=False,
        )
        outputs: list[str] = []
        for result in results:
            hypothesis = result.hypotheses[0] if result.hypotheses else []
            outputs.append(normalize_text(self._target_sp.decode(hypothesis)))
        return outputs

    def translate_batch(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
        mode: QualityMode,
    ) -> list[TranslationResult]:
        started = time.perf_counter()
        translated_texts = self._translate_texts([item.source_text for item in items])
        results: list[TranslationResult] = []
        for item, translated in zip(items, translated_texts, strict=False):
            results.append(
                TranslationResult(
                    source_text=item.source_text,
                    translated_text=translated or normalize_text(item.source_text),
                    provider=self.name,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(
            f"[AutoTrans][{self.name}] translated {len(items)} item(s) in {elapsed_ms:.0f}ms",
            flush=True,
        )
        for item, result in list(zip(items, results, strict=False))[:6]:
            print(
                f"[AutoTrans][{self.name}] {normalize_text(item.source_text)!r} -> {normalize_text(result.translated_text)!r}",
                flush=True,
            )
        return results

    def translate_screen_blocks(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
    ) -> list[TranslationResult]:
        return self.translate_batch(items, source_lang, target_lang, QualityMode.HIGH_QUALITY)


class WordByWordTranslator:
    name = "local-word-by-word"

    _WORD_MAP = {
        "follow": "theo",
        "yuna": "Yuna",
        "do": "",
        "not": "khong",
        "raise": "gay",
        "the": "",
        "alarm": "bao dong",
        "restart": "khoi dong lai",
        "from": "tu",
        "last": "cuoi",
        "checkpoint": "diem kiem soat",
        "exit": "thoat",
        "to": "den",
        "title": "tieu de",
        "screen": "man hinh",
        "enter": "vao",
        "legends": "Legends",
        "mode": "che do",
        "save": "luu",
        "game": "game",
        "accessibility": "tro nang",
        "mouse": "chuot",
        "keyboard": "ban phim",
        "audio": "am thanh",
        "graphics": "do hoa",
        "open": "mo",
        "close": "dong",
        "climb": "leo",
        "collect": "nhat",
        "pick": "nhat",
        "up": "len",
        "mission": "nhiem vu",
        "objective": "muc tieu",
        "quest": "nhiem vu",
        "journal": "nhat ky",
        "map": "ban do",
        "completed": "hoan thanh",
        "privacy": "rieng tu",
        "settings": "cai dat",
        "end": "ket thuc",
        "suffering": "dau kho",
        "more": "them",
        "guards": "linh canh",
        "they": "ho",
        "said": "noi",
        "all": "tat ca",
        "samurai": "samurai",
        "were": "da",
        "dead": "chet",
        "thank": "cam on",
        "you": "ban",
        "my": "cua toi",
        "lord": "lanh chua",
        "brother": "anh em",
        "mongols": "quan Mongol",
        "took": "bat",
        "him": "anh ay",
    }
    _TOKEN_RE = re.compile(r"[A-Za-z']+|\d+|[^A-Za-z'\d\s]+")

    def _translate_token(self, token: str) -> str:
        if not token:
            return token
        if not any(char.isalpha() for char in token):
            return token
        lowered = token.lower()
        translated = self._WORD_MAP.get(lowered)
        if translated is None:
            if token.isupper() and len(token) > 1:
                return token
            return token
        return translated

    def _translate_text(self, text: str) -> str:
        normalized = normalize_text(text)
        if not normalized:
            return ""
        tokens = self._TOKEN_RE.findall(normalized)
        translated_tokens: list[str] = []
        for token in tokens:
            mapped = self._translate_token(token)
            if mapped:
                translated_tokens.append(mapped)
        result = " ".join(translated_tokens)
        result = re.sub(r"\s+([,.:;!?])", r"\1", result)
        result = re.sub(r"\(\s+", "(", result)
        result = re.sub(r"\s+\)", ")", result)
        return normalize_text(result)

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
            translated = self._translate_text(item.source_text)
            results.append(
                TranslationResult(
                    source_text=item.source_text,
                    translated_text=translated or normalize_text(item.source_text),
                    provider=self.name,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(
            f"[AutoTrans][{self.name}] translated {len(items)} item(s) in {elapsed_ms:.0f}ms",
            flush=True,
        )
        for item, result in list(zip(items, results, strict=False))[:6]:
            print(
                f"[AutoTrans][{self.name}] {normalize_text(item.source_text)!r} -> {normalize_text(result.translated_text)!r}",
                flush=True,
            )
        return results

    def translate_screen_blocks(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
    ) -> list[TranslationResult]:
        return self.translate_batch(items, source_lang, target_lang, QualityMode.HIGH_QUALITY)


class OpenAITranslator:
    name = "openai"
    _LEADING_NUMBER_RE = re.compile(r"^\s*[\"'`]*\s*\d+[\.\):\-]\s*")
    _LEADING_BULLET_RE = re.compile(r"^\s*[\"'`]*\s*[-*]+\s*")
    _BLOCK_RE = re.compile(r"<BLOCK_(\d+)>\s*(.*?)\s*</BLOCK_\1>", re.DOTALL)

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

    @classmethod
    def _parse_block_response(cls, output_text: str, expected_count: int) -> list[str]:
        matches = cls._BLOCK_RE.findall(output_text or "")
        parsed: dict[int, str] = {}
        for raw_index, raw_text in matches:
            try:
                parsed[int(raw_index)] = normalize_text(raw_text)
            except ValueError:
                continue
        if parsed:
            return [cls._sanitize_line(parsed.get(index, "")) for index in range(1, expected_count + 1)]
        return [
            cls._sanitize_line(line)
            for line in (output_text or "").splitlines()
            if cls._sanitize_line(line)
        ]

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

    def translate_screen_blocks(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
    ) -> list[TranslationResult]:
        started = time.perf_counter()
        prompt_lines = [
            "You are a professional translator for story-heavy video games.",
            "Translate these OCR blocks from a single game screen into natural Vietnamese.",
            "Preserve consistent terminology, proper nouns, place names, factions, skills, and item names.",
            "If a block is a short UI label such as MAP, JOURNAL, GEAR, or TECHNIQUES, translate it as a concise UI label.",
            "If a block is quest, codex, lore, or story text, translate it fluently while preserving the intended tone.",
            "Rules:",
            "- Return exactly one output block for each input block, in the same order.",
            "- Keep the <BLOCK_n> and </BLOCK_n> tags in the output.",
            "- Write only the translation inside each tag.",
            "- Do not add notes, numbering, or explanations.",
            "",
            "Input blocks:",
        ]
        for index, item in enumerate(items, start=1):
            prompt_lines.append(f"<BLOCK_{index}>")
            prompt_lines.append(item.source_text)
            prompt_lines.append(f"</BLOCK_{index}>")
        response = self._client.responses.create(
            model=self._model,
            input="\n".join(prompt_lines),
            timeout=max(self._timeout_s, 15.0),
        )
        output_text = getattr(response, "output_text", "").strip()
        translated_blocks = self._parse_block_response(output_text, len(items))
        results: list[TranslationResult] = []
        for index, item in enumerate(items):
            translated = translated_blocks[index] if index < len(translated_blocks) else ""
            results.append(
                TranslationResult(
                    source_text=item.source_text,
                    translated_text=translated or normalize_text(item.source_text),
                    provider=self.name,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
        if self._verbose:
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(
                f"[AutoTrans][{self._model}] deep-translated {len(items)} block(s) in {elapsed_ms:.0f}ms",
                flush=True,
            )
        return results


class OllamaTranslator:
    name = "ollama"
    _LEADING_NUMBER_RE = re.compile(r"^\s*[\"'`]*\s*\d+[\.\):\-]\s*")
    _LEADING_BULLET_RE = re.compile(r"^\s*[\"'`]*\s*[-*]+\s*")
    _BLOCK_RE = re.compile(r"<BLOCK_(\d+)>\s*(.*?)\s*</BLOCK_\1>", re.DOTALL)

    def __init__(
        self,
        model: str,
        base_url: str,
        timeout_s: float = 15.0,
        verbose: bool = False,
        max_logged_items: int = 6,
    ) -> None:
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        # Deep mode can send large menu/lore screens, so Ollama needs a longer read timeout.
        self._timeout_s = max(timeout_s, 45.0)
        self._verbose = verbose
        self._max_logged_items = max_logged_items
        if not self._model:
            raise RuntimeError("Ollama model is required")
        if not self._base_url:
            raise RuntimeError("Ollama base URL is required")

    @classmethod
    def _sanitize_line(cls, text: str) -> str:
        cleaned = normalize_text(text)
        cleaned = cls._LEADING_NUMBER_RE.sub("", cleaned)
        cleaned = cls._LEADING_BULLET_RE.sub("", cleaned)
        cleaned = cleaned.strip(" \"'`")
        return normalize_text(cleaned)

    @classmethod
    def _parse_block_response(cls, output_text: str, expected_count: int) -> list[str]:
        matches = cls._BLOCK_RE.findall(output_text or "")
        parsed: dict[int, str] = {}
        for raw_index, raw_text in matches:
            try:
                parsed[int(raw_index)] = normalize_text(raw_text)
            except ValueError:
                continue
        if parsed:
            return [cls._sanitize_line(parsed.get(index, "")) for index in range(1, expected_count + 1)]
        return [
            cls._sanitize_line(line)
            for line in (output_text or "").splitlines()
            if cls._sanitize_line(line)
        ]

    def _generate(self, prompt: str) -> str:
        chunks: list[str] = []
        timeout = httpx.Timeout(self._timeout_s, connect=min(self._timeout_s, 5.0))
        with httpx.stream(
            "POST",
            f"{self._base_url}/api/generate",
            json={
                "model": self._model,
                "prompt": prompt,
                "stream": True,
                "keep_alive": "30m",
            },
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                payload = json.loads(line)
                chunk = normalize_text(str(payload.get("response", "")))
                if chunk:
                    chunks.append(chunk)
                if payload.get("done"):
                    break
        return normalize_text("".join(chunks))

    def translate_batch(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
        mode: QualityMode,
    ) -> list[TranslationResult]:
        started = time.perf_counter()
        prompt_lines = [
            "Bạn là một dịch giả game chuyên nghiệp. Hãy dịch các dòng OCR sau sang tiếng Việt tự nhiên.",
            "Quy tắc:",
            "- Trả về đúng 1 dòng dịch cho mỗi dòng đầu vào, đúng thứ tự.",
            "- Giữ tên riêng, địa danh, phe phái, tên vật phẩm khi phù hợp.",
            "- Không giải thích, không đánh số, không thêm ghi chú.",
            "",
            "Input lines:",
        ]
        prompt_lines.extend(f"{index + 1}. {item.source_text}" for index, item in enumerate(items))
        output_text = self._generate("\n".join(prompt_lines))
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
            print(f"[AutoTrans][{self._model}] translated {len(items)} item(s) in {elapsed_ms:.0f}ms", flush=True)
        return results

    def translate_screen_blocks(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
    ) -> list[TranslationResult]:
        started = time.perf_counter()
        prompt_lines = [
            "Bạn là một dịch giả truyện và game chuyên nghiệp.",
            "Hãy dịch các block OCR của cùng 1 màn hình game sang tiếng Việt.",
            "Ưu tiên dịch đúng nghĩa, tự nhiên, đúng ngữ cảnh UI game.",
            "Giữ nhất quán thuật ngữ, tên riêng, địa danh, phe phái, kỹ năng, vật phẩm.",
            "Nếu block là nhãn menu ngắn như MAP, JOURNAL, GEAR, TECHNIQUES thì dịch thành nhãn UI ngắn gọn, không diễn giải.",
            "Nếu block là mô tả quest, codex, lore hoặc hội thoại thì dịch mượt, đúng văn phong game.",
            "Quy tắc:",
            "- Trả về đúng 1 block output cho mỗi block input, đúng thứ tự.",
            "- Giữ nguyên tag <BLOCK_n> và </BLOCK_n> trong output.",
            "- Chỉ viết nội dung dịch nằm bên trong từng tag.",
            "- Không thêm giải thích, không thêm ghi chú, không đổi thứ tự.",
            "",
            "Input blocks:",
        ]
        for index, item in enumerate(items, start=1):
            prompt_lines.append(f"<BLOCK_{index}>")
            prompt_lines.append(item.source_text)
            prompt_lines.append(f"</BLOCK_{index}>")
        output_text = self._generate("\n".join(prompt_lines))
        translated_blocks = self._parse_block_response(output_text, len(items))
        results: list[TranslationResult] = []
        for index, item in enumerate(items):
            translated = translated_blocks[index] if index < len(translated_blocks) else ""
            results.append(
                TranslationResult(
                    source_text=item.source_text,
                    translated_text=translated or normalize_text(item.source_text),
                    provider=self.name,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
        if self._verbose:
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(f"[AutoTrans][{self._model}] deep-translated {len(items)} block(s) in {elapsed_ms:.0f}ms", flush=True)
        return results

def build_default_local_translator(config: AppConfig) -> TranslatorProvider:
    backend = config.local_translator_backend.strip().lower()
    if backend == "ctranslate2":
        try:
            return CTranslate2Translator(config)
        except Exception as exc:
            print(f"[AutoTrans] CTranslate2 unavailable, falling back to word-by-word: {exc}", flush=True)

    if backend == "word":
        return WordByWordTranslator()

    return WordByWordTranslator()
