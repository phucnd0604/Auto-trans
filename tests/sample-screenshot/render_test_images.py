from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from autotrans.config import AppConfig
from autotrans.models import Frame, QualityMode, Rect
from autotrans.services.ocr import RapidOCRProvider
from autotrans.services.translation import OpenAITranslator, build_default_local_translator


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
)


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in FONT_CANDIDATES:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if width <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def fit_text_layout(
    draw: ImageDraw.ImageDraw,
    text: str,
    width: int,
    height: int,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    usable_width = max(10, width - 4)
    usable_height = max(10, height - 2)
    single_line = height <= 34
    max_size = min(max(int(height * 1.15), 12), 44)

    for font_size in range(max_size, 5, -1):
        font = get_font(font_size)
        if single_line:
            lines = [text]
        else:
            lines = wrap_text(draw, text, font, usable_width)
        line_box = draw.textbbox((0, 0), "Ay", font=font)
        line_height = max(1, line_box[3] - line_box[1]) + 1
        text_block_height = line_height * len(lines)
        max_line_width = max(
            draw.textbbox((0, 0), line, font=font)[2] - draw.textbbox((0, 0), line, font=font)[0]
            for line in lines
        )
        if max_line_width <= usable_width and text_block_height <= usable_height:
            return font, lines, line_height

    font = get_font(6)
    lines = [text] if single_line else wrap_text(draw, text, font, usable_width)
    line_box = draw.textbbox((0, 0), "Ay", font=font)
    line_height = max(1, line_box[3] - line_box[1]) + 1
    return font, lines, line_height


def draw_overlay(image: np.ndarray, x: int, y: int, width: int, height: int, text: str) -> np.ndarray:
    x = max(0, x)
    y = max(0, y)
    width = max(1, width)
    height = max(1, height)
    x2 = min(image.shape[1], x + width)
    y2 = min(image.shape[0], y + height)

    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = Image.new("RGBA", pil_image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(
        (x, y, x2, y2),
        fill=(0, 0, 0, 184),
    )

    pil_image = Image.alpha_composite(pil_image, overlay)
    draw = ImageDraw.Draw(pil_image)

    font, lines, line_height = fit_text_layout(draw, text, x2 - x, y2 - y)
    text_block_height = line_height * len(lines)
    baseline_y = y + max(0, ((y2 - y) - text_block_height) // 2)

    for line in lines:
        line_box = draw.textbbox((0, 0), line, font=font)
        line_width = line_box[2] - line_box[0]
        line_x = x + max(0, ((x2 - x) - line_width) // 2)
        draw.text((line_x, baseline_y), line, font=font, fill=(245, 210, 90, 255))
        baseline_y += line_height

    return cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)


def main() -> None:
    root = Path("tests/sample-screenshot")
    config = AppConfig()
    config.ocr_provider = "rapidocr"
    provider = RapidOCRProvider(config)
    if config.cloud_provider == "openai" and config.openai_base_url:
        translator = OpenAITranslator(
            model=config.openai_model,
            base_url=config.openai_base_url,
            api_key=config.openai_api_key,
        )
    else:
        translator = build_default_local_translator(config)

    for image_path in sorted(root.glob("*.png")):
        if image_path.name.startswith("test-"):
            continue
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"Failed to read {image_path.name}")
            continue
        frame = Frame(image=image.copy(), timestamp=0.0, window_rect=Rect(0, 0, image.shape[1], image.shape[0]))
        boxes = provider.recognize(frame)
        selected = boxes
        translations = translator.translate_batch(selected, "en", "vi", QualityMode.BALANCED)
        translated_by_source = {item.source_text: item.translated_text for item in translations}

        rendered = image.copy()
        for box in selected:
            text = translated_by_source.get(box.source_text, box.source_text)
            rendered = draw_overlay(rendered, box.bbox.x, box.bbox.y, box.bbox.width, box.bbox.height, text)

        output_path = image_path.with_name(f"test-{image_path.name}")
        cv2.imwrite(str(output_path), rendered)
        print(f"{image_path.name}: selected={len(selected)} -> {output_path.name}")
        for box in selected:
            translated = translated_by_source.get(box.source_text, box.source_text)
            print(f"  {box.source_text!r} => {translated!r} @ ({box.bbox.x},{box.bbox.y},{box.bbox.width},{box.bbox.height})")


if __name__ == "__main__":
    main()
