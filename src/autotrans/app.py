from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QApplication

from autotrans.config import AppConfig
from autotrans.services.capture import WindowsWindowCapture
from autotrans.services.ocr import (
    PaddleOCRProvider,
)
from autotrans.services.orchestrator import PipelineOrchestrator
from autotrans.services.translation import GeminiRestTranslator, GroqTranslator, build_default_local_translator
from autotrans.ui.global_hotkeys import GlobalHotkeyManager
from autotrans.ui.main_window import MainWindow
from autotrans.ui.overlay import OverlayWindow
from autotrans.ui.settings_dialog import SettingsDialog, load_startup_settings
from autotrans.utils.runtime_diagnostics import RuntimeDiagnostics
from autotrans.utils.runtime_logging import setup_runtime_logging


def _install_global_exception_hooks(diagnostics: RuntimeDiagnostics | None = None) -> None:
    previous_sys_hook = sys.excepthook
    previous_thread_hook = getattr(threading, "excepthook", None)

    def _log_uncaught_exception(
        source: str,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback,
        *,
        thread_name: str | None = None,
    ) -> None:
        details = {
            "source": source,
            "thread_name": thread_name or threading.current_thread().name,
            "exception_type": getattr(exc_type, "__name__", str(exc_type)),
            "exception": repr(exc_value),
        }
        formatted_traceback = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print(
            f"[AutoTrans] Uncaught exception source={source} thread={details['thread_name']}: {details['exception']}",
            flush=True,
        )
        print(formatted_traceback, flush=True)
        if diagnostics is not None:
            diagnostics.record_event(
                "uncaught_exception",
                "Uncaught Python exception",
                details=details,
                snapshot={"traceback": formatted_traceback},
            )
            diagnostics.close()

    def _sys_excepthook(exc_type, exc_value, exc_traceback) -> None:
        _log_uncaught_exception("sys.excepthook", exc_type, exc_value, exc_traceback)
        if previous_sys_hook is not None:
            previous_sys_hook(exc_type, exc_value, exc_traceback)

    def _thread_excepthook(args) -> None:
        _log_uncaught_exception(
            "threading.excepthook",
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            thread_name=args.thread.name if args.thread is not None else None,
        )
        if callable(previous_thread_hook):
            previous_thread_hook(args)

    sys.excepthook = _sys_excepthook
    if callable(previous_thread_hook):
        threading.excepthook = _thread_excepthook


class _LazyOCRProvider:
    def __init__(self, provider_name: str, factory: Callable[[], object]) -> None:
        self._provider_name = provider_name
        self._factory = factory
        self._instance = None
        self._init_error: Exception | None = None
        self._init_lock = threading.Lock()

    @property
    def name(self) -> str:
        if self._instance is not None:
            return getattr(self._instance, "name", self._provider_name)
        return self._provider_name

    def _get_instance(self):
        if self._instance is not None:
            return self._instance
        if self._init_error is not None:
            raise RuntimeError(
                f"OCR provider '{self._provider_name}' initialization previously failed"
            ) from self._init_error

        if self._instance is None:
            with self._init_lock:
                if self._instance is not None:
                    return self._instance
                if self._init_error is not None:
                    raise RuntimeError(
                        f"OCR provider '{self._provider_name}' initialization previously failed"
                    ) from self._init_error
                started = time.perf_counter()
                print(f"[AutoTrans] Initializing OCR provider: {self._provider_name}", flush=True)
                try:
                    self._instance = self._factory()
                except Exception as exc:
                    self._init_error = exc
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    print(
                        f"[AutoTrans] OCR provider init failed: {self._provider_name} ({elapsed_ms:.1f}ms): {exc}",
                        flush=True,
                    )
                    traceback.print_exc()
                    raise
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                print(f"[AutoTrans] OCR provider ready: {self._provider_name} ({elapsed_ms:.1f}ms)", flush=True)
        return self._instance

    def recognize(self, frame):
        return self._get_instance().recognize(frame)

    def recognize_paragraphs(self, frame):
        return self._get_instance().recognize_paragraphs(frame)


