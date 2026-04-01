from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from autotrans.config import AppConfig
from autotrans.models import Frame, OverlayItem, Rect, VisibilityState
from autotrans.services.cache import TranslationCache
from autotrans.services.ocr import PaddleOCRProvider
from autotrans.services.translation import GeminiRestTranslator, GeminiTranslator, WordByWordTranslator


capture_stub = types.ModuleType("autotrans.services.capture")


class CaptureService:
    def capture_window(self, hwnd: int):
        raise NotImplementedError


capture_stub.CaptureService = CaptureService
sys.modules.setdefault("autotrans.services.capture", capture_stub)

from autotrans.services.orchestrator import PipelineOrchestrator


ROOT = Path(__file__).resolve().parent
DEFAULT_IMAGES = ("quest1.png", "quest2.png")
LAYOUT_BACKEND = os.environ.get("AUTOTRANS_LAYOUT_BACKEND", "pp_doclayout_s").strip().lower() or "pp_doclayout_s"
TRANSLATOR_BACKEND = os.environ.get("AUTOTRANS_TRANSLATOR_BACKEND", "word").strip().lower() or "word"
OVERLAY_BRUSH_PATH = ROOT.parent.parent / "src" / "autotrans" / "ui" / "assets" / "overlay-brush.png"

FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/System/Library/Fonts/Supplemental/Helvetica.ttc"),
)


class ImageCapture:
    def __init__(self, image: np.ndarray) -> None:
        self._image = image

    def capture_window(self, hwnd: int):
        height, width = self._image.shape[:2]
        return Frame(
            image=self._image.copy(),
            timestamp=0.0,
            window_rect=Rect(0, 0, width, height),
        )


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in FONT_CANDIDATES:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.replace("\n", " \n ").split()
    if not words:
        return [text]
    lines: list[str] = []
    current = ""
    for word in words:
        if word == "\\n":
            if current:
                lines.append(current)
                current = ""
            continue
        candidate = word if not current else f"{current} {word}"
        line_box = draw.textbbox((0, 0), candidate, font=font)
        line_width = line_box[2] - line_box[0]
        if line_width <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _fit_text_layout(
    draw: ImageDraw.ImageDraw,
    text: str,
    width: int,
    height: int,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    usable_width = max(40, width - 12)
    usable_height = max(20, height - 10)
    max_size = min(max(int(height * 0.6), 14), 34)

    for font_size in range(max_size, 9, -1):
        font = _get_font(font_size)
        lines = _wrap_text(draw, text, font, usable_width)
        line_box = draw.textbbox((0, 0), "Ay", font=font)
        line_height = max(1, line_box[3] - line_box[1]) + 2
        text_height = line_height * len(lines)
        max_line_width = max(
            draw.textbbox((0, 0), line, font=font)[2] - draw.textbbox((0, 0), line, font=font)[0]
            for line in lines
        )
        if max_line_width <= usable_width and text_height <= usable_height:
            return font, lines, line_height

    font = _get_font(10)
    lines = _wrap_text(draw, text, font, usable_width)
    line_box = draw.textbbox((0, 0), "Ay", font=font)
    line_height = max(1, line_box[3] - line_box[1]) + 2
    return font, lines, line_height


def _measure_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    width: int,
    height: int,
) -> tuple[ImageFont.ImageFont, list[str], int, int]:
    font, lines, line_height = _fit_text_layout(draw, text, width, height)
    max_line_width = 0
    for line in lines:
        line_box = draw.textbbox((0, 0), line, font=font)
        max_line_width = max(max_line_width, line_box[2] - line_box[0])
    text_height = line_height * len(lines)
    return font, lines, line_height, max_line_width, text_height


