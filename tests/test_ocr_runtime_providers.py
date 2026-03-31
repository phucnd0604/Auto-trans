from __future__ import annotations

import numpy as np

from autotrans import app as app_module
from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, QualityMode, Rect, TranslationResult
from autotrans.services.ocr import BaseOCRProvider, PaddleOCRProvider
from autotrans.services.orchestrator import PipelineOrchestrator


class _StubCaptureService:
    def __init__(self, frame: Frame) -> None:
        self._frame = frame

    def capture_window(self, hwnd: int) -> Frame | None:
        return self._frame

    def list_windows(self) -> list[object]:
        return []


class _NoopTranslator:
    name = "local-ctranslate2"

    def translate_batch(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
        mode: QualityMode,
    ) -> list[TranslationResult]:
        return [
            TranslationResult(
                source_text=item.source_text,
                translated_text=f"LOCAL: {item.source_text}",
                provider=self.name,
                latency_ms=1.0,
            )
            for item in items
        ]

    def translate_screen_blocks(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
    ) -> list[TranslationResult]:
        return [
            TranslationResult(
                source_text=item.source_text,
                translated_text=f"DEEP: {item.source_text}",
                provider="gemini-rest",
                latency_ms=5.0,
            )
            for item in items
        ]


class _CountingOCRProvider:
    def __init__(self, boxes: list[OCRBox], *, paragraphs: list[OCRBox] | None = None) -> None:
        self.boxes = boxes
        self.paragraphs = paragraphs if paragraphs is not None else boxes
        self.recognize_calls = 0
        self.paragraph_calls = 0

    def recognize(self, frame: Frame) -> list[OCRBox]:
        self.recognize_calls += 1
        return list(self.boxes)

    def recognize_paragraphs(self, frame: Frame) -> list[OCRBox]:
        self.paragraph_calls += 1
        return list(self.paragraphs)


def _make_config() -> AppConfig:
    config = AppConfig()
    config.translation_log_enabled = False
    config.subtitle_mode = True
    config.translation_stable_scans = 1
    config.subtitle_hold_frames = 1
    config.debounce_frames = 1
    config.deep_translation_api_key = "test-key"
    return config


def _make_frame() -> Frame:
    return Frame(
        image=np.zeros((240, 360, 3), dtype=np.uint8),
        timestamp=0.0,
        window_rect=Rect(x=0, y=0, width=360, height=240),
    )


def _live_box() -> OCRBox:
    return OCRBox(
        id="live-1",
        source_text="Follow Yuna to the bridge",
        confidence=0.95,
        bbox=Rect(x=40, y=188, width=240, height=28),
        language_hint="en",
        line_id="subtitle-1",
    )


def _deep_box() -> OCRBox:
    return OCRBox(
        id="deep-1",
        source_text="Quest Objective\nFind the lost relic",
        confidence=0.96,
        bbox=Rect(x=20, y=24, width=220, height=60),
        language_hint="en",
        line_id="paragraph-1",
    )


def test_build_realtime_ocr_provider_selects_paddle(monkeypatch) -> None:
    config = _make_config()
    config.ocr_provider = "paddleocr"

    class FakePaddleProvider:
        name = "paddleocr"

        def __init__(self, passed_config: AppConfig) -> None:
            self.config = passed_config

        def recognize(self, frame: Frame) -> list[OCRBox]:
            return []

        def recognize_paragraphs(self, frame: Frame) -> list[OCRBox]:
            return []

    monkeypatch.setattr(app_module, "PaddleOCRProvider", FakePaddleProvider)

    provider = app_module._build_realtime_ocr_provider(config)

    assert provider.name == "paddleocr"
    assert isinstance(provider._get_instance(), FakePaddleProvider)
    assert provider._get_instance().config is config


def test_deep_provider_stays_rapid_when_realtime_uses_paddle(monkeypatch) -> None:
    config = _make_config()
    config.ocr_provider = "paddleocr"

    class FakeRapidProvider:
        name = "rapidocr"

        def __init__(self, passed_config: AppConfig) -> None:
            self.config = passed_config

        def recognize(self, frame: Frame) -> list[OCRBox]:
            return []

        def recognize_paragraphs(self, frame: Frame) -> list[OCRBox]:
            return []

    monkeypatch.setattr(app_module, "RapidOCRProvider", FakeRapidProvider)

    provider = app_module._build_deep_ocr_provider(config)

    assert provider.name == "rapidocr"
    assert isinstance(provider._get_instance(), FakeRapidProvider)
    assert provider._get_instance().config is config


def test_build_realtime_ocr_provider_rejects_unknown_provider() -> None:
    config = _make_config()
    config.ocr_provider = "unknown"

    try:
        app_module._build_realtime_ocr_provider(config)
    except ValueError as exc:
        assert "Unsupported realtime OCR provider" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown provider")


def test_paddle_provider_converts_nested_result_to_ocr_boxes() -> None:
    provider = PaddleOCRProvider.__new__(PaddleOCRProvider)
    BaseOCRProvider.__init__(provider, _make_config())
    provider._language = "en"

    class FakeEngine:
        def predict(self, image):
            return [[
                (
                    [[10, 20], [110, 20], [110, 48], [10, 48]],
                    ("Quest accepted", 0.93),
                ),
                (
                    [[12, 60], [144, 60], [144, 88], [12, 88]],
                    ("Start adventure", 0.89),
                ),
            ]]

    provider._engine = FakeEngine()

    boxes = provider.recognize(_make_frame())

    assert [box.source_text for box in boxes] == ["Quest accepted", "Start adventure"]
    assert boxes[0].bbox == Rect(x=10, y=20, width=100, height=28)
    assert boxes[0].language_hint == "en"


def test_live_process_uses_realtime_provider_only() -> None:
    frame = _make_frame()
    realtime_provider = _CountingOCRProvider([_live_box()])
    deep_provider = _CountingOCRProvider([_deep_box()])
    orchestrator = PipelineOrchestrator(
        config=_make_config(),
        capture_service=_StubCaptureService(frame),
        ocr_provider=realtime_provider,
        deep_ocr_provider=deep_provider,
        local_translator=_NoopTranslator(),
        cloud_translator=_NoopTranslator(),
    )

    overlay_items = orchestrator.process_window(1)

    assert overlay_items
    assert realtime_provider.recognize_calls == 1
    assert realtime_provider.paragraph_calls == 0
    assert deep_provider.recognize_calls == 0
    assert deep_provider.paragraph_calls == 0


def test_prepare_deep_translation_uses_deep_provider_only() -> None:
    frame = _make_frame()
    realtime_provider = _CountingOCRProvider([_live_box()])
    deep_provider = _CountingOCRProvider([_deep_box()], paragraphs=[_deep_box()])
    orchestrator = PipelineOrchestrator(
        config=_make_config(),
        capture_service=_StubCaptureService(frame),
        ocr_provider=realtime_provider,
        deep_ocr_provider=deep_provider,
        local_translator=_NoopTranslator(),
        cloud_translator=_NoopTranslator(),
    )

    grouped_boxes, preview_items = orchestrator.prepare_deep_translation(1)

    assert grouped_boxes
    assert preview_items
    assert realtime_provider.recognize_calls == 0
    assert realtime_provider.paragraph_calls == 0
    assert deep_provider.recognize_calls == 0
    assert deep_provider.paragraph_calls == 1
