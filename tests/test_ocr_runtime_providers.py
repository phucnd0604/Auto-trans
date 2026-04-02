from __future__ import annotations

from pathlib import Path

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


def test_deep_provider_uses_paddle_provider(monkeypatch) -> None:
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

    provider = app_module._build_deep_ocr_provider(config)

    assert provider.name == "paddleocr"
    assert isinstance(provider._get_instance(), FakePaddleProvider)
    assert provider._get_instance().config is config


def test_lazy_ocr_provider_caches_init_failure() -> None:
    calls = {"count": 0}

    def factory():
        calls["count"] += 1
        raise RuntimeError("boom")

    provider = app_module._LazyOCRProvider("paddleocr", factory)

    for _ in range(2):
        try:
            provider._get_instance()
        except RuntimeError as exc:
            assert "initialization previously failed" in str(exc) or str(exc) == "boom"
        else:
            raise AssertionError("Expected init failure")

    assert calls["count"] == 1


def test_warmup_ocr_providers_initializes_lazy_instances() -> None:
    calls = {"count": 0}

    class PlainProvider:
        name = "plain"

    def factory():
        calls["count"] += 1
        return object()

    lazy_provider = app_module._LazyOCRProvider("paddleocr", factory)

    app_module._warmup_ocr_providers([lazy_provider, PlainProvider()])

    assert calls["count"] == 1
    assert lazy_provider._instance is not None


def test_build_realtime_ocr_provider_rejects_unknown_provider() -> None:
    config = _make_config()
    config.ocr_provider = "unknown"

    try:
        app_module._build_realtime_ocr_provider(config)
    except ValueError as exc:
        assert "Unsupported realtime OCR provider" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown provider")


def test_build_cloud_translator_selects_provider_backend(monkeypatch) -> None:
    config = _make_config()
    config.deep_translation_provider = "groq"

    class FakeGroqTranslator:
        name = "groq"

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class FakeGeminiRestTranslator:
        name = "gemini-rest"

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(app_module, "GroqTranslator", FakeGroqTranslator)
    monkeypatch.setattr(app_module, "GeminiRestTranslator", FakeGeminiRestTranslator)

    groq_translator = app_module._build_cloud_translator(config)

    assert groq_translator is not None
    assert groq_translator.name == "groq"
    assert groq_translator.kwargs["api_key"] == "test-key"

    config.deep_translation_provider = "gemini"
    gemini_translator = app_module._build_cloud_translator(config)

    assert gemini_translator is not None
    assert gemini_translator.name == "gemini-rest"


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


def test_paddle_provider_forces_english_only_language() -> None:
    config = _make_config()
    config.ocr_languages = ["ja", "zh-cn", "en"]
    provider = PaddleOCRProvider.__new__(PaddleOCRProvider)
    BaseOCRProvider.__init__(provider, config)

    assert provider._resolve_language() == "en"
    assert provider._resolve_recognition_model_name() == "en_PP-OCRv5_mobile_rec"


def test_paddle_provider_resolves_recognition_model_from_user_cache(monkeypatch, tmp_path) -> None:
    config = _make_config()
    provider = PaddleOCRProvider.__new__(PaddleOCRProvider)
    BaseOCRProvider.__init__(provider, config)

    fake_home = tmp_path / "home"
    model_dir = fake_home / ".paddlex" / "official_models" / "en_PP-OCRv5_mobile_rec"
    model_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    model_name, resolved_dir = provider._resolve_recognition_model()

    assert model_name == "en_PP-OCRv5_mobile_rec"
    assert resolved_dir == model_dir


def test_paddle_provider_recognize_paragraphs_merges_lines_by_layout_region() -> None:
    provider = PaddleOCRProvider.__new__(PaddleOCRProvider)
    BaseOCRProvider.__init__(provider, _make_config())
    provider._language = "en"
    provider._paddlex_layout_disabled = False

    class FakeEngine:
        def predict(self, image):
            return [[
                (
                    [[10, 20], [180, 20], [180, 48], [10, 48]],
                    ("Quest Objective", 0.93),
                ),
                (
                    [[12, 56], [240, 56], [240, 84], [12, 84]],
                    ("Find the lost relic", 0.91),
                ),
            ]]

    class FakeStructureEngine:
        def predict(self, image):
            return [
                {
                    "boxes": [
                        {"label": "text", "coordinate": [0, 10, 260, 100], "score": 0.97},
                    ]
                }
            ]

    provider._engine = FakeEngine()
    provider._paddlex_layout_model = FakeStructureEngine()

    boxes = provider.recognize_paragraphs(_make_frame())

    assert len(boxes) == 1
    assert boxes[0].source_text == "Quest Objective\nFind the lost relic"
    assert boxes[0].bbox == Rect(x=10, y=20, width=230, height=64)


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
