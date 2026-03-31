from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import tomllib

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


DEFAULT_STARTUP_SETTINGS: dict[str, Any] = {
    "ocr_provider": "rapidocr",
    "capture_backend": "printwindow",
    "capture_fps": 4.0,
    "subtitle_mode": True,
    "ocr_crop_subtitle_only": True,
    "overlay_fps": 30,
    "overlay_ttl_seconds": 1.5,
    "translation_log_enabled": True,
    "font_size": 18,
    "deep_translation_api_key": "",
    "deep_translation_model": "gemini-2.0-flash",
    "deep_translation_transport": "rest",
    "game_profile_title": "",
    "game_profile_world": "",
    "game_profile_factions": "",
    "game_profile_characters_honorifics": "",
    "game_profile_terms_items_skills": "",
    "advanced_settings": False,
}

SETTING_TOOLTIPS: dict[str, str] = {
    "Gemini API Key": "API key cho deep mode Gemini. Realtime translation van dung ctranslate2, khong dung key nay.",
    "Game Title": "Ten game de bo sung ngu canh cho deep mode, giup Gemini giu dung thuat ngu va khong khi.",
    "World / Setting": "Mo ta boi canh, thoi dai, the gioi, he thong suc manh va tone chung cua game cho deep mode.",
    "Factions / Organizations": "Danh sach phe phai, to chuc, tong mon, quoc gia hoac nhom quan trong de deep mode dich on dinh hon.",
    "Characters & Honorifics": "Nhan vat chinh, cach xung ho, danh xung va honorific can uu tien khi deep mode dich hoi thoai.",
    "Terms / Items / Skills": "Thuat ngu rieng, vat pham, ky nang, canh gioi, ten ky nang va cach viet mong muon trong deep mode.",
    "OCR Provider": "OCR engine cho realtime translation. PaddleOCR dang nhanh hon tren bo test subtitle hien tai; deep mode van co dinh dung RapidOCR.",
    "Capture Backend": "Cach chup hinh cua cua so game. PrintWindow on dinh hon, BetterCam nhanh hon voi mot so game, MSS la fallback tong quat.",
    "Capture FPS": "Tan suat chup hinh cho pipeline realtime. Tang cao hon se cap nhat nhanh hon nhung ton CPU/GPU hon.",
    "Subtitle Mode": "Bat bo loc subtitle. Khi bat, pipeline uu tien text o vung subtitle thay vi HUD/menu text.",
    "Subtitle Crop": "Chi OCR vung subtitle o phia duoi man hinh. Thuong giup tang toc do rat nhieu va giam nhieu text rac.",
    "Overlay FPS": "Tan suat ve lai overlay ban dich. Cao hon cho cam giac muot hon nhung co them chi phi render.",
    "Overlay TTL (s)": "Thoi gian giu mot overlay tren man hinh truoc khi tu dong an di.",
    "Font Size": "Co chu mac dinh cua overlay ban dich.",
    "Logging": "Ghi log runtime va chi tiet OCR/translation vao file .runtime/logs/autotrans.log de debug va benchmark.",
    "Gemini Model": "Model Gemini dung cho deep mode. Khong anh huong toi realtime ctranslate2.",
}


