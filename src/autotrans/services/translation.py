from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod
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

        self._config = config
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

    @staticmethod
    def _safe_log_text(text: str) -> str:
        normalized = normalize_text(text)
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            normalized.encode(encoding)
            return normalized
        except UnicodeEncodeError:
            return normalized.encode(encoding, errors="backslashreplace").decode(encoding)

    @staticmethod
    def _apply_honorific_postprocess(text: str) -> str:
        normalized = normalize_text(text)
        if not normalized:
            return normalized

        replacements = [
            (r"\bcác bạn\b", "Chư vị"),
            (r"\bbọn tôi\b", "Bọn ta"),
            (r"\bchúng tôi\b", "Chúng ta"),
            (r"\bchúng tao\b", "Chúng ta"),
            (r"\btụi tôi\b", "Bọn ta"),
            (r"\btụi tao\b", "Bọn ta"),
            (r"\btôi\b", "Ta"),
            (r"\btao\b", "Ta"),
            (r"\btớ\b", "Ta"),
            (r"\bmình\b", "Ta"),
            (r"\bbạn\b", "Ngươi"),
            (r"\bcậu\b", "Ngươi"),
        ]

        output = normalized
        for pattern, replacement in replacements:
            output = re.sub(pattern, replacement, output, flags=re.IGNORECASE)
        return normalize_text(output)

    def _translate_texts(self, texts: list[str]) -> list[str]:
        tokenized = [self._source_sp.encode(normalize_text(text), out_type=str) for text in texts]
        results = self._translator.translate_batch(
            tokenized,
            beam_size=max(self._config.local_beam_size, 1),
            repetition_penalty=max(self._config.local_repetition_penalty, 1.0),
            no_repeat_ngram_size=max(self._config.local_no_repeat_ngram_size, 0),
            max_decoding_length=max(self._config.local_max_decoding_length, 1),
            return_scores=False,
        )
        outputs: list[str] = []
        for result in results:
            hypothesis = result.hypotheses[0] if result.hypotheses else []
            outputs.append(self._apply_honorific_postprocess(self._target_sp.decode(hypothesis)))
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
        print(f"[AutoTrans][{self.name}] translated {len(items)} item(s) in {elapsed_ms:.0f}ms", flush=True)
        for item, result in list(zip(items, results, strict=False))[:6]:
            print(
                f"[AutoTrans][{self.name}] {self._safe_log_text(item.source_text)!r} -> {self._safe_log_text(result.translated_text)!r}",
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


class DeepCloudTranslatorBase(ABC):
    _LEADING_NUMBER_RE = re.compile(r"^\s*[\"'`]*\s*\d+[\.\):\-]\s*")
    _LEADING_BULLET_RE = re.compile(r"^\s*[\"'`]*\s*[-*]+\s*")
    _BLOCK_RE = re.compile(r"<BLOCK_(\d+)>\s*(.*?)\s*</BLOCK_\1>", re.DOTALL)

    def __init__(
        self,
        model: str,
        api_key: str | None,
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

    def _log_verbose_block(self, label: str, text: str) -> None:
        if not self._verbose:
            return
        started = time.perf_counter()
        print(f"[AutoTrans][{self.name}] {label} BEGIN", flush=True)
        print(text, flush=True)
        print(f"[AutoTrans][{self.name}] {label} END", flush=True)
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"[AutoTrans][{self.name}] {label} log_ms={elapsed_ms:.0f}", flush=True)

    @staticmethod
    def _safe_log_text(text: str) -> str:
        normalized = normalize_text(text)
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            normalized.encode(encoding)
            return normalized
        except UnicodeEncodeError:
            return normalized.encode(encoding, errors="backslashreplace").decode(encoding)

    @staticmethod
    def _get_payload_value(payload: object, key: str, default: object = None) -> object:
        if isinstance(payload, dict):
            return payload.get(key, default)
        return getattr(payload, key, default)

    @staticmethod
    def _normalize_response_payload(payload: object) -> dict[str, object]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    return item
            raise RuntimeError("Cloud translator returned a list without any object payload")
        if hasattr(payload, "model_dump"):
            dumped = payload.model_dump()
            if isinstance(dumped, dict):
                return dumped
        raise RuntimeError(f"Cloud translator returned unsupported payload type: {type(payload).__name__}")

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
        return [cls._sanitize_line(line) for line in (output_text or "").splitlines() if cls._sanitize_line(line)]

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
        return [f"{label}: {value.strip()}" for label, value in profile_pairs if value and value.strip()]

    def _build_deep_system_instruction(self) -> str:
        system_lines = [GEMINI_DEEP_SYSTEM_PROMPT]
        system_lines.extend(
            [
                "",
                "Ưu tiên trung thành với OCR hơn văn phong.",
                "Không được tự ý thêm ý, thêm chi tiết, thêm chủ ngữ, hay điền phần bị cắt mất.",
                "Nếu input là nhãn menu, tên vật phẩm, tên kỹ năng, mục tiêu ngắn, hoặc cụm từ rút gọn thì phải dịch ngắn gọn tương ứng, không biến thành câu văn dài.",
                "Không ép thêm xưng hô hoặc văn cổ phong vào mọi block. Chỉ dùng văn phong cổ phong khi input thực sự là câu hội thoại hoàn chỉnh.",
            ]
        )
        game_profile_lines = self._build_game_profile_lines()
        if game_profile_lines:
            system_lines.extend(
                [
                    "",
                    "Game Profile và ngữ cảnh:",
                    *game_profile_lines,
                ]
            )
        return "\n".join(system_lines)

    def _build_deep_translation_contents(self, items: list[OCRBox]) -> str:
        prompt_lines = [
            "Quy tắc output:",
            "- Trả về đúng 1 block output cho mỗi block input, đúng thứ tự.",
            "- Giữ nguyên tag <BLOCK_n> và </BLOCK_n> trong output.",
            "- Chỉ viết nội dung dịch nằm bên trong từng tag.",
            "- Không thêm ghi chú, không giải thích, không đổi thứ tự.",
            "- Dịch sát nghĩa và ngắn gọn. Không được diễn giải, phóng tác, hay viết dài hơn cần thiết.",
            "- Nếu input là menu label, tên vật phẩm, tên kỹ năng, tên nhiệm vụ, hoặc cụm ngắn thì output phải là một nhãn ngắn tương ứng, không thành câu dài.",
            "- Nếu input bị cắt do OCR thì chỉ dịch phần nhìn thấy, không được suy đoán phần bị thiếu.",
            "- Không thêm thông tin không xuất hiện trong block input.",
            "- Cố gắng giữ độ dài output gần với input. Input rất ngắn thì output cũng phải rất ngắn.",
            "",
            "Input blocks:",
        ]
        for index, item in enumerate(items, start=1):
            prompt_lines.append(f"<BLOCK_{index}>")
            prompt_lines.append(item.source_text.strip())
            prompt_lines.append(f"</BLOCK_{index}>")
        return "\n".join(prompt_lines)

    @staticmethod
    def _extract_content_text(content: object) -> str:
        if isinstance(content, str):
            return normalize_text(content).strip()
        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    item_type = normalize_text(str(item.get("type", ""))).strip().lower()
                    text_value = item.get("text")
                else:
                    item_type = normalize_text(str(getattr(item, "type", ""))).strip().lower()
                    text_value = getattr(item, "text", None)
                if item_type not in {"", "text", "output_text"}:
                    continue
                if isinstance(text_value, str) and text_value.strip():
                    fragments.append(normalize_text(text_value).strip())
            return normalize_text("\n".join(fragment for fragment in fragments if fragment)).strip()
        return ""

    @classmethod
    def _extract_standard_choice_text(cls, payload: object) -> str:
        choices = cls._get_payload_value(payload, "choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        message = cls._get_payload_value(first, "message")
        if message is None:
            return ""
        return cls._extract_content_text(cls._get_payload_value(message, "content"))

    @classmethod
    def _extract_message_text(cls, payload: object) -> str:
        if isinstance(payload, list):
            for item in payload:
                text = cls._extract_message_text(item)
                if text:
                    return text
            return ""
        text = cls._extract_standard_choice_text(payload)
        if text:
            return text
        if not isinstance(payload, dict) and not hasattr(payload, "model_dump"):
            return ""
        normalized_payload = payload.model_dump() if hasattr(payload, "model_dump") else payload
        for candidate in (
            normalized_payload.get("output_text"),
            normalized_payload.get("text"),
            normalized_payload.get("content"),
        ):
            text = cls._extract_content_text(candidate)
            if text:
                return text
        return ""

    @abstractmethod
    def _generate_batch_text(self, contents: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def _generate_deep_text(self, system_instruction: str, contents: str) -> str:
        raise NotImplementedError

    def translate_batch(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
        mode: QualityMode,
    ) -> list[TranslationResult]:
        started = time.perf_counter()
        prompt_lines = [
            "Ngươi đang dịch văn bản OCR từ giao diện game sang tiếng Việt tự nhiên.",
            "Quy tắc:",
            "- Trả về đúng một dòng dịch cho mỗi dòng input, đúng thứ tự.",
            "- Giữ nguyên tên riêng như nhân vật, địa danh, phe phái, vật phẩm khi phù hợp.",
            "- Dịch nhãn menu, mục tiêu nhiệm vụ, và phụ đề một cách tự nhiên, ngắn gọn.",
            "- Không giải thích, không thêm ghi chú, không đánh số.",
            "- Nếu OCR bị nhiễu, hãy giữ đúng ý đọc được và không tự bịa thêm nội dung.",
            "",
            "Các dòng input:",
        ]
        prompt_lines.extend(f"{index + 1}. {item.source_text}" for index, item in enumerate(items))
        contents = "\n".join(prompt_lines)
        self._log_verbose_block("batch contents", contents)
        output_text = self._generate_batch_text(contents)
        self._log_verbose_block("batch response", output_text or "<empty>")
        translated_lines = [self._sanitize_line(line) for line in output_text.splitlines() if self._sanitize_line(line)]
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
            print(f"[AutoTrans][{self.name}] translated {len(items)} item(s) in {elapsed_ms:.0f}ms", flush=True)
            for item, result in list(zip(items, results, strict=False))[: self._max_logged_items]:
                print(
                    f"[AutoTrans][{self.name}] {self._safe_log_text(item.source_text)!r} -> {self._safe_log_text(result.translated_text)!r}",
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
        self._log_verbose_block("deep system_instruction", system_instruction)
        self._log_verbose_block("deep contents", contents)
        request_started = time.perf_counter()
        output_text = self._generate_deep_text(system_instruction, contents)
        request_elapsed_ms = (time.perf_counter() - request_started) * 1000
        self._log_verbose_block("deep response", output_text or "<empty>")
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
            print(f"[AutoTrans][{self.name}] deep-translated {len(items)} block(s) in {elapsed_ms:.0f}ms", flush=True)
            print(
                f"[AutoTrans][{self.name}] deep timing build_ms={build_elapsed_ms:.0f} request_ms={request_elapsed_ms:.0f} parse_ms={parse_elapsed_ms:.0f}",
                flush=True,
            )
        return results


class GeminiTranslator(DeepCloudTranslatorBase):
    name = "gemini"
    _ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    def __init__(
        self,
        model: str = "gemini-3.1-flash-lite-preview",
        api_key: str | None = None,
        config: AppConfig | None = None,
        timeout_s: float = 2.5,
        verbose: bool = False,
        max_logged_items: int = 6,
    ) -> None:
        super().__init__(model, api_key, config, timeout_s=timeout_s, verbose=verbose, max_logged_items=max_logged_items)

    @staticmethod
    def _find_curl_binary() -> str:
        for candidate in ("curl.exe", "curl"):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        raise RuntimeError("curl is not available")

    def _post_json(self, payload: dict[str, object]) -> dict[str, object]:
        if not self._api_key:
            raise RuntimeError("Gemini API key is required")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            curl_binary = self._find_curl_binary()
            result = subprocess.run(
                [
                    curl_binary,
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
            raise RuntimeError("curl is not available") from exc
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

    def _generate_batch_text(self, contents: str) -> str:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [{"role": "user", "content": contents}],
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
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": contents},
            ],
        }
        self._log_verbose_block("gemini rest deep request", json.dumps(payload, ensure_ascii=False, indent=2))
        response_payload = self._post_json(payload)
        self._log_verbose_block(
            "gemini rest deep response raw",
            json.dumps(response_payload, ensure_ascii=False, indent=2),
        )
        return self._extract_message_text(response_payload)


class GroqTranslator(DeepCloudTranslatorBase):
    name = "groq"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        config: AppConfig | None = None,
        timeout_s: float = 2.5,
        verbose: bool = False,
        max_logged_items: int = 6,
    ) -> None:
        super().__init__(model, api_key, config, timeout_s=timeout_s, verbose=verbose, max_logged_items=max_logged_items)
        if not self._api_key:
            raise RuntimeError("Groq API key is required")
        try:
            from groq import Groq
        except Exception as exc:  # pragma: no cover - dependency import error
            raise RuntimeError("groq package is required for Groq deep translation") from exc
        self._client = Groq(api_key=self._api_key, timeout=self._timeout_s)

    def _create_chat_completion(self, messages: list[dict[str, str]]) -> object:
        return self._client.chat.completions.create(messages=messages, model=self._model)

    def _generate_batch_text(self, contents: str) -> str:
        payload = [{"role": "user", "content": contents}]
        self._log_verbose_block("groq batch request", json.dumps({"model": self._model, "messages": payload}, ensure_ascii=False, indent=2))
        response = self._create_chat_completion(payload)
        response_dict = self._normalize_response_payload(response)
        self._log_verbose_block("groq batch response raw", json.dumps(response_dict, ensure_ascii=False, indent=2))
        return self._extract_message_text(response)

    def _generate_deep_text(self, system_instruction: str, contents: str) -> str:
        payload = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": contents},
        ]
        self._log_verbose_block("groq deep request", json.dumps({"model": self._model, "messages": payload}, ensure_ascii=False, indent=2))
        response = self._create_chat_completion(payload)
        response_dict = self._normalize_response_payload(response)
        self._log_verbose_block("groq deep response raw", json.dumps(response_dict, ensure_ascii=False, indent=2))
        return self._extract_message_text(response)


class GeminiRestTranslator(GeminiTranslator):
    name = "gemini-rest"


def build_default_local_translator(config: AppConfig) -> TranslatorProvider:
    backend = config.local_translator_backend.strip().lower()
    if backend != "ctranslate2":
        print(f"[AutoTrans] Unsupported local translator '{backend}', forcing ctranslate2", flush=True)
    return CTranslate2Translator(config)
