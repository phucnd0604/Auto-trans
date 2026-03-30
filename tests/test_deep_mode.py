from __future__ import annotations

import json

import numpy as np

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, OverlayItem, OverlayStyle, QualityMode, Rect, TranslationResult
from autotrans.services.orchestrator import PipelineOrchestrator
from autotrans.services.translation import GEMINI_DEEP_SYSTEM_PROMPT, GeminiTranslator
from autotrans.ui.overlay import OverlayWindow
from autotrans.ui.settings_dialog import SettingsDialog, load_startup_settings


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


class StubLocalTranslator:
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
        return self.translate_batch(items, source_lang, target_lang, QualityMode.HIGH_QUALITY)


class StubCloudTranslator:
    name = "gemini"

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
                translated_text=f"CLOUD: {item.source_text}",
                provider=self.name,
                latency_ms=10.0,
            )
            for item in items
        ]

    def translate_screen_blocks(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
    ) -> list[TranslationResult]:
        return self.translate_batch(items, source_lang, target_lang, QualityMode.HIGH_QUALITY)


def _make_config() -> AppConfig:
    config = AppConfig()
    config.deep_translation_api_key = "test-key"
    config.deep_translation_model = "gemini-test"
    config.deep_translation_transport = "sdk"
    config.translation_log_enabled = False
    config.subtitle_mode = True
    return config


def _make_frame() -> Frame:
    return Frame(
        image=np.zeros((300, 400, 3), dtype=np.uint8),
        timestamp=0.0,
        window_rect=Rect(x=0, y=0, width=400, height=300),
    )


def _make_boxes() -> list[OCRBox]:
    return [
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


def test_translate_deep_boxes_falls_back_to_local_without_cloud() -> None:
    config = _make_config()
    config.deep_translation_api_key = None
    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=StubCaptureService(_make_frame()),
        ocr_provider=StubOCRProvider(_make_boxes()),
        local_translator=StubLocalTranslator(),
        cloud_translator=None,
    )

    grouped_boxes, preview_items = orchestrator.prepare_deep_translation(100)
    items = orchestrator.translate_deep_boxes(grouped_boxes)

    assert grouped_boxes
    assert preview_items
    assert items
    assert all(item.translated_text.startswith("LOCAL:") for item in items)


def test_translate_deep_boxes_prefers_cloud_when_available() -> None:
    config = _make_config()
    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=StubCaptureService(_make_frame()),
        ocr_provider=StubOCRProvider(_make_boxes()),
        local_translator=StubLocalTranslator(),
        cloud_translator=StubCloudTranslator(),
    )

    grouped_boxes, _ = orchestrator.prepare_deep_translation(100)
    items = orchestrator.translate_deep_boxes(grouped_boxes)

    assert items
    assert all(item.region == "deep-ui" for item in items)
    assert all(item.translated_text.startswith("CLOUD:") for item in items)


def test_settings_dialog_hides_advanced_controls_by_default(qtbot, tmp_path) -> None:
    dialog = SettingsDialog(settings_path=tmp_path / "ui-settings.json")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)

    assert dialog.deep_translation_api_key_edit.isVisible()
    assert dialog.game_profile_title_edit.isVisible()
    assert dialog.game_profile_world_edit.isVisible()
    assert dialog.game_profile_factions_edit.isVisible()
    assert dialog.game_profile_characters_honorifics_edit.isVisible()
    assert dialog.game_profile_terms_items_skills_edit.isVisible()
    assert not dialog.advanced_container.isVisible()
    assert dialog.advanced_check.isChecked() is False

    dialog.advanced_check.setChecked(True)

    assert dialog.advanced_container.isVisible()


