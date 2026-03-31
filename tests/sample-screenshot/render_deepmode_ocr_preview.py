from __future__ import annotations

import json
import os
from pathlib import Path

import cv2

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, Rect
from autotrans.services.ocr import RapidOCRProvider


ROOT = Path(__file__).resolve().parent
DEFAULT_IMAGES = ("quest1.png", "quest2.png")
LAYOUT_BACKEND = os.environ.get("AUTOTRANS_LAYOUT_BACKEND", "auto").strip().lower() or "auto"


def _make_frame(image):
    height, width = image.shape[:2]
    return Frame(
        image=image.copy(),
        timestamp=0.0,
        window_rect=Rect(0, 0, width, height),
    )


def _draw_box(image, box: OCRBox, index: int) -> None:
    x1 = box.bbox.x
    y1 = box.bbox.y
    x2 = box.bbox.right
    y2 = box.bbox.bottom
    cv2.rectangle(image, (x1, y1), (x2, y2), (40, 220, 120), 3)

    label = f"{index}: {box.source_text[:80]}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    thickness = 2
    (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
    label_x = max(0, x1)
    label_y = max(text_height + 8, y1 - 10)
    panel_x2 = min(image.shape[1] - 1, label_x + text_width + 12)
    panel_y1 = max(0, label_y - text_height - 8)
    panel_y2 = min(image.shape[0] - 1, label_y + baseline + 4)
    cv2.rectangle(image, (label_x, panel_y1), (panel_x2, panel_y2), (0, 0, 0), -1)
    cv2.putText(
        image,
        label,
        (label_x + 6, label_y),
        font,
        font_scale,
        (240, 240, 240),
        thickness,
        cv2.LINE_AA,
    )


def _write_outputs(image_path: Path, boxes: list[OCRBox], backend_tag: str) -> tuple[Path, Path]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Failed to read {image_path}")

    preview = image.copy()
    payload: list[dict[str, object]] = []
    for index, box in enumerate(boxes, start=1):
        _draw_box(preview, box, index)
        payload.append(
            {
                "index": index,
                "text": box.source_text,
                "confidence": round(float(box.confidence), 4),
                "bbox": {
                    "x": box.bbox.x,
                    "y": box.bbox.y,
                    "width": box.bbox.width,
                    "height": box.bbox.height,
                },
                "line_id": box.line_id,
            }
        )

    output_image = image_path.with_name(f"{image_path.stem}.deepmode-{backend_tag}-ocr-boxes.png")
    output_json = image_path.with_name(f"{image_path.stem}.deepmode-{backend_tag}-ocr-boxes.json")
    cv2.imwrite(str(output_image), preview)
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

    provider = RapidOCRProvider(config)
    if LAYOUT_BACKEND == "rapid-layout":
        provider._paddlex_layout_disabled = True
        provider._paddlex_layout_model = None
    elif LAYOUT_BACKEND == "paddlex":
        provider._layout_disabled = True
        provider._layout_engine = None
    elif LAYOUT_BACKEND != "auto":
        raise RuntimeError(
            f"Unsupported AUTOTRANS_LAYOUT_BACKEND={LAYOUT_BACKEND!r}. "
            "Use auto, paddlex, or rapid-layout."
        )

    for image_name in DEFAULT_IMAGES:
        image_path = ROOT / image_name
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"Failed to read {image_path}")
            continue

        frame = _make_frame(image)
        line_boxes = provider.recognize(frame)
        deep_boxes = provider.recognize_paragraphs(frame)
        output_image, output_json = _write_outputs(image_path, deep_boxes, LAYOUT_BACKEND.replace("-", "_"))

        print(f"=== {image_name} ===")
        print(f"layout backend mode: {LAYOUT_BACKEND}")
        print(f"line boxes: {len(line_boxes)}")
        print(f"deep grouped boxes: {len(deep_boxes)}")
        print(f"image output: {output_image}")
        print(f"json output: {output_json}")
        for index, box in enumerate(deep_boxes, start=1):
            print(
                f"[{index}] text={box.source_text!r} "
                f"conf={box.confidence:.3f} "
                f"bbox=({box.bbox.x},{box.bbox.y},{box.bbox.width},{box.bbox.height}) "
                f"line_id={box.line_id!r}"
            )


if __name__ == "__main__":
    main()