class _LazyTranslatorProvider:
    def __init__(self, provider_name: str, factory: Callable[[], object]) -> None:
        self._provider_name = provider_name
        self._factory = factory
        self._instance = None

    @property
    def name(self) -> str:
        if self._instance is not None:
            return getattr(self._instance, "name", self._provider_name)
        return self._provider_name

    def _get_instance(self):
        if self._instance is None:
            started = time.perf_counter()
            print(f"[AutoTrans] Initializing translator: {self._provider_name}", flush=True)
            self._instance = self._factory()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            print(f"[AutoTrans] Translator ready: {self._provider_name} ({elapsed_ms:.1f}ms)", flush=True)
        return self._instance

    def translate_batch(self, items, source_lang: str, target_lang: str, mode):
        return self._get_instance().translate_batch(items, source_lang, target_lang, mode)

    def translate_screen_blocks(self, items, source_lang: str, target_lang: str):
        return self._get_instance().translate_screen_blocks(items, source_lang, target_lang)


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


def _prepare_runtime_environment(config: AppConfig) -> RuntimeDiagnostics:
    runtime_dirs = [
        config.runtime_root_dir,
        config.local_model_dir,
        config.cache_root_dir,
        config.xdg_data_home,
        config.xdg_cache_home,
        config.xdg_config_home,
        config.hf_home,
        config.paddle_cache_dir,
        config.log_dir,
    ]
    for path in runtime_dirs:
        path.mkdir(parents=True, exist_ok=True)

    os.environ["XDG_DATA_HOME"] = str(config.xdg_data_home.resolve())
    os.environ["XDG_CACHE_HOME"] = str(config.xdg_cache_home.resolve())
    os.environ["XDG_CONFIG_HOME"] = str(config.xdg_config_home.resolve())
    os.environ["HF_HOME"] = str(config.hf_home.resolve())
    os.environ["PADDLE_HOME"] = str(config.paddle_cache_dir.resolve())
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(config.paddle_cache_dir.resolve())

    setup_runtime_logging(config)
    diagnostics = RuntimeDiagnostics(config)
    print(f"[AutoTrans] Runtime root: {config.runtime_root_dir}", flush=True)
    print(f"[AutoTrans] Cache root: {config.cache_root_dir}", flush=True)
    print(f"[AutoTrans] Paddle cache root: {config.paddle_cache_dir}", flush=True)
    if diagnostics.is_enabled():
        print(f"[AutoTrans] Diagnostics session: {diagnostics.session_path}", flush=True)
        diagnostics.record_event(
            "session_started",
            "Runtime diagnostics session started",
            details={"session_path": diagnostics.session_path},
        )
    return diagnostics


def _build_realtime_ocr_provider(config: AppConfig):
    if config.ocr_provider != "paddleocr":
        raise ValueError(f"Unsupported realtime OCR provider: {config.ocr_provider}")
    print("[AutoTrans] Realtime OCR provider selected: paddleocr (lazy)", flush=True)
    return _LazyOCRProvider("paddleocr", lambda: PaddleOCRProvider(config))


def _build_deep_ocr_provider(config: AppConfig):
    print("[AutoTrans] Deep OCR provider selected: paddleocr (lazy)", flush=True)
    return _LazyOCRProvider("paddleocr", lambda: PaddleOCRProvider(config, deep_mode=True))


def _normalize_deep_provider_name(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized in {"openai", "gemini-rest", "gemini"}:
        return "gemini"
    if normalized == "groq":
        return "groq"
    return normalized


def _build_local_translator(config: AppConfig):
    print("[AutoTrans] Local translator selected: ctranslate2 (lazy)", flush=True)
    return _LazyTranslatorProvider("local-ctranslate2", lambda: build_default_local_translator(config))


def _mask_api_key(api_key: str | None) -> str:
    if not api_key:
        return "missing"
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:4]}...{api_key[-4:]}"


