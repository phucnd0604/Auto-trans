from __future__ import annotations

import json
import os
from pathlib import Path

import cv2
import numpy as np

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, Rect
from autotrans.services.ocr import BaseOCRProvider, PaddleOCRProvider
from autotrans.utils.text import normalize_text


ROOT = Path(__file__).resolve().parent
DEFAULT_IMAGES = ("quest1.png", "quest2.png")
LAYOUT_BACKEND = os.environ.get("AUTOTRANS_LAYOUT_BACKEND", "auto").strip().lower() or "auto"
PADDLE_MODEL_ROOT = Path(
    os.environ.get(
        "PADDLE_PDX_CACHE_HOME",
        str(ROOT.parent.parent / ".runtime" / "paddlex-cache"),
    )
).resolve() / "official_models"


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


class _PreviewMergeHelper(BaseOCRProvider):
    def recognize(self, frame: Frame) -> list[OCRBox]:
        return []

    def recognize_paragraphs(self, frame: Frame) -> list[OCRBox]:
        return []


class _PaddleLayoutPreviewProvider:
    name = "paddleocr"

    def __init__(self, config: AppConfig) -> None:
        self._helper = _PreviewMergeHelper(config)
        from paddleocr import LayoutDetection, PaddleOCR

        recognition_model_dir = PADDLE_MODEL_ROOT / "en_PP-OCRv5_mobile_rec"
        if not recognition_model_dir.exists():
            alias_dir = PADDLE_MODEL_ROOT / "latin_PP-OCRv5_mobile_rec"
            if alias_dir.exists():
                recognition_model_dir = alias_dir
            else:
                recognition_model_dir = PADDLE_MODEL_ROOT / "latin_PP-OCRv5_rec_mobile"
        recognition_model_name = "en_PP-OCRv5_mobile_rec"
        if recognition_model_dir.name != recognition_model_name:
            recognition_model_name = recognition_model_dir.name

        self._ocr = PaddleOCR(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_detection_model_dir=str(PADDLE_MODEL_ROOT / "PP-OCRv5_mobile_det"),
            text_recognition_model_name=recognition_model_name,
            text_recognition_model_dir=str(recognition_model_dir),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_det_limit_side_len=192,
            text_recognition_batch_size=8,
        )
        self._layout = LayoutDetection(
            model_name="PP-DocLayout-S",
            model_dir=str(PADDLE_MODEL_ROOT / "PP-DocLayout-S"),
            threshold=0.35,
            layout_nms=True,
        )

    def _recognize_raw_lines(self, frame: Frame) -> list[OCRBox]:
        result = self._ocr.predict(frame.image)[0]
        boxes: list[OCRBox] = []
        for index, (points, text, confidence) in enumerate(
            zip(result["rec_polys"], result["rec_texts"], result["rec_scores"], strict=False)
        ):
            if isinstance(points, np.ndarray):
                points = points.tolist()
            try:
                xs = [int(round(float(point[0]))) for point in points]
                ys = [int(round(float(point[1]))) for point in points]
            except (TypeError, ValueError, IndexError):
                continue
            bbox = Rect(
                x=min(xs),
                y=min(ys),
                width=max(xs) - min(xs),
                height=max(ys) - min(ys),
            )
            normalized = normalize_text(str(text))
            confidence_value = float(confidence)
            if not self._helper._is_meaningful(normalized, bbox, confidence_value):
                continue
            boxes.append(
                OCRBox(
                    id="",
                    source_text=normalized,
                    confidence=confidence_value,
                    bbox=bbox,
                    language_hint="en",
                    line_id=f"paddle-{index}",
                )
            )
        return boxes

    def _detect_layout_regions(self, frame: Frame) -> list[tuple[Rect, str, float]]:
        result = self._layout.predict(frame.image)[0]
        regions: list[tuple[Rect, str, float]] = []
        for item in result["boxes"]:
            label = normalize_text(str(item.get("label", "")))
            if label == "paragraph_title":
                label = "title"
            coordinate = item.get("coordinate") or []
            if len(coordinate) < 4:
                continue
            x1, y1, x2, y2 = [int(round(float(value))) for value in coordinate[:4]]
            rect = Rect(
                x=min(x1, x2),
                y=min(y1, y2),
                width=abs(x2 - x1),
                height=abs(y2 - y1),
            )
            if rect.width < 8 or rect.height < 8:
                continue
            regions.append((rect, label, float(item.get("score", 1.0))))
        return regions

    def recognize(self, frame: Frame) -> list[OCRBox]:
        return self._helper._merge_line_boxes(self._recognize_raw_lines(frame))

    def recognize_paragraphs(self, frame: Frame) -> list[OCRBox]:
        line_boxes = self.recognize(frame)
        layout_regions = self._detect_layout_regions(frame)
        return self._helper._merge_layout_regions(line_boxes, layout_regions, line_separator="\n")


def _make_provider(config: AppConfig):
    if LAYOUT_BACKEND not in {"auto", "pp-structure"}:
        raise RuntimeError(
            f"Unsupported AUTOTRANS_LAYOUT_BACKEND={LAYOUT_BACKEND!r} for paddleocr. "
            "Use auto or pp-structure."
        )
    if (PADDLE_MODEL_ROOT / "PP-OCRv5_mobile_det").exists() and (PADDLE_MODEL_ROOT / "PP-DocLayout-S").exists():
        return _PaddleLayoutPreviewProvider(config)
    return PaddleOCRProvider(config)


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

    provider = _make_provider(config)

    for image_name in DEFAULT_IMAGES:
        image_path = ROOT / image_name
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"Failed to read {image_path}")
            continue

        frame = _make_frame(image)
        line_boxes = provider.recognize(frame)
        deep_boxes = provider.recognize_paragraphs(frame)
        backend_tag = f"paddleocr-{LAYOUT_BACKEND}".replace("-", "_")
        output_image, output_json = _write_outputs(image_path, deep_boxes, backend_tag)

        print(f"=== {image_name} ===")
        print("ocr provider: paddleocr")
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