def test_load_startup_settings_maps_legacy_openai_keys(tmp_path) -> None:
    runtime_dir = tmp_path / ".runtime"
    runtime_dir.mkdir(parents=True)
    settings_path = runtime_dir / "ui-settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "openai_api_key": "legacy-key",
                "openai_model": "legacy-model",
                "openai_base_url": "https://legacy.example/v1",
                "local_translator": "word",
                "cloud_provider": "openai",
            }
        ),
        encoding="utf-8",
    )

    settings = load_startup_settings(settings_path)

    assert settings["deep_translation_api_key"] == "legacy-key"
    assert settings["deep_translation_model"] == "legacy-model"
    assert settings["deep_translation_transport"] == "sdk"
    assert settings["game_profile_title"] == ""
    assert settings["game_profile_world"] == ""
    assert settings["game_profile_factions"] == ""
    assert settings["game_profile_characters_honorifics"] == ""
    assert settings["game_profile_terms_items_skills"] == ""
    assert "local_translator" not in settings
    assert "cloud_provider" not in settings


def test_settings_dialog_values_include_game_profile_fields(tmp_path) -> None:
    dialog = SettingsDialog(settings_path=tmp_path / "ui-settings.json")
    dialog.game_profile_title_edit.setText("Phi Tien Truyen")
    dialog.game_profile_world_edit.setPlainText("Tu tien the gioi, tong mon va bi canh")
    dialog.game_profile_factions_edit.setPlainText("Thanh Van Mon, Ma Dao")
    dialog.game_profile_characters_honorifics_edit.setPlainText("Han Lap - dao huu, Nam Cung Uyen - tien tu")
    dialog.game_profile_terms_items_skills_edit.setPlainText("Linh thach, phap bao, Truc Co")

    values = dialog.values()

    assert values["game_profile_title"] == "Phi Tien Truyen"
    assert values["game_profile_world"] == "Tu tien the gioi, tong mon va bi canh"
    assert values["game_profile_factions"] == "Thanh Van Mon, Ma Dao"
    assert values["game_profile_characters_honorifics"] == "Han Lap - dao huu, Nam Cung Uyen - tien tu"
    assert values["game_profile_terms_items_skills"] == "Linh thach, phap bao, Truc Co"
    assert values["deep_translation_transport"] == "sdk"


def test_gemini_translator_builds_deep_contents_with_game_profile() -> None:
    config = _make_config()
    config.game_profile_title = "Phi Tien Truyen"
    config.game_profile_world = "The gioi tu tien, canh gioi phan minh"
    config.game_profile_factions = "Thanh Van Mon, Huyet Sat Tông"
    config.game_profile_characters_honorifics = "Han Lap - dao huu, su huynh"
    config.game_profile_terms_items_skills = "Linh thach, phap bao, ket dan"
    translator = GeminiTranslator(
        model=config.deep_translation_model,
        api_key=config.deep_translation_api_key,
        config=config,
    )

    system_instruction = translator._build_deep_system_instruction()
    prompt = translator._build_deep_translation_contents(_make_boxes())

    assert "Game Profile va ngu canh:" in system_instruction
    assert "Game Title: Phi Tien Truyen" in system_instruction
    assert "World / Setting: The gioi tu tien, canh gioi phan minh" in system_instruction
    assert "Factions / Organizations: Thanh Van Mon, Huyet Sat Tông" in system_instruction
    assert "Characters & Honorifics: Han Lap - dao huu, su huynh" in system_instruction
    assert "Terms / Items / Skills: Linh thach, phap bao, ket dan" in system_instruction
    assert "Game Profile va ngu canh:" not in prompt
    assert "<BLOCK_1>" in prompt
    assert "</BLOCK_2>" in prompt


def test_gemini_translator_omits_empty_game_profile_lines() -> None:
    config = _make_config()
    translator = GeminiTranslator(
        model=config.deep_translation_model,
        api_key=config.deep_translation_api_key,
        config=config,
    )

    system_instruction = translator._build_deep_system_instruction()
    prompt = translator._build_deep_translation_contents(_make_boxes())

    assert GEMINI_DEEP_SYSTEM_PROMPT in system_instruction
    assert "Game Profile va ngu canh:" not in system_instruction
    assert "Game Title:" not in system_instruction
    assert "Game Profile va ngu canh:" not in prompt


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
