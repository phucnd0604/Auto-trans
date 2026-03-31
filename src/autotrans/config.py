from __future__ import annotations

import sys
from dataclasses import dataclass
from os import cpu_count, getenv
from pathlib import Path


def _default_app_root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _resolve_from_app_root(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (_default_app_root_dir() / path).resolve()


_DEFAULT_RUNTIME_ROOT_DIR = _resolve_from_app_root(getenv("AUTOTRANS_RUNTIME_ROOT_DIR", ".runtime"))
_DEFAULT_MODEL_DIR = Path(
    getenv(
        "AUTOTRANS_LOCAL_MODEL_DIR",
        str(_DEFAULT_RUNTIME_ROOT_DIR / "models" / "quickmt-en-vi"),
    )
)
_DEFAULT_CACHE_ROOT_DIR = Path(
    getenv(
        "AUTOTRANS_CACHE_ROOT_DIR",
        str(_DEFAULT_RUNTIME_ROOT_DIR / "translation-cache"),
    )
)
_DEFAULT_XDG_DATA_HOME = Path(
    getenv(
        "AUTOTRANS_XDG_DATA_HOME",
        str(_DEFAULT_RUNTIME_ROOT_DIR / "xdg" / "data"),
    )
)
_DEFAULT_XDG_CACHE_HOME = Path(
    getenv(
        "AUTOTRANS_XDG_CACHE_HOME",
        str(_DEFAULT_RUNTIME_ROOT_DIR / "xdg" / "cache"),
    )
)
_DEFAULT_XDG_CONFIG_HOME = Path(
    getenv(
        "AUTOTRANS_XDG_CONFIG_HOME",
        str(_DEFAULT_RUNTIME_ROOT_DIR / "xdg" / "config"),
    )
)
_DEFAULT_HF_HOME = Path(
    getenv(
        "AUTOTRANS_HF_HOME",
        str(_DEFAULT_RUNTIME_ROOT_DIR / "huggingface"),
    )
)
_DEFAULT_LOG_DIR = Path(
    getenv(
        "AUTOTRANS_LOG_DIR",
        str(_DEFAULT_RUNTIME_ROOT_DIR / "logs"),
    )
)
_DEFAULT_INTRA_THREADS = str(max((cpu_count() or 4) - 1, 1))


@dataclass(slots=True)
class AppConfig:
    runtime_root_dir: Path = _DEFAULT_RUNTIME_ROOT_DIR
    capture_fps: float = float(getenv("AUTOTRANS_CAPTURE_FPS", "4"))
    overlay_fps: int = int(getenv("AUTOTRANS_OVERLAY_FPS", "30"))
    mode: str = getenv("AUTOTRANS_TRANSLATION_MODE", "balanced")
    source_lang: str = getenv("AUTOTRANS_SOURCE_LANG", "en")
    target_lang: str = getenv("AUTOTRANS_TARGET_LANG", "vi")
    font_size: int = int(getenv("AUTOTRANS_FONT_SIZE", "18"))
    overlay_background_opacity: float = float(getenv("AUTOTRANS_OVERLAY_BG_OPACITY", "0.9"))
    overlay_box_padding: int = int(getenv("AUTOTRANS_OVERLAY_BOX_PADDING", "8"))
    overlay_ttl_seconds: float = float(getenv("AUTOTRANS_OVERLAY_TTL_SECONDS", "1.5"))
    overlay_max_groups: int = int(getenv("AUTOTRANS_OVERLAY_MAX_GROUPS", "8"))
    translation_log_enabled: bool = getenv("AUTOTRANS_TRANSLATION_LOG_ENABLED", "1") != "0"
    translation_log_max_items: int = int(getenv("AUTOTRANS_TRANSLATION_LOG_MAX_ITEMS", "6"))
    translation_stable_scans: int = int(getenv("AUTOTRANS_TRANSLATION_STABLE_SCANS", "2"))
    glossary_version: str = getenv("AUTOTRANS_GLOSSARY_VERSION", "word-v1")
    subtitle_mode: bool = getenv("AUTOTRANS_SUBTITLE_MODE", "1") != "0"
    subtitle_region_top_ratio: float = float(getenv("AUTOTRANS_SUBTITLE_REGION_TOP_RATIO", "0.70"))
    subtitle_center_tolerance_px: int = int(getenv("AUTOTRANS_SUBTITLE_CENTER_TOLERANCE_PX", "400"))
    subtitle_min_width_ratio: float = float(getenv("AUTOTRANS_SUBTITLE_MIN_WIDTH_RATIO", "0.08"))
    subtitle_min_chars: int = int(getenv("AUTOTRANS_SUBTITLE_MIN_CHARS", "6"))
    subtitle_max_candidates: int = int(getenv("AUTOTRANS_SUBTITLE_MAX_CANDIDATES", "4"))
    subtitle_hold_frames: int = int(getenv("AUTOTRANS_SUBTITLE_HOLD_FRAMES", "2"))
    ocr_provider: str = getenv("AUTOTRANS_OCR_PROVIDER", "rapidocr")
    ocr_languages: tuple[str, ...] = tuple(
        language.strip()
        for language in getenv("AUTOTRANS_OCR_LANGUAGES", "en,jp").split(",")
        if language.strip()
    )
    ocr_min_confidence: float = float(getenv("AUTOTRANS_OCR_MIN_CONFIDENCE", "0.45"))
    ocr_preprocess: bool = getenv("AUTOTRANS_OCR_PREPROCESS", "0") != "0"
    ocr_max_side: int = int(getenv("AUTOTRANS_OCR_MAX_SIDE", "960"))
    ocr_max_boxes: int = int(getenv("AUTOTRANS_OCR_MAX_BOXES", "0"))
    ocr_crop_subtitle_only: bool = getenv("AUTOTRANS_OCR_CROP_SUBTITLE_ONLY", "1") != "0"
    overlay_source_text: bool = getenv("AUTOTRANS_OVERLAY_SOURCE_TEXT", "0") != "0"
    capture_backend: str = getenv("AUTOTRANS_CAPTURE_BACKEND", "mss")
    local_model_enabled: bool = getenv("AUTOTRANS_LOCAL_MODEL_ENABLED", "0") != "0"
    local_translator_backend: str = "ctranslate2"
    local_model_path: str | None = getenv("AUTOTRANS_LOCAL_MODEL_PATH") or None
    local_model_repo: str = getenv("AUTOTRANS_LOCAL_MODEL_REPO", "quickmt/quickmt-en-vi")
    local_model_dir: Path = _DEFAULT_MODEL_DIR
    local_model_device: str = getenv("AUTOTRANS_LOCAL_MODEL_DEVICE", "cpu")
    local_model_compute_type: str = getenv("AUTOTRANS_LOCAL_MODEL_COMPUTE_TYPE", "int8")
    local_inter_threads: int = int(getenv("AUTOTRANS_LOCAL_INTER_THREADS", "1"))
    local_intra_threads: int = int(getenv("AUTOTRANS_LOCAL_INTRA_THREADS", _DEFAULT_INTRA_THREADS))
    local_target_prefix: str = getenv("AUTOTRANS_LOCAL_TARGET_PREFIX", ">>vie<<")
    xdg_data_home: Path = _DEFAULT_XDG_DATA_HOME
    xdg_cache_home: Path = _DEFAULT_XDG_CACHE_HOME
    xdg_config_home: Path = _DEFAULT_XDG_CONFIG_HOME
    hf_home: Path = _DEFAULT_HF_HOME
    log_dir: Path = _DEFAULT_LOG_DIR
    log_max_lines: int = int(getenv("AUTOTRANS_LOG_MAX_LINES", "10000"))
    log_trim_to_lines: int = int(getenv("AUTOTRANS_LOG_TRIM_TO_LINES", "5000"))
    deep_translation_api_key: str | None = getenv("AUTOTRANS_DEEP_TRANSLATION_API_KEY") or None
    deep_translation_model: str = getenv("AUTOTRANS_DEEP_TRANSLATION_MODEL", "gemini-2.0-flash")
    deep_translation_transport: str = getenv("AUTOTRANS_DEEP_TRANSLATION_TRANSPORT", "rest")
    game_profile_title: str = getenv("AUTOTRANS_GAME_PROFILE_TITLE", "")
    game_profile_world: str = getenv("AUTOTRANS_GAME_PROFILE_WORLD", "")
    game_profile_factions: str = getenv("AUTOTRANS_GAME_PROFILE_FACTIONS", "")
    game_profile_characters_honorifics: str = getenv("AUTOTRANS_GAME_PROFILE_CHARACTERS_HONORIFICS", "")
    game_profile_terms_items_skills: str = getenv("AUTOTRANS_GAME_PROFILE_TERMS_ITEMS_SKILLS", "")
    cloud_timeout_ms: int = int(getenv("AUTOTRANS_CLOUD_TIMEOUT_MS", "2500"))
    deep_translation_timeout_ms: int = int(getenv("AUTOTRANS_DEEP_TRANSLATION_TIMEOUT_MS", "90000"))
    debounce_frames: int = int(getenv("AUTOTRANS_DEBOUNCE_FRAMES", "1"))
    cache_size: int = int(getenv("AUTOTRANS_CACHE_SIZE", "1024"))
    cache_root_dir: Path = _DEFAULT_CACHE_ROOT_DIR

    def __post_init__(self) -> None:
        self.runtime_root_dir = _resolve_from_app_root(self.runtime_root_dir)
        self.local_model_dir = _resolve_from_app_root(self.local_model_dir)
        self.cache_root_dir = _resolve_from_app_root(self.cache_root_dir)
        self.xdg_data_home = _resolve_from_app_root(self.xdg_data_home)
        self.xdg_cache_home = _resolve_from_app_root(self.xdg_cache_home)
        self.xdg_config_home = _resolve_from_app_root(self.xdg_config_home)
        self.hf_home = _resolve_from_app_root(self.hf_home)
        self.log_dir = _resolve_from_app_root(self.log_dir)

    @property
    def translation_mode(self) -> str:
        return self.mode

    @staticmethod
    def deep_translation_host() -> str:
        return "generativelanguage.googleapis.com"