def _normalize_loaded_settings(settings: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(settings)
    if "deep_translation_api_key" not in normalized:
        normalized["deep_translation_api_key"] = str(normalized.get("openai_api_key", "")).strip()
    if "deep_translation_model" not in normalized:
        model = str(normalized.get("openai_model", "")).strip()
        normalized["deep_translation_model"] = model or DEFAULT_STARTUP_SETTINGS["deep_translation_model"]
    normalized["deep_translation_transport"] = "rest"
    normalized.pop("local_translator", None)
    normalized.pop("cloud_provider", None)
    normalized.pop("deep_translation_base_url", None)
    normalized.pop("openai_base_url", None)
    return normalized


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
    if "fps" in capture:
        settings["capture_fps"] = float(capture["fps"])
    if "mode" in subtitle:
        settings["subtitle_mode"] = bool(subtitle["mode"])
    if "crop_subtitle_only" in subtitle:
        settings["ocr_crop_subtitle_only"] = bool(subtitle["crop_subtitle_only"])
    if "fps" in overlay:
        settings["overlay_fps"] = int(overlay["fps"])
    if "ttl_seconds" in overlay:
        settings["overlay_ttl_seconds"] = float(overlay["ttl_seconds"])
    if "font_size" in overlay:
        settings["font_size"] = int(overlay["font_size"])
    if "translation_log_enabled" in logging:
        settings["translation_log_enabled"] = bool(logging["translation_log_enabled"])
    if "openai_model" in translation:
        settings["deep_translation_model"] = str(translation["openai_model"]).strip()
    return _normalize_loaded_settings(settings)


class SettingsDialog(QDialog):
    def __init__(self, settings_path: Path, initial_settings: dict[str, Any] | None = None) -> None:
        super().__init__()
        self._settings_path = settings_path
        settings = dict(DEFAULT_STARTUP_SETTINGS)
        if initial_settings:
            settings.update(_normalize_loaded_settings(initial_settings))

        self.setWindowTitle("AutoTrans Settings")
        self.resize(760, 420)
        self.setMinimumWidth(720)

        self.deep_translation_api_key_edit = QLineEdit(str(settings["deep_translation_api_key"]))
        self.deep_translation_api_key_edit.setEchoMode(QLineEdit.Password)
        self.deep_translation_api_key_edit.setPlaceholderText("Nhap Gemini API key, de trong se fallback sang ctranslate2")

        self.game_profile_title_edit = QLineEdit(str(settings["game_profile_title"]))
        self.game_profile_title_edit.setPlaceholderText("Ten game")

        self.game_profile_world_edit = QTextEdit()
        self.game_profile_world_edit.setPlainText(str(settings["game_profile_world"]))
        self.game_profile_world_edit.setPlaceholderText("Bo canh, the gioi, thoi dai, he thong suc manh")
        self.game_profile_world_edit.setFixedHeight(56)

        self.game_profile_factions_edit = QTextEdit()
        self.game_profile_factions_edit.setPlainText(str(settings["game_profile_factions"]))
        self.game_profile_factions_edit.setPlaceholderText("Tong mon, the luc, to chuc, phe phai")
        self.game_profile_factions_edit.setFixedHeight(56)

        self.game_profile_characters_honorifics_edit = QTextEdit()
        self.game_profile_characters_honorifics_edit.setPlainText(str(settings["game_profile_characters_honorifics"]))
        self.game_profile_characters_honorifics_edit.setPlaceholderText("Nhan vat chinh va danh xung nen dung")
        self.game_profile_characters_honorifics_edit.setFixedHeight(56)

        self.game_profile_terms_items_skills_edit = QTextEdit()
        self.game_profile_terms_items_skills_edit.setPlainText(str(settings["game_profile_terms_items_skills"]))
        self.game_profile_terms_items_skills_edit.setPlaceholderText("Thuat ngu, vat pham, ky nang, canh gioi")
        self.game_profile_terms_items_skills_edit.setFixedHeight(56)

        self.advanced_check = QCheckBox("Advanced")
        self.advanced_check.setChecked(bool(settings["advanced_settings"]))

        self.ocr_provider_combo = QComboBox()
        self.ocr_provider_combo.addItems(["rapidocr", "paddleocr"])
        self.ocr_provider_combo.setCurrentText(str(settings["ocr_provider"]))

        self.capture_backend_combo = QComboBox()
        self.capture_backend_combo.addItems(["printwindow", "bettercam", "mss"])
        self.capture_backend_combo.setCurrentText(str(settings["capture_backend"]))

        self.capture_fps_spin = QDoubleSpinBox()
        self.capture_fps_spin.setRange(0.2, 10.0)
        self.capture_fps_spin.setDecimals(1)
        self.capture_fps_spin.setSingleStep(0.5)
        self.capture_fps_spin.setValue(float(settings["capture_fps"]))

        self.subtitle_mode_check = QCheckBox("Enable subtitle mode")
        self.subtitle_mode_check.setChecked(bool(settings["subtitle_mode"]))

        self.crop_subtitle_check = QCheckBox("Crop OCR to subtitle region only")
        self.crop_subtitle_check.setChecked(bool(settings["ocr_crop_subtitle_only"]))

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

        self.deep_translation_model_edit = QLineEdit(str(settings["deep_translation_model"]))
        self.deep_translation_model_edit.setPlaceholderText("gemini-2.0-flash")

        expanding_fields = (
            self.deep_translation_api_key_edit,
            self.game_profile_title_edit,
            self.game_profile_world_edit,
            self.game_profile_factions_edit,
            self.game_profile_characters_honorifics_edit,
            self.game_profile_terms_items_skills_edit,
            self.ocr_provider_combo,
            self.capture_backend_combo,
            self.capture_fps_spin,
            self.subtitle_mode_check,
            self.crop_subtitle_check,
            self.overlay_fps_spin,
            self.overlay_ttl_spin,
            self.font_size_spin,
            self.translation_log_check,
            self.deep_translation_model_edit,
        )
        for widget in expanding_fields:
            widget.setSizePolicy(QSizePolicy.Expanding, widget.sizePolicy().verticalPolicy())

        deep_form = QFormLayout()
        deep_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        deep_form.setFormAlignment(Qt.AlignTop | Qt.AlignLeft)
        deep_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._add_labeled_row(deep_form, "Gemini API Key", self.deep_translation_api_key_edit)
        self._add_labeled_row(deep_form, "Game Title", self.game_profile_title_edit)
        self._add_labeled_row(deep_form, "World / Setting", self.game_profile_world_edit)
        self._add_labeled_row(deep_form, "Factions / Organizations", self.game_profile_factions_edit)
        self._add_labeled_row(deep_form, "Characters & Honorifics", self.game_profile_characters_honorifics_edit)
        self._add_labeled_row(deep_form, "Terms / Items / Skills", self.game_profile_terms_items_skills_edit)

        advanced_form = QFormLayout()
        advanced_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        advanced_form.setFormAlignment(Qt.AlignTop | Qt.AlignLeft)
        advanced_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._add_labeled_row(advanced_form, "OCR Provider", self.ocr_provider_combo)
        self._add_labeled_row(advanced_form, "Capture Backend", self.capture_backend_combo)
        self._add_labeled_row(advanced_form, "Capture FPS", self.capture_fps_spin)
        self._add_labeled_row(advanced_form, "Subtitle Mode", self.subtitle_mode_check)
        self._add_labeled_row(advanced_form, "Subtitle Crop", self.crop_subtitle_check)
        self._add_labeled_row(advanced_form, "Overlay FPS", self.overlay_fps_spin)
        self._add_labeled_row(advanced_form, "Overlay TTL (s)", self.overlay_ttl_spin)
        self._add_labeled_row(advanced_form, "Font Size", self.font_size_spin)
        self._add_labeled_row(advanced_form, "Logging", self.translation_log_check)
        self._add_labeled_row(advanced_form, "Gemini Model", self.deep_translation_model_edit)
        self.advanced_container = QWidget()
        self.advanced_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.advanced_container.setLayout(advanced_form)
        self.advanced_container.setVisible(self.advanced_check.isChecked())
        self.advanced_check.toggled.connect(self.advanced_container.setVisible)

        deep_column = QWidget()
        deep_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        deep_column_layout = QVBoxLayout()
        deep_column_layout.setContentsMargins(0, 0, 0, 0)
        deep_column_layout.addWidget(QLabel("Deep Translation"))
        deep_column_layout.addWidget(
            QLabel("Deep translation mac dinh dung Gemini. Neu khong nhap API key, he thong se fallback sang ctranslate2.")
        )
        deep_column_layout.addLayout(deep_form)
        deep_column_layout.addWidget(self.advanced_check)
        deep_column_layout.addStretch(1)
        deep_column.setLayout(deep_column_layout)

        self.advanced_column = QWidget()
        self.advanced_column.setVisible(self.advanced_check.isChecked())
        self.advanced_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        advanced_column_layout = QVBoxLayout()
        advanced_column_layout.setContentsMargins(0, 0, 0, 0)
        advanced_column_layout.addWidget(QLabel("Advanced Settings"))
        advanced_column_layout.addWidget(self.advanced_container)
        advanced_column_layout.addStretch(1)
        self.advanced_column.setLayout(advanced_column_layout)
        self.advanced_check.toggled.connect(self.advanced_column.setVisible)

        columns_layout = QHBoxLayout()
        columns_layout.addWidget(deep_column, 3)
        columns_layout.addWidget(self.advanced_column, 2)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(columns_layout)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _add_labeled_row(self, form: QFormLayout, title: str, field: QWidget) -> None:
        tooltip = SETTING_TOOLTIPS.get(title, "")
        label = QLabel(title)
        if tooltip:
            label.setToolTip(tooltip)
            field.setToolTip(tooltip)
        form.addRow(label, field)

    def values(self) -> dict[str, Any]:
        return {
            "ocr_provider": self.ocr_provider_combo.currentText(),
            "capture_backend": self.capture_backend_combo.currentText(),
            "capture_fps": self.capture_fps_spin.value(),
            "subtitle_mode": self.subtitle_mode_check.isChecked(),
            "ocr_crop_subtitle_only": self.crop_subtitle_check.isChecked(),
            "overlay_fps": self.overlay_fps_spin.value(),
            "overlay_ttl_seconds": self.overlay_ttl_spin.value(),
            "translation_log_enabled": self.translation_log_check.isChecked(),
            "font_size": self.font_size_spin.value(),
            "deep_translation_api_key": self.deep_translation_api_key_edit.text().strip(),
            "deep_translation_model": self.deep_translation_model_edit.text().strip(),
            "deep_translation_transport": "rest",
            "game_profile_title": self.game_profile_title_edit.text().strip(),
            "game_profile_world": self.game_profile_world_edit.toPlainText().strip(),
            "game_profile_factions": self.game_profile_factions_edit.toPlainText().strip(),
            "game_profile_characters_honorifics": self.game_profile_characters_honorifics_edit.toPlainText().strip(),
            "game_profile_terms_items_skills": self.game_profile_terms_items_skills_edit.toPlainText().strip(),
            "advanced_settings": self.advanced_check.isChecked(),
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
                settings.update(_normalize_loaded_settings(loaded))
        except Exception:
            pass
    return _normalize_loaded_settings(settings)