def _build_cloud_translator(config: AppConfig, diagnostics: RuntimeDiagnostics | None = None):
    provider = _normalize_deep_provider_name(config.deep_translation_provider)
    config.deep_translation_provider = provider
    print(
        "[AutoTrans] Cloud translator config: "
        f"provider={provider} "
        f"model={config.deep_translation_model} "
        f"transport={config.deep_translation_transport} "
        f"api_key={_mask_api_key(config.deep_translation_api_key)}",
        flush=True,
    )
    if not config.deep_translation_api_key:
        print("[AutoTrans] Deep translator: disabled, fallback to ctranslate2", flush=True)
        if diagnostics is not None:
            diagnostics.record_event(
                "deep_translator_disabled",
                "Deep translator disabled, using local fallback",
                details={"provider": provider, "model": config.deep_translation_model, "reason": "missing_api_key"},
            )
        return None

    try:
        config.deep_translation_transport = "rest"
        if provider == "groq":
            translator = GroqTranslator(
                model=config.deep_translation_model,
                api_key=config.deep_translation_api_key,
                config=config,
                timeout_s=config.deep_translation_timeout_ms / 1000.0,
                verbose=config.runtime_verbose_log,
                max_logged_items=config.translation_log_max_items,
            )
        elif provider == "gemini":
            translator = GeminiRestTranslator(
                model=config.deep_translation_model,
                api_key=config.deep_translation_api_key,
                config=config,
                timeout_s=config.deep_translation_timeout_ms / 1000.0,
                verbose=config.runtime_verbose_log,
                max_logged_items=config.translation_log_max_items,
            )
        else:
            raise ValueError(f"Unsupported deep translation provider: {config.deep_translation_provider}")
        print(
            f"[AutoTrans] Deep translator: {translator.name} provider={provider} model={config.deep_translation_model}",
            flush=True,
        )
        if diagnostics is not None:
            diagnostics.record_event(
                "deep_translator_ready",
                "Deep translator initialized",
                details={"provider": provider, "model": config.deep_translation_model, "translator": translator.name},
            )
        return translator
    except Exception as exc:
        print(
            "[AutoTrans] Deep translator unavailable, fallback to ctranslate2: "
            f"provider={provider} model={config.deep_translation_model} error={exc!r}",
            flush=True,
        )
        traceback.print_exc()
        if diagnostics is not None:
            diagnostics.record_event(
                "deep_translator_unavailable",
                "Deep translator unavailable, using local fallback",
                details={"provider": provider, "model": config.deep_translation_model, "error": repr(exc)},
            )
        return None


def _warmup_ocr_providers(providers: list[object]) -> None:
    for provider in providers:
        warmup = getattr(provider, "_get_instance", None)
        provider_name = getattr(provider, "name", provider.__class__.__name__)
        if not callable(warmup):
            continue
        try:
            print(f"[AutoTrans] OCR warmup starting: {provider_name}", flush=True)
            warmup()
            print(f"[AutoTrans] OCR warmup finished: {provider_name}", flush=True)
        except Exception as exc:
            print(f"[AutoTrans] OCR warmup skipped after failure: {provider_name}: {exc}", flush=True)


def _warmup_ocr_providers_async(*providers: object) -> threading.Thread:
    worker = threading.Thread(
        target=_warmup_ocr_providers,
        args=([provider for provider in providers if provider is not None],),
        daemon=True,
        name="autotrans-ocr-warmup",
    )
    worker.start()
    return worker


