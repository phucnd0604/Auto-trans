from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from autotrans.config import AppConfig
from autotrans.services.capture import WindowsWindowCapture
from autotrans.services.ocr import (
    MockOCRProvider,
    RapidOCRProvider,
)
from autotrans.services.orchestrator import PipelineOrchestrator
from autotrans.services.translation import GeminiRestTranslator, build_default_local_translator
from autotrans.ui.global_hotkeys import GlobalHotkeyManager
from autotrans.ui.main_window import MainWindow
from autotrans.ui.overlay import OverlayWindow
from autotrans.ui.settings_dialog import SettingsDialog, load_startup_settings
from autotrans.utils.runtime_logging import setup_runtime_logging


def _clear_runtime_path_overrides() -> None:
    for key in (
        "AUTOTRANS_RUNTIME_ROOT_DIR",
        "AUTOTRANS_LOCAL_MODEL_DIR",
        "AUTOTRANS_CACHE_ROOT_DIR",
        "AUTOTRANS_XDG_DATA_HOME",
        "AUTOTRANS_XDG_CACHE_HOME",
        "AUTOTRANS_XDG_CONFIG_HOME",
        "AUTOTRANS_HF_HOME",
    ):
        os.environ.pop(key, None)


def _prepare_runtime_environment(config: AppConfig) -> None:
    runtime_dirs = [
        config.runtime_root_dir,
        config.local_model_dir,
        config.cache_root_dir,
        config.xdg_data_home,
        config.xdg_cache_home,
        config.xdg_config_home,
        config.hf_home,
        config.log_dir,
    ]
    for path in runtime_dirs:
        path.mkdir(parents=True, exist_ok=True)

    os.environ["XDG_DATA_HOME"] = str(config.xdg_data_home.resolve())
    os.environ["XDG_CACHE_HOME"] = str(config.xdg_cache_home.resolve())
    os.environ["XDG_CONFIG_HOME"] = str(config.xdg_config_home.resolve())
    os.environ["HF_HOME"] = str(config.hf_home.resolve())

    setup_runtime_logging(config)
    print(f"[AutoTrans] Runtime root: {config.runtime_root_dir}", flush=True)
    print(f"[AutoTrans] Cache root: {config.cache_root_dir}", flush=True)


def _build_ocr_provider(config: AppConfig):
    if config.ocr_provider == "rapidocr":
        try:
            provider = RapidOCRProvider(config)
            print("[AutoTrans] OCR provider: rapidocr", flush=True)
            return provider
        except Exception as exc:
            print(f"[AutoTrans] RapidOCR unavailable, falling back to mock OCR: {exc}", flush=True)
            return MockOCRProvider()

    print("[AutoTrans] OCR provider: mock", flush=True)
    return MockOCRProvider()


def _build_local_translator(config: AppConfig):
    provider = build_default_local_translator(config)
    print("[AutoTrans] Local translator: ctranslate2", flush=True)
    return provider


def _build_cloud_translator(config: AppConfig):
    if not config.deep_translation_api_key:
        print("[AutoTrans] Deep translator: disabled, fallback to ctranslate2", flush=True)
        return None

    try:
        config.deep_translation_transport = "rest"
        translator = GeminiRestTranslator(
            model=config.deep_translation_model,
            api_key=config.deep_translation_api_key,
            config=config,
            timeout_s=config.deep_translation_timeout_ms / 1000.0,
            verbose=config.translation_log_enabled,
            max_logged_items=config.translation_log_max_items,
        )
        print(
            f"[AutoTrans] Deep translator: {translator.name} model={config.deep_translation_model}",
            flush=True,
        )
        return translator
    except Exception as exc:
        print(f"[AutoTrans] Deep translator unavailable, fallback to ctranslate2: {exc}", flush=True)
        return None


def _apply_startup_settings(config: AppConfig, settings: dict[str, object]) -> AppConfig:
    config.ocr_provider = str(settings.get("ocr_provider", config.ocr_provider))
    config.capture_backend = str(settings.get("capture_backend", config.capture_backend))
    config.local_translator_backend = "ctranslate2"
    raw_api_key = str(settings.get("deep_translation_api_key", config.deep_translation_api_key or "")).strip()
    config.deep_translation_api_key = raw_api_key or None
    config.deep_translation_model = (
        str(settings.get("deep_translation_model", config.deep_translation_model)).strip()
        or config.deep_translation_model
    )
    config.deep_translation_transport = "rest"
    config.game_profile_title = str(settings.get("game_profile_title", config.game_profile_title)).strip()
    config.game_profile_world = str(settings.get("game_profile_world", config.game_profile_world)).strip()
    config.game_profile_factions = str(settings.get("game_profile_factions", config.game_profile_factions)).strip()
    config.game_profile_characters_honorifics = str(
        settings.get("game_profile_characters_honorifics", config.game_profile_characters_honorifics)
    ).strip()
    config.game_profile_terms_items_skills = str(
        settings.get("game_profile_terms_items_skills", config.game_profile_terms_items_skills)
    ).strip()
    config.subtitle_mode = bool(settings.get("subtitle_mode", config.subtitle_mode))
    config.ocr_crop_subtitle_only = bool(settings.get("ocr_crop_subtitle_only", config.ocr_crop_subtitle_only))
    config.capture_fps = float(settings.get("capture_fps", config.capture_fps))
    config.overlay_fps = int(settings.get("overlay_fps", config.overlay_fps))
    config.overlay_ttl_seconds = float(settings.get("overlay_ttl_seconds", config.overlay_ttl_seconds))
    config.translation_log_enabled = bool(settings.get("translation_log_enabled", config.translation_log_enabled))
    config.font_size = int(settings.get("font_size", config.font_size))
    return config


def main() -> int:
    _clear_runtime_path_overrides()
    app = QApplication(sys.argv)
    config = AppConfig()
    settings_path = Path(config.runtime_root_dir) / "ui-settings.json"
    initial_settings = load_startup_settings(settings_path)
    settings_dialog = SettingsDialog(settings_path=settings_path, initial_settings=initial_settings)
    if settings_dialog.exec() == 0:
        return 0

    config = _apply_startup_settings(config, settings_dialog.values())
    _prepare_runtime_environment(config)
    capture_service = WindowsWindowCapture(config)
    overlay = OverlayWindow(ttl_seconds=config.overlay_ttl_seconds, overlay_fps=config.overlay_fps)
    hotkeys = GlobalHotkeyManager()
    app.installNativeEventFilter(hotkeys)
    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=capture_service,
        ocr_provider=_build_ocr_provider(config),
        local_translator=_build_local_translator(config),
        cloud_translator=_build_cloud_translator(config),
    )
    window = MainWindow(
        config=config,
        capture_service=capture_service,
        orchestrator=orchestrator,
        overlay=overlay,
        global_hotkeys=hotkeys,
    )
    window.show()
    try:
        return app.exec()
    finally:
        hotkeys.unregister_all()


if __name__ == "__main__":
    raise SystemExit(main())
