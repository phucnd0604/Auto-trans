from __future__ import annotations

import numpy as np

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, OverlayItem, OverlayStyle, Rect, TranslationResult
from autotrans.services.orchestrator import PipelineOrchestrator
from autotrans.services.translation import OpenAITranslator, WordByWordTranslator
from autotrans.ui.overlay import OverlayWindow


class StubCaptureService:
    def __init__(self, frame: Frame | None) -> None:
        self._frame = frame

    def capture_window(self, hwnd: int) -> Frame | None:
        return self._frame


class StubOCRProvider:
    def __init__(self, boxes: list[OCRBox]) -> None:
        self._boxes = boxes

    def recognize(self, frame: Frame) -> list[OCRBox]:
        return list(self._boxes)


class StubCloudTranslator(OpenAITranslator):
    def __init__(self) -> None:
        self._model = "test-model"
        self._timeout_s = 15.0
        self._verbose = False
        self._max_logged_items = 0

    def translate_screen_blocks(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
    ):
        return [
            TranslationResult(
                source_text=item.source_text,
                translated_text=f"VI: {item.source_text}",
                provider="cloud",
                latency_ms=10.0,
            )
            for item in items
        ]


def _make_config() -> AppConfig:
    config = AppConfig()
    config.openai_api_key = "test-key"
    config.cloud_provider = "openai"
    config.openai_base_url = "http://localhost:11434/v1"
    config.translation_log_enabled = False
    config.subtitle_mode = True
    return config


def _make_frame() -> Frame:
    return Frame(
        image=np.zeros((300, 400, 3), dtype=np.uint8),
        timestamp=0.0,
        window_rect=Rect(x=0, y=0, width=400, height=300),
    )


def test_process_window_deep_falls_back_to_local_without_cloud() -> None:
    config = _make_config()
    config.cloud_provider = "none"
    config.openai_api_key = None
    boxes = [
        OCRBox(
            id="a",
            source_text="Quest Objective",
            confidence=0.9,
            bbox=Rect(x=20, y=30, width=160, height=28),
        ),
    ]
    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=StubCaptureService(_make_frame()),
        ocr_provider=StubOCRProvider(boxes),
        local_translator=WordByWordTranslator(),
        cloud_translator=None,
    )

    items = orchestrator.process_window_deep(100)

    assert items
    assert items[0].translated_text


def test_process_window_deep_returns_overlay_items_from_cloud() -> None:
    config = _make_config()
    boxes = [
        OCRBox(
            id="a",
            source_text="Quest Objective",
            confidence=0.9,
            bbox=Rect(x=20, y=30, width=160, height=28),
        ),
        OCRBox(
            id="b",
            source_text="Find the lost relic",
            confidence=0.9,
            bbox=Rect(x=20, y=64, width=220, height=28),
        ),
    ]
    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=StubCaptureService(_make_frame()),
        ocr_provider=StubOCRProvider(boxes),
        local_translator=WordByWordTranslator(),
        cloud_translator=StubCloudTranslator(),
    )

    items = orchestrator.process_window_deep(100)

    assert items
    assert all(item.region == "deep-ui" for item in items)
    assert all(item.translated_text.startswith("VI:") for item in items)


def test_overlay_keeps_persistent_items_after_live_items_clear(qtbot) -> None:
    overlay = OverlayWindow()
    qtbot.addWidget(overlay)
    style = OverlayStyle()
    persistent = OverlayItem(
        bbox=Rect(x=10, y=10, width=100, height=40),
        translated_text="Persistent",
        style=style,
        region="deep-ui",
    )
    live = OverlayItem(
        bbox=Rect(x=20, y=80, width=100, height=40),
        translated_text="Live",
        style=style,
        region="subtitle",
        tracking_key="live-1",
        linger_seconds=1.0,
    )

    overlay.set_persistent_overlay_items([persistent])
    overlay.set_overlay_items([live])
    overlay.clear_overlay_items()

    assert overlay._persistent_items == [persistent]
    assert overlay._items == []
