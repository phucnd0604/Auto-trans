from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from autotrans.config import AppConfig
from autotrans.services.capture import WindowsWindowCapture
from autotrans.services.ocr import (
    FallbackOCRProvider,
    MockOCRProvider,
    PaddleOCRProvider,
    RapidOCRProvider,
)
from autotrans.services.orchestrator import PipelineOrchestrator
from autotrans.services.translation import OpenAITranslator, build_default_local_translator
from autotrans.ui.main_window import MainWindow
from autotrans.ui.overlay import OverlayWindow


def _build_ocr_provider(config: AppConfig):
    if config.ocr_provider == "rapidocr":
        try:
            provider = RapidOCRProvider(config)
            print("[AutoTrans] OCR provider: rapidocr", flush=True)
            return provider
        except Exception as exc:
            print(f"[AutoTrans] RapidOCR unavailable, falling back to mock OCR: {exc}", flush=True)
            return MockOCRProvider()

    if config.ocr_provider == "paddle":
        try:
            primary = PaddleOCRProvider(config)
            fallback = RapidOCRProvider(config)
            print("[AutoTrans] OCR provider: paddle with rapidocr fallback", flush=True)
            return FallbackOCRProvider(primary, fallback)
        except Exception as exc:
            print(f"[AutoTrans] PaddleOCR unavailable, falling back to RapidOCR: {exc}", flush=True)
            try:
                provider = RapidOCRProvider(config)
                print("[AutoTrans] OCR provider: rapidocr", flush=True)
                return provider
            except Exception as rapid_exc:
                print(f"[AutoTrans] RapidOCR unavailable, falling back to mock OCR: {rapid_exc}", flush=True)
                return MockOCRProvider()

    print("[AutoTrans] OCR provider: mock", flush=True)
    return MockOCRProvider()


def _build_local_translator(config: AppConfig):
    provider = build_default_local_translator(config)
    print(f"[AutoTrans] Local translator: {provider.name}", flush=True)
    return provider


def _build_cloud_translator(config: AppConfig):
    if config.cloud_provider == "openai":
        try:
            return OpenAITranslator(
                model=config.openai_model,
                base_url=config.openai_base_url,
                api_key=config.openai_api_key,
                verbose=config.translation_log_enabled,
                max_logged_items=config.translation_log_max_items,
            )
        except Exception as exc:
            print(f"[AutoTrans] Cloud translator unavailable: {exc}", flush=True)
            return None
    return None


def main() -> int:
    app = QApplication(sys.argv)
    config = AppConfig()
    capture_service = WindowsWindowCapture(config)
    overlay = OverlayWindow(ttl_seconds=config.overlay_ttl_seconds)
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
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

