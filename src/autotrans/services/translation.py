from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Protocol

from autotrans.config import AppConfig
from autotrans.models import OCRBox, QualityMode, TranslationResult
from autotrans.utils.text import normalize_text

GEMINI_DEEP_SYSTEM_PROMPT = """Role: Người là một đại sư dịch thuật cổ phong, chuyên gia chuyển ngữ tiểu thuyết Tiên hiệp và Kiếm hiệp sang tiếng Việt theo phong cách chương hồi của Vong Ngữ.

Quy tắc chuyển ngữ:

    Xưng hô (Quan trọng):
    - Dựa vào địa vị: Dùng 'Tại hạ', 'Đạo hữu', 'Các hạ', 'Tiền bối', 'Vãn bối', 'Sư tôn', 'Đồ nhi'.

        Tuyệt đối KHÔNG dùng: 'Tôi', 'Bạn', 'Anh', 'Em', 'Mày', 'Tao'.

    Từ vựng Hán Việt: Ưu tiên dùng từ Hán Việt cổ điển.

        Ví dụ: 'Đi bộ' -> 'Bộ hành', 'Uống rượu' -> 'Ẩm tửu', 'Cửa hàng' -> 'Linh bảo các/Tiệm thuốc', 'Money' -> 'Linh thạch/Bạc'.

    Cấu trúc câu: Hành văn súc tích, mang âm hưởng kiếm hiệp. Nếu là lời chào, hãy dịch là 'Bái kiến' hoặc 'Hữu lễ'.

    Tên riêng: Giữ nguyên tên riêng nhưng thêm danh xưng (Thiếu hiệp, Tiên tử, Lão quái, Yêu nhân).

Ví dụ mẫu:

    Input: "Hello Phuc, what are you doing here?" -> Output: "Bái kiến Phúc thiếu hiệp, chẳng hay các hạ ghé thăm nơi này có điều chi chỉ giáo?"

    Input: "I will kill you!" -> Output: "Ngươi muốn tìm cái chết! Hôm nay ta sẽ cho ngươi biết thế nào là hồn bay phách tán!"

Yêu cầu: Dịch thẳng sang tiếng Việt, không giải thích thêm."""


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


class GeminiTranslator:
    name = "gemini"
    _LEADING_NUMBER_RE = re.compile(r"^\s*[\"'`]*\s*\d+[\.\):\-]\s*")
    _LEADING_BULLET_RE = re.compile(r"^\s*[\"'`]*\s*[-*]+\s*")
    _BLOCK_RE = re.compile(r"<BLOCK_(\d+)>\s*(.*?)\s*</BLOCK_\1>", re.DOTALL)

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        api_key: str | None = None,
        config: AppConfig | None = None,
        timeout_s: float = 2.5,
        verbose: bool = False,
        max_logged_items: int = 6,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._config = config
        self._timeout_s = timeout_s
        self._verbose = verbose
        self._max_logged_items = max_logged_items
        self._client = None

    def _log_verbose_block(self, label: str, text: str) -> None:
        if not self._verbose:
            return
        started = time.perf_counter()
        print(f"[AutoTrans][{self._model}] {label} BEGIN", flush=True)
        print(text, flush=True)
        print(f"[AutoTrans][{self._model}] {label} END", flush=True)
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"[AutoTrans][{self._model}] {label} log_ms={elapsed_ms:.0f}", flush=True)

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed") from exc
        client_kwargs: dict[str, str] = {}
        if self._api_key:
            client_kwargs["api_key"] = self._api_key
        client_kwargs["http_options"] = types.HttpOptions(
            timeout=max(int(self._timeout_s * 1000), 1000),
        )
        self._client = genai.Client(**client_kwargs)
        return self._client

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

    def _build_game_profile_lines(self) -> list[str]:
        if self._config is None:
            return []

        profile_pairs = [
            ("Game Title", self._config.game_profile_title),
            ("World / Setting", self._config.game_profile_world),
            ("Factions / Organizations", self._config.game_profile_factions),
            ("Characters & Honorifics", self._config.game_profile_characters_honorifics),
            ("Terms / Items / Skills", self._config.game_profile_terms_items_skills),
        ]
        lines = [f"{label}: {value.strip()}" for label, value in profile_pairs if value and value.strip()]
        return lines

    def _build_deep_system_instruction(self) -> str:
        system_lines = [GEMINI_DEEP_SYSTEM_PROMPT]
        game_profile_lines = self._build_game_profile_lines()
        if game_profile_lines:
            system_lines.extend(
                [
                    "",
                    "Game Profile va ngu canh:",
                    *game_profile_lines,
                ]
            )
        return "\n".join(system_lines)

    def _build_deep_translation_contents(self, items: list[OCRBox]) -> str:
        prompt_lines: list[str] = []
        prompt_lines.extend(
            [
                "Quy tac output:",
                "- Tra ve dung 1 block output cho moi block input, dung thu tu.",
                "- Giu nguyen tag <BLOCK_n> va </BLOCK_n> trong output.",
                "- Chi viet noi dung dich nam ben trong tung tag.",
                "- Khong them ghi chu, khong giai thich, khong doi thu tu.",
                "",
                "Input blocks:",
            ]
        )
        for index, item in enumerate(items, start=1):
            prompt_lines.append(f"<BLOCK_{index}>")
            prompt_lines.append(item.source_text.strip())
            prompt_lines.append(f"</BLOCK_{index}>")
        return "\n".join(prompt_lines)

    def _generate_batch_text(self, contents: str) -> str:
        response = self._get_client().models.generate_content(
            model=self._model,
            contents=contents,
        )
        return normalize_text(getattr(response, "text", "")).strip()

    def _generate_deep_text(self, system_instruction: str, contents: str) -> str:
        try:
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed") from exc
        response = self._get_client().models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return normalize_text(getattr(response, "text", "")).strip()

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
        contents = "\n".join(prompt_lines)
        self._log_verbose_block("gemini batch contents", contents)
        output_text = self._generate_batch_text(contents)
        self._log_verbose_block("gemini batch response", output_text or "<empty>")
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
        build_started = time.perf_counter()
        system_instruction = self._build_deep_system_instruction()
        contents = self._build_deep_translation_contents(items)
        build_elapsed_ms = (time.perf_counter() - build_started) * 1000
        self._log_verbose_block("gemini deep system_instruction", system_instruction)
        self._log_verbose_block("gemini deep contents", contents)
        request_started = time.perf_counter()
        output_text = self._generate_deep_text(system_instruction, contents)
        request_elapsed_ms = (time.perf_counter() - request_started) * 1000
        self._log_verbose_block("gemini deep response", output_text or "<empty>")
        parse_started = time.perf_counter()
        translated_blocks = self._parse_block_response(output_text, len(items))
        parse_elapsed_ms = (time.perf_counter() - parse_started) * 1000
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
            print(
                f"[AutoTrans][{self._model}] deep timing build_ms={build_elapsed_ms:.0f} request_ms={request_elapsed_ms:.0f} parse_ms={parse_elapsed_ms:.0f}",
                flush=True,
            )
        return results


