import numpy as np

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, QualityMode, Rect, TranslationResult
from autotrans.services.orchestrator import PipelineOrchestrator


class FakeCapture:
    def list_windows(self):
        return []

    def capture_window(self, hwnd: int):
        return Frame(
            image=np.zeros((1000, 2000, 3), dtype=np.uint8),
            timestamp=1.0,
            window_rect=Rect(0, 0, 2000, 1000),
        )


class FakeOCR:
    name = "fake"

    def recognize(self, frame: Frame):
        return [
            OCRBox(
                id="",
                source_text="then drop him with one strike",
                confidence=0.95,
                bbox=Rect(450, 860, 820, 42),
                language_hint="en",
                line_id="line-0",
            )
        ]


class FakeTranslator:
    name = "local"

    def __init__(self):
        self.calls = 0

    def translate_batch(self, items, source_lang, target_lang, mode):
        self.calls += 1
        return [
            TranslationResult(
                source_text=item.source_text,
                translated_text="Ha guc han chi bang mot nhat chem",
                provider=self.name,
                latency_ms=12.0,
            )
            for item in items
        ]


class FailingCloudTranslator:
    name = "cloud"

    def translate_batch(self, items, source_lang, target_lang, mode):
        raise RuntimeError("cloud down")


class NoCloudPolicy:
    def select(self, text_items, mode, network_state, cost_budget=True):
        from autotrans.services.policy import ProviderDecision

        return ProviderDecision(provider="local", reason="test")


class CloudPolicy:
    def select(self, text_items, mode, network_state, cost_budget=True):
        from autotrans.services.policy import ProviderDecision

        return ProviderDecision(provider="cloud", reason="test")


def test_orchestrator_uses_cache_after_first_pass() -> None:
    config = AppConfig()
    config.mode = QualityMode.BALANCED.value
    config.debounce_frames = 1
    config.translation_stable_scans = 1
    translator = FakeTranslator()
    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=FakeCapture(),
        ocr_provider=FakeOCR(),
        local_translator=translator,
        cloud_translator=None,
        policy=NoCloudPolicy(),
    )

    items_first = orchestrator.process_window(1)
    items_second = orchestrator.process_window(1)

    assert len(items_first) == 1
    assert items_first[0].translated_text == "Ha guc han chi bang mot nhat chem"
    assert translator.calls == 1
    assert len(items_second) == 1


def test_orchestrator_falls_back_to_local_on_cloud_error() -> None:
    config = AppConfig()
    config.mode = QualityMode.HIGH_QUALITY.value
    config.debounce_frames = 1
    config.translation_stable_scans = 1
    translator = FakeTranslator()
    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=FakeCapture(),
        ocr_provider=FakeOCR(),
        local_translator=translator,
        cloud_translator=FailingCloudTranslator(),
        policy=CloudPolicy(),
    )

    items = orchestrator.process_window(1)

    assert len(items) == 1
    assert items[0].translated_text == "Ha guc han chi bang mot nhat chem"
    assert translator.calls == 1


def test_orchestrator_can_overlay_source_text_without_translation() -> None:
    config = AppConfig()
    config.overlay_source_text = True
    config.subtitle_mode = False
    config.ocr_crop_subtitle_only = False
    config.debounce_frames = 1
    config.translation_stable_scans = 1
    translator = FakeTranslator()
    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=FakeCapture(),
        ocr_provider=FakeOCR(),
        local_translator=translator,
        cloud_translator=None,
        policy=NoCloudPolicy(),
    )

    items = orchestrator.process_window(1)

    assert len(items) == 1
    assert items[0].translated_text == "then drop him with one strike"
    assert translator.calls == 0


def test_orchestrator_waits_for_stable_scan_before_translation() -> None:
    config = AppConfig()
    config.mode = QualityMode.BALANCED.value
    config.debounce_frames = 1
    config.translation_stable_scans = 2
    translator = FakeTranslator()
    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=FakeCapture(),
        ocr_provider=FakeOCR(),
        local_translator=translator,
        cloud_translator=None,
        policy=NoCloudPolicy(),
    )

    items_first = orchestrator.process_window(1)
    items_second = orchestrator.process_window(1)

    assert items_first == []
    assert len(items_second) == 1
    assert translator.calls == 1
