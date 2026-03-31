from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import cv2
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from autotrans.config import AppConfig
from autotrans.models import Frame, Rect
from autotrans.services.cache import TranslationCache
from autotrans.services.ocr import RapidOCRProvider
from autotrans.ui.settings_dialog import load_startup_settings
from autotrans.services.translation import (
    GeminiRestTranslator,
    GeminiTranslator,
    WordByWordTranslator,
    build_default_local_translator,
)


capture_stub = types.ModuleType("autotrans.services.capture")


class CaptureService:
    def capture_window(self, hwnd: int):
        raise NotImplementedError


capture_stub.CaptureService = CaptureService
capture_stub.WindowsWindowCapture = CaptureService
sys.modules.setdefault("autotrans.services.capture", capture_stub)

hotkeys_stub = types.ModuleType("autotrans.ui.global_hotkeys")


class GlobalHotkeyManager:
    def unregister_all(self) -> None:
        return None


hotkeys_stub.GlobalHotkeyManager = GlobalHotkeyManager
sys.modules.setdefault("autotrans.ui.global_hotkeys", hotkeys_stub)

main_window_stub = types.ModuleType("autotrans.ui.main_window")


class MainWindow:
    pass


main_window_stub.MainWindow = MainWindow
sys.modules.setdefault("autotrans.ui.main_window", main_window_stub)

