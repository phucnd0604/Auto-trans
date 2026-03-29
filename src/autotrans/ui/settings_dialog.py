from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


DEFAULT_STARTUP_SETTINGS: dict[str, Any] = {
    "ocr_provider": "rapidocr",
    "capture_backend": "printwindow",
    "local_translator": "ctranslate2",
    "cloud_provider": "none",
    "subtitle_mode": False,
    "ocr_crop_subtitle_only": False,
    "capture_fps": 1.0,
    "overlay_fps": 30,
    "overlay_ttl_seconds": 1.5,
    "translation_log_enabled": True,
    "font_size": 18,
}


class SettingsDialog(QDialog):
    def __init__(self, settings_path: Path, initial_settings: dict[str, Any] | None = None) -> None:
        super().__init__()
        self._settings_path = settings_path
        settings = dict(DEFAULT_STARTUP_SETTINGS)
        if initial_settings:
            settings.update(initial_settings)

        self.setWindowTitle("AutoTrans Settings")
        self.resize(420, 320)

        self.ocr_provider_combo = QComboBox()
        self.ocr_provider_combo.addItems(["rapidocr"])
        selected_ocr_provider = str(settings["ocr_provider"])
        if selected_ocr_provider not in {"rapidocr"}:
            selected_ocr_provider = "rapidocr"
        self.ocr_provider_combo.setCurrentText(selected_ocr_provider)

        self.capture_backend_combo = QComboBox()
        self.capture_backend_combo.addItems(["printwindow", "mss"])
        self.capture_backend_combo.setCurrentText(str(settings["capture_backend"]))

        self.local_translator_combo = QComboBox()
        self.local_translator_combo.addItems(["ctranslate2", "word"])
        selected_local_translator = str(settings["local_translator"])
        if selected_local_translator not in {"ctranslate2", "word"}:
            selected_local_translator = "ctranslate2"
        self.local_translator_combo.setCurrentText(selected_local_translator)

        self.cloud_provider_combo = QComboBox()
        self.cloud_provider_combo.addItems(["none", "openai"])
        self.cloud_provider_combo.setCurrentText(str(settings["cloud_provider"]))

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
    if settings_path.exists():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update(loaded)
        except Exception:
            pass
    return settings
