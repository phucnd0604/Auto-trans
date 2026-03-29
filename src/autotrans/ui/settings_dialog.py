from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import tomllib

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)


DEFAULT_STARTUP_SETTINGS: dict[str, Any] = {
    "ocr_provider": "rapidocr",
    "capture_backend": "bettercam",
    "local_translator": "ctranslate2",
    "cloud_provider": "none",
    "openai_base_url": "https://api.openai.com/v1",
    "openai_api_key": "",
    "openai_model": "gpt-5-mini",
    "subtitle_mode": False,
    "ocr_crop_subtitle_only": False,
    "capture_fps": 1.0,
    "overlay_fps": 30,
    "overlay_ttl_seconds": 1.5,
    "translation_log_enabled": True,
    "font_size": 18,
}


def _load_preset_settings(preset_path: Path) -> dict[str, Any]:
    if not preset_path.exists():
        return {}
    try:
        data = tomllib.loads(preset_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    settings: dict[str, Any] = {}
    capture = data.get("capture", {})
    ocr = data.get("ocr", {})
    translation = data.get("translation", {})
    overlay = data.get("overlay", {})
    subtitle = data.get("subtitle", {})
    logging = data.get("logging", {})

    if "backend" in capture:
        settings["capture_backend"] = capture["backend"]
    if "provider" in ocr:
        settings["ocr_provider"] = ocr["provider"]
    if "local_translator" in translation:
        settings["local_translator"] = translation["local_translator"]
    if "cloud_provider" in translation:
        settings["cloud_provider"] = translation["cloud_provider"]
    if "openai_base_url" in translation:
        settings["openai_base_url"] = translation["openai_base_url"]
    if "openai_model" in translation:
        settings["openai_model"] = translation["openai_model"]
    if "mode" in subtitle:
        settings["subtitle_mode"] = bool(subtitle["mode"])
    if "crop_subtitle_only" in subtitle:
        settings["ocr_crop_subtitle_only"] = bool(subtitle["crop_subtitle_only"])
    if "fps" in capture:
        settings["capture_fps"] = float(capture["fps"])
    if "fps" in overlay:
        settings["overlay_fps"] = int(overlay["fps"])
    if "ttl_seconds" in overlay:
        settings["overlay_ttl_seconds"] = float(overlay["ttl_seconds"])
    if "font_size" in overlay:
        settings["font_size"] = int(overlay["font_size"])
    if "translation_log_enabled" in logging:
        settings["translation_log_enabled"] = bool(logging["translation_log_enabled"])
    return settings


class SettingsDialog(QDialog):
    def __init__(self, settings_path: Path, initial_settings: dict[str, Any] | None = None) -> None:
        super().__init__()
        self._settings_path = settings_path
        settings = dict(DEFAULT_STARTUP_SETTINGS)
        if initial_settings:
            settings.update(initial_settings)

        self.setWindowTitle("AutoTrans Settings")
        self.resize(520, 420)

        self.ocr_provider_combo = QComboBox()
        self.ocr_provider_combo.addItems(["rapidocr"])
        selected_ocr_provider = str(settings["ocr_provider"])
        if selected_ocr_provider not in {"rapidocr"}:
            selected_ocr_provider = "rapidocr"
        self.ocr_provider_combo.setCurrentText(selected_ocr_provider)

        self.capture_backend_combo = QComboBox()
        self.capture_backend_combo.addItems(["bettercam", "printwindow", "mss"])
        self.capture_backend_combo.setCurrentText(str(settings["capture_backend"]))

        self.local_translator_combo = QComboBox()
        self.local_translator_combo.addItems(["ctranslate2", "word"])
        selected_local_translator = str(settings["local_translator"])
        if selected_local_translator not in {"ctranslate2", "word"}:
            selected_local_translator = "ctranslate2"
        self.local_translator_combo.setCurrentText(selected_local_translator)

        self.cloud_provider_combo = QComboBox()
        self.cloud_provider_combo.addItems(["none", "openai", "ollama"])
        self.cloud_provider_combo.setCurrentText(str(settings["cloud_provider"]))

        self.openai_base_url_edit = QLineEdit(str(settings["openai_base_url"]))
        self.openai_base_url_edit.setPlaceholderText("https://openrouter.ai/api/v1 or http://ubuntu-server:11434")

        self.openai_api_key_edit = QLineEdit(str(settings["openai_api_key"]))
        self.openai_api_key_edit.setEchoMode(QLineEdit.Password)
        self.openai_api_key_edit.setPlaceholderText("OpenAI/OpenRouter key, or leave empty for Ollama")

        self.openai_model_edit = QLineEdit(str(settings["openai_model"]))
        self.openai_model_edit.setPlaceholderText("openai/gpt-4.1-mini or qwen2.5:3b")

        self.subtitle_mode_check = QCheckBox("Enable subtitle mode")
        self.subtitle_mode_check.setChecked(bool(settings["subtitle_mode"]))

        self.crop_subtitle_check = QCheckBox("Crop OCR to subtitle region only")
        self.crop_subtitle_check.setChecked(bool(settings["ocr_crop_subtitle_only"]))

        self.capture_fps_spin = QDoubleSpinBox()
        self.capture_fps_spin.setRange(0.2, 10.0)
        self.capture_fps_spin.setDecimals(1)
        self.capture_fps_spin.setSingleStep(0.5)
        self.capture_fps_spin.setValue(float(settings["capture_fps"]))

        self.overlay_fps_spin = QSpinBox()
        self.overlay_fps_spin.setRange(5, 60)
        self.overlay_fps_spin.setValue(int(settings["overlay_fps"]))

        self.overlay_ttl_spin = QDoubleSpinBox()
        self.overlay_ttl_spin.setRange(0.2, 10.0)
        self.overlay_ttl_spin.setDecimals(1)
        self.overlay_ttl_spin.setSingleStep(0.1)
        self.overlay_ttl_spin.setValue(float(settings["overlay_ttl_seconds"]))

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(12, 36)
        self.font_size_spin.setValue(int(settings["font_size"]))

        self.translation_log_check = QCheckBox("Enable translation log")
        self.translation_log_check.setChecked(bool(settings["translation_log_enabled"]))

        form = QFormLayout()
        form.addRow("OCR Provider", self.ocr_provider_combo)
        form.addRow("Capture Backend", self.capture_backend_combo)
        form.addRow("Local Translator", self.local_translator_combo)
        form.addRow("Cloud Provider", self.cloud_provider_combo)
        form.addRow("Cloud Base URL", self.openai_base_url_edit)
        form.addRow("Cloud API Key", self.openai_api_key_edit)
        form.addRow("Cloud Model", self.openai_model_edit)
        form.addRow("Capture FPS", self.capture_fps_spin)
        form.addRow("Overlay FPS", self.overlay_fps_spin)
        form.addRow("Overlay TTL (s)", self.overlay_ttl_spin)
        form.addRow("Font Size", self.font_size_spin)
        form.addRow("Subtitle Mode", self.subtitle_mode_check)
        form.addRow("Subtitle Crop", self.crop_subtitle_check)
        form.addRow("Logging", self.translation_log_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Review startup settings, then press OK to open AutoTrans."))
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def values(self) -> dict[str, Any]:
        return {
            "ocr_provider": self.ocr_provider_combo.currentText(),
            "capture_backend": self.capture_backend_combo.currentText(),
            "local_translator": self.local_translator_combo.currentText(),
            "cloud_provider": self.cloud_provider_combo.currentText(),
            "openai_base_url": self.openai_base_url_edit.text().strip(),
            "openai_api_key": self.openai_api_key_edit.text().strip(),
            "openai_model": self.openai_model_edit.text().strip(),
            "subtitle_mode": self.subtitle_mode_check.isChecked(),
            "ocr_crop_subtitle_only": self.crop_subtitle_check.isChecked(),
            "capture_fps": self.capture_fps_spin.value(),
            "overlay_fps": self.overlay_fps_spin.value(),
            "overlay_ttl_seconds": self.overlay_ttl_spin.value(),
            "translation_log_enabled": self.translation_log_check.isChecked(),
            "font_size": self.font_size_spin.value(),
        }

    def accept(self) -> None:
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(
            json.dumps(self.values(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        super().accept()


def load_startup_settings(settings_path: Path) -> dict[str, Any]:
    settings = dict(DEFAULT_STARTUP_SETTINGS)
    preset_path = settings_path.parent.parent / "preset.toml"
    settings.update(_load_preset_settings(preset_path))
    if settings_path.exists():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update(loaded)
        except Exception:
            pass
    return settings