def _apply_startup_settings(config: AppConfig, settings: dict[str, object]) -> AppConfig:
    config.ocr_provider = "paddleocr"
    config.capture_backend = str(settings.get("capture_backend", config.capture_backend))
    config.local_translator_backend = "ctranslate2"
    raw_api_key = str(settings.get("deep_translation_api_key", config.deep_translation_api_key or "")).strip()
    config.deep_translation_api_key = raw_api_key or None
    provider = str(settings.get("deep_translation_provider", config.deep_translation_provider)).strip()
    config.deep_translation_provider = _normalize_deep_provider_name(provider)
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
    config.runtime_verbose_log = bool(
        settings.get("runtime_verbose_log", settings.get("translation_log_enabled", config.runtime_verbose_log))
    )
    config.diagnostics_enabled = bool(settings.get("diagnostics_enabled", config.diagnostics_enabled))
    config.diagnostics_trigger_threshold_ms = int(
        settings.get("diagnostics_trigger_threshold_ms", config.diagnostics_trigger_threshold_ms)
    )
    config.font_size = int(settings.get("font_size", config.font_size))
    return config


def main() -> int:
    startup_started = time.perf_counter()

    def log_startup_step(label: str, started: float) -> None:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        print(f"[AutoTrans][Startup] {label}: {elapsed_ms:.1f}ms", flush=True)

    _clear_runtime_path_overrides()
    step_started = time.perf_counter()
    app = QApplication(sys.argv)
    log_startup_step("QApplication init", step_started)

    step_started = time.perf_counter()
    config = AppConfig()
    log_startup_step("AppConfig init", step_started)

    settings_path = Path(config.runtime_root_dir) / "ui-settings.json"
    step_started = time.perf_counter()
    initial_settings = load_startup_settings(settings_path)
    log_startup_step("load_startup_settings", step_started)

    step_started = time.perf_counter()
    settings_dialog = SettingsDialog(settings_path=settings_path, initial_settings=initial_settings)
    log_startup_step("SettingsDialog init", step_started)

    if settings_dialog.exec() == 0:
        return 0

    step_started = time.perf_counter()
    config = _apply_startup_settings(config, settings_dialog.values())
    log_startup_step("apply_startup_settings", step_started)

    step_started = time.perf_counter()
    diagnostics = _prepare_runtime_environment(config)
    _install_global_exception_hooks(diagnostics)
    log_startup_step("prepare_runtime_environment", step_started)

    step_started = time.perf_counter()
    capture_service = WindowsWindowCapture(config)
    log_startup_step("WindowsWindowCapture init", step_started)

    step_started = time.perf_counter()
    overlay = OverlayWindow(ttl_seconds=config.overlay_ttl_seconds, overlay_fps=config.overlay_fps)
    log_startup_step("OverlayWindow init", step_started)

    step_started = time.perf_counter()
    hotkeys = GlobalHotkeyManager()
    app.installNativeEventFilter(hotkeys)
    log_startup_step("GlobalHotkeyManager init", step_started)

    step_started = time.perf_counter()
    realtime_ocr_provider = _build_realtime_ocr_provider(config)
    deep_ocr_provider = _build_deep_ocr_provider(config)
    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=capture_service,
        ocr_provider=realtime_ocr_provider,
        deep_ocr_provider=deep_ocr_provider,
        local_translator=_build_local_translator(config),
        cloud_translator=_build_cloud_translator(config, diagnostics),
        diagnostics=diagnostics,
    )
    log_startup_step("PipelineOrchestrator init", step_started)

    step_started = time.perf_counter()
    window = MainWindow(
        config=config,
        capture_service=capture_service,
        orchestrator=orchestrator,
        overlay=overlay,
        global_hotkeys=hotkeys,
        diagnostics=diagnostics,
    )
    log_startup_step("MainWindow init", step_started)

    print(
        f"[AutoTrans][Startup] app ready in {(time.perf_counter() - startup_started) * 1000.0:.1f}ms",
        flush=True,
    )
    window.show()
    _warmup_ocr_providers_async(realtime_ocr_provider, deep_ocr_provider)
    try:
        return app.exec()
    finally:
        diagnostics.close()
        hotkeys.unregister_all()


if __name__ == "__main__":
    raise SystemExit(main())