class GeminiRestTranslator(GeminiTranslator):
    name = "gemini-rest"
    _ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    @staticmethod
    def _normalize_response_payload(payload: object) -> dict[str, object]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    return item
            raise RuntimeError("Gemini REST returned a list without any object payload")
        raise RuntimeError(f"Gemini REST returned unsupported payload type: {type(payload).__name__}")

    def _post_json(self, payload: dict[str, object]) -> dict[str, object]:
        if not self._api_key:
            raise RuntimeError("Gemini API key is required")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            result = subprocess.run(
                [
                    "curl.exe",
                    "--silent",
                    "--show-error",
                    "--location",
                    "--max-time",
                    str(max(int(self._timeout_s), 1)),
                    "-X",
                    "POST",
                    self._ENDPOINT,
                    "-H",
                    f"Authorization: Bearer {self._api_key}",
                    "-H",
                    "Content-Type: application/json",
                    "--data-binary",
                    "@-",
                ],
                input=data,
                capture_output=True,
                check=False,
                timeout=max(self._timeout_s + 5.0, 10.0),
            )
        except FileNotFoundError as exc:
            raise RuntimeError("curl.exe is not available") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Gemini REST curl timeout after {self._timeout_s:.1f}s") from exc
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Gemini REST curl failed ({result.returncode}): {stderr}")
        raw = result.stdout.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gemini REST invalid JSON response: {raw[:400]}") from exc
        parsed = self._normalize_response_payload(parsed)
        error_payload = parsed.get("error")
        if isinstance(error_payload, dict):
            raise RuntimeError(f"Gemini REST API error: {json.dumps(error_payload, ensure_ascii=False)}")
        return parsed

    @staticmethod
    def _extract_content_text(content: object) -> str:
        if isinstance(content, str):
            return normalize_text(content).strip()
        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    item_type = normalize_text(str(item.get("type", ""))).strip().lower()
                    if item_type not in {"", "text", "output_text"}:
                        continue
                    text_value = item.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        fragments.append(normalize_text(text_value).strip())
            return normalize_text("\n".join(fragment for fragment in fragments if fragment)).strip()
        return ""

    @classmethod
    def _extract_standard_choice_text(cls, payload: object) -> str:
        if not isinstance(payload, dict):
            return ""
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        message = first.get("message")
        if not isinstance(message, dict):
            return ""
        return cls._extract_content_text(message.get("content"))

    @staticmethod
    def _extract_message_text(payload: object) -> str:
        if isinstance(payload, list):
            for item in payload:
                text = GeminiRestTranslator._extract_message_text(item)
                if text:
                    return text
            return ""
        text = GeminiRestTranslator._extract_standard_choice_text(payload)
        if text:
            return text
        if not isinstance(payload, dict):
            return ""
        candidates = [
            payload.get("output_text"),
            payload.get("text"),
            payload.get("content"),
        ]
        for candidate in candidates:
            text = GeminiRestTranslator._extract_content_text(candidate)
            if text:
                return text
        return ""

    def _generate_batch_text(self, contents: str) -> str:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": contents,
                }
            ],
        }
        self._log_verbose_block("gemini rest batch request", json.dumps(payload, ensure_ascii=False, indent=2))
        response_payload = self._post_json(payload)
        self._log_verbose_block(
            "gemini rest batch response raw",
            json.dumps(response_payload, ensure_ascii=False, indent=2),
        )
        return self._extract_message_text(response_payload)

    def _generate_deep_text(self, system_instruction: str, contents: str) -> str:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": system_instruction,
                },
                {
                    "role": "user",
                    "content": contents,
                },
            ],
        }
        self._log_verbose_block("gemini rest deep request", json.dumps(payload, ensure_ascii=False, indent=2))
        response_payload = self._post_json(payload)
        self._log_verbose_block(
            "gemini rest deep response raw",
            json.dumps(response_payload, ensure_ascii=False, indent=2),
        )
        return self._extract_message_text(response_payload)


def build_default_local_translator(config: AppConfig) -> TranslatorProvider:
    backend = config.local_translator_backend.strip().lower()
    if backend != "ctranslate2":
        print(f"[AutoTrans] Unsupported local translator '{backend}', forcing ctranslate2", flush=True)
    return CTranslate2Translator(config)