from autotrans.services.orchestrator import PipelineOrchestrator
from autotrans.ui.overlay import OverlayWindow
from autotrans.app import (
    _apply_startup_settings,
    _build_cloud_translator,
    _build_local_translator,
    _build_ocr_provider,
    _prepare_runtime_environment,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_IMAGES = ("quest1.png", "quest2.png")
LAYOUT_BACKEND = os.environ.get("AUTOTRANS_LAYOUT_BACKEND", "rapid-layout").strip().lower() or "rapid-layout"
TRANSLATOR_BACKEND = os.environ.get("AUTOTRANS_TRANSLATOR_BACKEND", "word").strip().lower() or "word"
DOTENV_PATH = ROOT.parent.parent / ".env"


class ImageCapture:
    def __init__(self, image) -> None:
        self._image = image

    def capture_window(self, hwnd: int):
        height, width = self._image.shape[:2]
        return Frame(
            image=self._image.copy(),
            timestamp=0.0,
            window_rect=Rect(0, 0, width, height),
        )


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _make_provider(config: AppConfig) -> RapidOCRProvider:
    provider = _build_ocr_provider(config)
    if LAYOUT_BACKEND == "rapid-layout":
        provider._paddlex_layout_disabled = True
        provider._paddlex_layout_model = None
    elif LAYOUT_BACKEND == "paddlex":
        provider._layout_disabled = True
        provider._layout_engine = None
    elif LAYOUT_BACKEND != "auto":
        raise RuntimeError(
            f"Unsupported AUTOTRANS_LAYOUT_BACKEND={LAYOUT_BACKEND!r}. Use auto, paddlex, or rapid-layout."
        )
    return provider


def _make_cloud_translator(config: AppConfig):
    if TRANSLATOR_BACKEND in {"gemini", "gemini-rest"}:
        config.deep_translation_transport = "rest" if TRANSLATOR_BACKEND == "gemini-rest" else "sdk"
        return _build_cloud_translator(config)
    return None


def _make_local_translator(config: AppConfig):
    if TRANSLATOR_BACKEND == "ctranslate2":
        return _build_local_translator(config)
    return WordByWordTranslator()


def _render_overlay_exact(image, overlay_items, overlay_fps: int, ttl_seconds: float):
    app = QApplication.instance() or QApplication([])
    overlay = OverlayWindow(ttl_seconds=ttl_seconds, overlay_fps=overlay_fps)
    overlay.sync_window_rect(Rect(0, 0, image.shape[1], image.shape[0]))
    overlay.clear_overlay_items()
    overlay.set_persistent_overlay_items(overlay_items)
    overlay.resize(image.shape[1], image.shape[0])
    overlay.show()
    app.processEvents()

    qimage = QImage(image.shape[1], image.shape[0], QImage.Format_ARGB32_Premultiplied)
    qimage.fill(0)
    painter = QPainter(qimage)
    try:
        overlay.render(painter, QPoint(0, 0), QRect(0, 0, image.shape[1], image.shape[0]))
    finally:
        painter.end()

    ptr = qimage.bits()
    overlay_array = bytes(ptr)
    import numpy as np

    overlay_rgba = np.frombuffer(overlay_array, dtype=np.uint8).reshape((image.shape[0], image.shape[1], 4))
    overlay_bgra = overlay_rgba.copy()
    base_bgra = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    alpha = overlay_bgra[:, :, 3:4].astype("float32") / 255.0
    composed = overlay_bgra[:, :, :3].astype("float32") * alpha + base_bgra[:, :, :3].astype("float32") * (1.0 - alpha)
    overlay.close()
    return composed.astype("uint8")


def _write_outputs(image_path: Path, grouped_boxes, pending_items, final_items, backend_tag: str, translator_tag: str):
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Failed to read {image_path}")

    pending_render = _render_overlay_exact(image, pending_items, overlay_fps=30, ttl_seconds=1.5)
    final_render = _render_overlay_exact(image, final_items, overlay_fps=30, ttl_seconds=1.5)

    payload = {
        "grouped_box_count": len(grouped_boxes),
        "pending_overlay_count": len(pending_items),
        "final_overlay_count": len(final_items),
        "final_overlay_items": [
            {
                "text": item.translated_text,
                "source_text": item.source_text,
                "region": item.region,
                "visibility_state": item.visibility_state.value,
                "bbox": {
                    "x": item.bbox.x,
                    "y": item.bbox.y,
                    "width": item.bbox.width,
                    "height": item.bbox.height,
                },
            }
            for item in final_items
        ],
    }

    suffix = f"deepmode-runtime-qt-{backend_tag}-{translator_tag}"
    pending_image = image_path.with_name(f"{image_path.stem}.{suffix}-pending.png")
    final_image = image_path.with_name(f"{image_path.stem}.{suffix}-final.png")
    output_json = image_path.with_name(f"{image_path.stem}.{suffix}.json")
    cv2.imwrite(str(pending_image), pending_render)
    cv2.imwrite(str(final_image), final_render)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return pending_image, final_image, output_json


def main() -> None:
    dotenv_values = _load_dotenv(DOTENV_PATH)
    if not os.environ.get("AUTOTRANS_DEEP_TRANSLATION_API_KEY"):
        alias_key = dotenv_values.get("AUTOTRANS_DEEP_TRANSLATION_API_KEY") or dotenv_values.get("GOOGLE_GEMINI_API_KEY")
        if alias_key:
            os.environ["AUTOTRANS_DEEP_TRANSLATION_API_KEY"] = alias_key

    config = AppConfig()
    settings_path = Path(config.runtime_root_dir) / "ui-settings.json"
    initial_settings = load_startup_settings(settings_path)
    config = _apply_startup_settings(config, initial_settings)
    env_model = os.environ.get("AUTOTRANS_DEEP_TRANSLATION_MODEL", "").strip()
    env_transport = os.environ.get("AUTOTRANS_DEEP_TRANSLATION_TRANSPORT", "").strip().lower()
    if not config.deep_translation_api_key:
        alias_key = dotenv_values.get("AUTOTRANS_DEEP_TRANSLATION_API_KEY") or dotenv_values.get("GOOGLE_GEMINI_API_KEY")
        if alias_key:
            config.deep_translation_api_key = alias_key
    if env_model:
        config.deep_translation_model = env_model
    if env_transport in {"sdk", "rest"}:
        config.deep_translation_transport = env_transport
    config.ocr_provider = "rapidocr"
    config.local_translator_backend = "ctranslate2"
    config.subtitle_mode = False
    config.ocr_crop_subtitle_only = False
    config.ocr_max_boxes = 0
    config.ocr_preprocess = True
    config.ocr_min_confidence = 0.25
    config.translation_log_enabled = True
    config.translation_log_max_items = 20
    _prepare_runtime_environment(config)

    backend_tag = LAYOUT_BACKEND.replace("-", "_")
    translator_tag = TRANSLATOR_BACKEND.replace("-", "_")

    for image_name in DEFAULT_IMAGES:
        image_path = ROOT / image_name
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"Failed to read {image_path}")
            continue

        orchestrator = PipelineOrchestrator(
            config=config,
            capture_service=ImageCapture(image),
            ocr_provider=_make_provider(config),
            local_translator=_make_local_translator(config),
            cloud_translator=_make_cloud_translator(config),
            cache=TranslationCache(),
        )
        grouped_boxes, pending_items = orchestrator.prepare_deep_translation(1)
        final_items = orchestrator.translate_deep_boxes(grouped_boxes)
        pending_image, final_image, output_json = _write_outputs(
            image_path=image_path,
            grouped_boxes=grouped_boxes,
            pending_items=pending_items,
            final_items=final_items,
            backend_tag=backend_tag,
            translator_tag=translator_tag,
        )

        print(f"=== {image_name} ===")
        print(f"layout backend mode: {LAYOUT_BACKEND}")
        print(f"translator backend mode: {TRANSLATOR_BACKEND}")
        print(f"grouped boxes: {len(grouped_boxes)}")
        print(f"pending overlay items: {len(pending_items)}")
        print(f"final overlay items: {len(final_items)}")
        print(f"pending image: {pending_image}")
        print(f"final image: {final_image}")
        print(f"json output: {output_json}")


if __name__ == "__main__":
    main()
