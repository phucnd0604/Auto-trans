from __future__ import annotations

from dataclasses import dataclass
from os import cpu_count, getenv
from pathlib import Path
from urllib.parse import urlparse


_DEFAULT_MODEL_DIR = Path(getenv("AUTOTRANS_LOCAL_MODEL_DIR", ".models/opus-mt-en-vi-ctranslate2"))
_DEFAULT_INTRA_THREADS = str(max((cpu_count() or 4) - 1, 1))
_DEFAULT_ARGOS_PACKAGES_DIR = Path(getenv("AUTOTRANS_ARGOS_PACKAGES_DIR", ".models/argos-packages"))


@dataclass(slots=True)
class AppConfig:
    capture_fps: float = float(getenv("AUTOTRANS_CAPTURE_FPS", "4"))
    overlay_fps: int = int(getenv("AUTOTRANS_OVERLAY_FPS", "30"))
    mode: str = getenv("AUTOTRANS_TRANSLATION_MODE", "balanced")
    source_lang: str = getenv("AUTOTRANS_SOURCE_LANG", "en")
    target_lang: str = getenv("AUTOTRANS_TARGET_LANG", "vi")
    font_size: int = int(getenv("AUTOTRANS_FONT_SIZE", "18"))
    overlay_background_opacity: float = float(getenv("AUTOTRANS_OVERLAY_BG_OPACITY", "0.9"))
    overlay_box_padding: int = int(getenv("AUTOTRANS_OVERLAY_BOX_PADDING", "8"))
    overlay_ttl_seconds: float = float(getenv("AUTOTRANS_OVERLAY_TTL_SECONDS", "1.5"))
    translation_log_enabled: bool = getenv("AUTOTRANS_TRANSLATION_LOG_ENABLED", "1") != "0"
    translation_log_max_items: int = int(getenv("AUTOTRANS_TRANSLATION_LOG_MAX_ITEMS", "6"))
    translation_stable_scans: int = int(getenv("AUTOTRANS_TRANSLATION_STABLE_SCANS", "2"))
    glossary_version: str = getenv("AUTOTRANS_GLOSSARY_VERSION", "word-v1")
    subtitle_mode: bool = getenv("AUTOTRANS_SUBTITLE_MODE", "1") != "0"
    subtitle_region_top_ratio: float = float(getenv("AUTOTRANS_SUBTITLE_REGION_TOP_RATIO", "0.45"))
    subtitle_min_width_ratio: float = float(getenv("AUTOTRANS_SUBTITLE_MIN_WIDTH_RATIO", "0.08"))
    subtitle_min_chars: int = int(getenv("AUTOTRANS_SUBTITLE_MIN_CHARS", "6"))
    subtitle_max_candidates: int = int(getenv("AUTOTRANS_SUBTITLE_MAX_CANDIDATES", "4"))
    subtitle_hold_frames: int = int(getenv("AUTOTRANS_SUBTITLE_HOLD_FRAMES", "2"))
    ocr_provider: str = getenv("AUTOTRANS_OCR_PROVIDER", "paddle")
    ocr_languages: tuple[str, ...] = tuple(
        language.strip()
        for language in getenv("AUTOTRANS_OCR_LANGUAGES", "en,jp").split(",")
        if language.strip()
    )
    ocr_min_confidence: float = float(getenv("AUTOTRANS_OCR_MIN_CONFIDENCE", "0.45"))
    ocr_preprocess: bool = getenv("AUTOTRANS_OCR_PREPROCESS", "0") != "0"
    ocr_max_side: int = int(getenv("AUTOTRANS_OCR_MAX_SIDE", "1280"))
    ocr_max_boxes: int = int(getenv("AUTOTRANS_OCR_MAX_BOXES", "0"))
    paddle_ocr_version: str = getenv("AUTOTRANS_PADDLE_OCR_VERSION", "PP-OCRv5")
    paddle_use_textline_orientation: bool = getenv("AUTOTRANS_PADDLE_USE_TEXTLINE_ORIENTATION", "0") != "0"
    paddle_text_det_limit_side_len: int = int(getenv("AUTOTRANS_PADDLE_TEXT_DET_LIMIT_SIDE_LEN", "1536"))
    paddle_text_det_thresh: float = float(getenv("AUTOTRANS_PADDLE_TEXT_DET_THRESH", "0.2"))
    paddle_text_det_box_thresh: float = float(getenv("AUTOTRANS_PADDLE_TEXT_DET_BOX_THRESH", "0.35"))
    paddle_text_det_unclip_ratio: float = float(getenv("AUTOTRANS_PADDLE_TEXT_DET_UNCLIP_RATIO", "1.5"))
    paddle_text_rec_score_thresh: float = float(getenv("AUTOTRANS_PADDLE_TEXT_REC_SCORE_THRESH", "0.2"))
    ocr_crop_subtitle_only: bool = getenv("AUTOTRANS_OCR_CROP_SUBTITLE_ONLY", "1") != "0"
    overlay_source_text: bool = getenv("AUTOTRANS_OVERLAY_SOURCE_TEXT", "0") != "0"
    capture_backend: str = getenv("AUTOTRANS_CAPTURE_BACKEND", "mss")
    local_model_enabled: bool = getenv("AUTOTRANS_LOCAL_MODEL_ENABLED", "0") != "0"
    local_translator_backend: str = getenv("AUTOTRANS_LOCAL_TRANSLATOR", "argos")
    local_model_path: str | None = getenv("AUTOTRANS_LOCAL_MODEL_PATH") or None
    local_model_repo: str = getenv("AUTOTRANS_LOCAL_MODEL_REPO", "manancode/opus-mt-en-vi-ctranslate2-android")
    local_model_dir: Path = _DEFAULT_MODEL_DIR
    local_model_device: str = getenv("AUTOTRANS_LOCAL_MODEL_DEVICE", "cpu")
    local_model_compute_type: str = getenv("AUTOTRANS_LOCAL_MODEL_COMPUTE_TYPE", "int8")
    local_inter_threads: int = int(getenv("AUTOTRANS_LOCAL_INTER_THREADS", "1"))
    local_intra_threads: int = int(getenv("AUTOTRANS_LOCAL_INTRA_THREADS", _DEFAULT_INTRA_THREADS))
    local_target_prefix: str = getenv("AUTOTRANS_LOCAL_TARGET_PREFIX", ">>vie<<")
    argos_packages_dir: Path = _DEFAULT_ARGOS_PACKAGES_DIR
    argos_auto_install: bool = getenv("AUTOTRANS_ARGOS_AUTO_INSTALL", "1") != "0"
    cloud_provider: str = getenv("AUTOTRANS_CLOUD_PROVIDER", "none")
    openai_base_url: str = getenv("AUTOTRANS_OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_api_key: str | None = getenv("AUTOTRANS_OPENAI_API_KEY") or getenv("OPENAI_API_KEY") or None
    openai_model: str = getenv("AUTOTRANS_OPENAI_MODEL", "gpt-5-mini")
    cloud_timeout_ms: int = int(getenv("AUTOTRANS_CLOUD_TIMEOUT_MS", "2500"))
    local_max_chars_balanced: int = int(getenv("AUTOTRANS_LOCAL_MAX_CHARS_BALANCED", "64"))
    debounce_frames: int = int(getenv("AUTOTRANS_DEBOUNCE_FRAMES", "1"))
    cache_size: int = int(getenv("AUTOTRANS_CACHE_SIZE", "1024"))
    cache_root_dir: str = getenv("AUTOTRANS_CACHE_ROOT_DIR", "D:\\Games\\Cache_Trans")

    @property
    def translation_mode(self) -> str:
        return self.mode

    def cloud_is_localhost(self) -> bool:
        hostname = (urlparse(self.openai_base_url).hostname or "").lower()
        return hostname in {"localhost", "127.0.0.1", "::1"}

    def cloud_base_host(self) -> str:
        return (urlparse(self.openai_base_url).hostname or "").strip()


