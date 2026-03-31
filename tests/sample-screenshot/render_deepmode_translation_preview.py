from __future__ import annotations

import json
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, Rect
from autotrans.services.ocr import RapidOCRProvider
from autotrans.services.translation import (
    GeminiRestTranslator,
    GeminiTranslator,
    TranslationResult,
    WordByWordTranslator,
    build_default_local_translator,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_IMAGES = ("quest1.png", "quest2.png")
LAYOUT_BACKEND = os.environ.get("AUTOTRANS_LAYOUT_BACKEND", "rapid-layout").strip().lower() or "rapid-layout"
TRANSLATOR_BACKEND = os.environ.get("AUTOTRANS_TRANSLATOR_BACKEND", "word").strip().lower() or "word"

FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/System/Library/Fonts/Supplemental/Helvetica.ttc"),
)


def _make_frame(image: np.ndarray) -> Frame:
    height, width = image.shape[:2]
    return Frame(
        image=image.copy(),
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


def _draw_translated_overlay(image: np.ndarray, box: OCRBox, translated_text: str) -> np.ndarray:
    x1 = max(0, box.bbox.x)
    y1 = max(0, box.bbox.y)
    x2 = min(image.shape[1], box.bbox.right)
    y2 = min(image.shape[0], box.bbox.bottom)

    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = Image.new("RGBA", pil_image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle((x1, y1, x2, y2), radius=8, fill=(8, 8, 8, 214), outline=(88, 220, 140, 255), width=3)

    pil_image = Image.alpha_composite(pil_image, overlay)
    draw = ImageDraw.Draw(pil_image)

    font, lines, line_height = _fit_text_layout(draw, translated_text, x2 - x1, y2 - y1)
    text_block_height = line_height * len(lines)
    baseline_y = y1 + max(4, ((y2 - y1) - text_block_height) // 2)

    for line in lines:
        line_box = draw.textbbox((0, 0), line, font=font)
        line_width = line_box[2] - line_box[0]
        line_x = x1 + max(6, ((x2 - x1) - line_width) // 2)
        draw.text((line_x, baseline_y), line, font=font, fill=(248, 232, 168, 255))
        baseline_y += line_height

    return cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)


def _make_provider(config: AppConfig) -> RapidOCRProvider:
    provider = RapidOCRProvider(config)
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


def _make_translator(config: AppConfig):
    if TRANSLATOR_BACKEND == "word":
        return WordByWordTranslator()
    if TRANSLATOR_BACKEND == "ctranslate2":
        return build_default_local_translator(config)
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
    raise RuntimeError(
        f"Unsupported AUTOTRANS_TRANSLATOR_BACKEND={TRANSLATOR_BACKEND!r}. "
        "Use word, ctranslate2, gemini, or gemini-rest."
    )


def _write_outputs(
    image_path: Path,
    grouped_boxes: list[OCRBox],
    translations: list[TranslationResult],
    backend_tag: str,
    translator_tag: str,
) -> tuple[Path, Path]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Failed to read {image_path}")

    translated_by_source = {item.source_text: item for item in translations}
    rendered = image.copy()
    payload: list[dict[str, object]] = []
    for index, box in enumerate(grouped_boxes, start=1):
        result = translated_by_source.get(box.source_text)
        translated_text = result.translated_text if result is not None else box.source_text
        rendered = _draw_translated_overlay(rendered, box, translated_text)
        payload.append(
            {
                "index": index,
                "source_text": box.source_text,
                "translated_text": translated_text,
                "confidence": round(float(box.confidence), 4),
                "bbox": {
                    "x": box.bbox.x,
                    "y": box.bbox.y,
                    "width": box.bbox.width,
                    "height": box.bbox.height,
                },
                "line_id": box.line_id,
                "provider": result.provider if result is not None else "",
            }
        )

    suffix = f"deepmode-{backend_tag}-{translator_tag}-overlay"
    output_image = image_path.with_name(f"{image_path.stem}.{suffix}.png")
    output_json = image_path.with_name(f"{image_path.stem}.{suffix}.json")
    cv2.imwrite(str(output_image), rendered)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_image, output_json


def main() -> None:
    config = AppConfig()
    config.ocr_provider = "rapidocr"
    config.subtitle_mode = False
    config.ocr_crop_subtitle_only = False
    config.ocr_max_boxes = 0
    config.ocr_preprocess = True
    config.ocr_min_confidence = 0.25
    config.translation_log_enabled = True
    config.translation_log_max_items = 20

    provider = _make_provider(config)
    translator = _make_translator(config)

    backend_tag = LAYOUT_BACKEND.replace("-", "_")
    translator_tag = TRANSLATOR_BACKEND.replace("-", "_")

    for image_name in DEFAULT_IMAGES:
        image_path = ROOT / image_name
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"Failed to read {image_path}")
            continue

        frame = _make_frame(image)
        grouped_boxes = provider.recognize_paragraphs(frame)
        translations = translator.translate_screen_blocks(
            items=grouped_boxes,
            source_lang=config.source_lang,
            target_lang=config.target_lang,
        )
        output_image, output_json = _write_outputs(
            image_path=image_path,
            grouped_boxes=grouped_boxes,
            translations=translations,
            backend_tag=backend_tag,
            translator_tag=translator_tag,
        )

        print(f"=== {image_name} ===")
        print(f"layout backend mode: {LAYOUT_BACKEND}")
        print(f"translator backend mode: {TRANSLATOR_BACKEND}")
        print(f"deep grouped boxes: {len(grouped_boxes)}")
        print(f"image output: {output_image}")
        print(f"json output: {output_json}")
        for index, (box, result) in enumerate(zip(grouped_boxes, translations, strict=False), start=1):
            print(
                f"[{index}] src={box.source_text!r} -> dst={result.translated_text!r} "
                f"bbox=({box.bbox.x},{box.bbox.y},{box.bbox.width},{box.bbox.height}) "
                f"provider={result.provider}"
            )


if __name__ == "__main__":
    main()