def _draw_overlay_item(image: np.ndarray, item: OverlayItem) -> np.ndarray:
    x1 = max(0, item.bbox.x)
    y1 = max(0, item.bbox.y)
    x2 = min(image.shape[1], item.bbox.right)
    y2 = min(image.shape[0], item.bbox.bottom)
    if x2 <= x1 or y2 <= y1:
        return image

    text_color = (245, 210, 90, 255)
    border = (90, 220, 255, 255)
    if item.visibility_state == VisibilityState.PENDING:
        text_color = (220, 232, 255, 255)

    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).convert("RGBA")
    draw = ImageDraw.Draw(pil_image)
    font, lines, line_height, text_block_width, text_block_height = _measure_text_block(
        draw,
        item.translated_text,
        x2 - x1,
        y2 - y1,
    )

    text_rect_width = min(max(text_block_width, 1), max(x2 - x1, 1))
    text_rect_height = min(max(text_block_height, 1), max(y2 - y1, 1))
    text_left = x1 + max(0, ((x2 - x1) - text_rect_width) // 2)
    text_top = y1 + max(0, ((y2 - y1) - text_rect_height) // 2)
    background_left = max(0, text_left - 12)
    background_top = max(0, text_top - 6)
    background_right = min(image.shape[1], text_left + text_rect_width + 12)
    background_bottom = min(image.shape[0], text_top + text_rect_height + 6)

    brush = None
    if OVERLAY_BRUSH_PATH.exists():
        brush = Image.open(OVERLAY_BRUSH_PATH).convert("RGBA")
    if brush is not None:
        brush = brush.resize(
            (max(background_right - background_left, 1), max(background_bottom - background_top, 1)),
            Image.Resampling.LANCZOS,
        )
        pil_image.alpha_composite(brush, (background_left, background_top))
    else:
        overlay = Image.new("RGBA", pil_image.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(
            (background_left, background_top, background_right, background_bottom),
            radius=6,
            fill=(0, 0, 0, 214),
        )
        pil_image = Image.alpha_composite(pil_image, overlay)
        draw = ImageDraw.Draw(pil_image)

    if item.visibility_state == VisibilityState.PENDING:
        draw.rounded_rectangle(
            (background_left, background_top, background_right, background_bottom),
            radius=6,
            outline=border,
            width=1,
        )

    baseline_y = text_top

    for line in lines:
        line_box = draw.textbbox((0, 0), line, font=font)
        line_width = line_box[2] - line_box[0]
        line_x = text_left + max(0, (text_rect_width - line_width) // 2)
        draw.text((line_x, baseline_y), line, font=font, fill=text_color)
        baseline_y += line_height

    return cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)


def _make_deep_provider(config: AppConfig) -> PaddleOCRProvider:
    if LAYOUT_BACKEND not in {"auto", "pp_doclayout_s", "pp-structure"}:
        raise RuntimeError(
            f"Unsupported AUTOTRANS_LAYOUT_BACKEND={LAYOUT_BACKEND!r}. Use auto, pp_doclayout_s, or pp-structure."
        )
    return PaddleOCRProvider(config)


def _make_cloud_translator(config: AppConfig):
    if TRANSLATOR_BACKEND == "gemini":
        if not config.deep_translation_api_key:
            raise RuntimeError("Gemini translator requested but AUTOTRANS_DEEP_TRANSLATION_API_KEY is empty")
        return GeminiTranslator(
            model=config.deep_translation_model,
            api_key=config.deep_translation_api_key,
            config=config,
            timeout_s=max(config.cloud_timeout_ms, config.deep_translation_timeout_ms) / 1000.0,
            verbose=config.translation_log_enabled,
            max_logged_items=config.translation_log_max_items,
        )
    if TRANSLATOR_BACKEND == "gemini-rest":
        if not config.deep_translation_api_key:
            raise RuntimeError("Gemini REST translator requested but AUTOTRANS_DEEP_TRANSLATION_API_KEY is empty")
        return GeminiRestTranslator(
            model=config.deep_translation_model,
            api_key=config.deep_translation_api_key,
            config=config,
            timeout_s=max(config.cloud_timeout_ms, config.deep_translation_timeout_ms) / 1000.0,
            verbose=config.translation_log_enabled,
            max_logged_items=config.translation_log_max_items,
        )
    return None


def _make_local_translator():
    return WordByWordTranslator()


def _write_outputs(
    image_path: Path,
    grouped_boxes,
    pending_items: list[OverlayItem],
    final_items: list[OverlayItem],
    backend_tag: str,
    translator_tag: str,
) -> tuple[Path, Path, Path]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Failed to read {image_path}")

    pending_render = image.copy()
    for item in pending_items:
        pending_render = _draw_overlay_item(pending_render, item)

    final_render = image.copy()
    for item in final_items:
        final_render = _draw_overlay_item(final_render, item)

    payload = {
        "grouped_boxes": [
            {
                "source_text": box.source_text,
                "confidence": round(float(box.confidence), 4),
                "bbox": {
                    "x": box.bbox.x,
                    "y": box.bbox.y,
                    "width": box.bbox.width,
                    "height": box.bbox.height,
                },
                "line_id": box.line_id,
            }
            for box in grouped_boxes
        ],
        "pending_overlay_items": [
            {
                "text": item.translated_text,
                "source_text": item.source_text,
                "visibility_state": item.visibility_state.value,
                "bbox": {
                    "x": item.bbox.x,
                    "y": item.bbox.y,
                    "width": item.bbox.width,
                    "height": item.bbox.height,
                },
            }
            for item in pending_items
        ],
        "final_overlay_items": [
            {
                "text": item.translated_text,
                "source_text": item.source_text,
                "visibility_state": item.visibility_state.value,
                "region": item.region,
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

    suffix = f"deepmode-runtime-{backend_tag}-{translator_tag}"
    pending_image = image_path.with_name(f"{image_path.stem}.{suffix}-pending.png")
    final_image = image_path.with_name(f"{image_path.stem}.{suffix}-final.png")
    output_json = image_path.with_name(f"{image_path.stem}.{suffix}.json")
    cv2.imwrite(str(pending_image), pending_render)
    cv2.imwrite(str(final_image), final_render)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return pending_image, final_image, output_json


def main() -> None:
    config = AppConfig()
    config.ocr_provider = "paddleocr"
    config.subtitle_mode = False
    config.ocr_crop_subtitle_only = False
    config.ocr_max_boxes = 0
    config.ocr_preprocess = True
    config.ocr_min_confidence = 0.25
    config.translation_log_enabled = True
    config.translation_log_max_items = 20

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
            ocr_provider=_make_deep_provider(config),
            deep_ocr_provider=_make_deep_provider(config),
            local_translator=_make_local_translator(),
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
        for index, item in enumerate(final_items, start=1):
            print(
                f"[{index}] src={item.source_text!r} -> dst={item.translated_text!r} "
                f"bbox=({item.bbox.x},{item.bbox.y},{item.bbox.width},{item.bbox.height}) "
                f"region={item.region!r}"
            )


if __name__ == "__main__":
    main()
