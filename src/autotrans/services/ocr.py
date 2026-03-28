from __future__ import annotations

import os
from typing import Protocol

import numpy as np

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, Rect
from autotrans.utils.text import normalize_text


class OCRProvider(Protocol):
    name: str

    def recognize(self, frame: Frame) -> list[OCRBox]:
        ...


class MockOCRProvider:
    name = "mock"

    def recognize(self, frame: Frame) -> list[OCRBox]:
        width = frame.window_rect.width
        height = frame.window_rect.height
        return [
            OCRBox(
                id="",
                source_text="Quest accepted",
                confidence=0.96,
                bbox=Rect(x=int(width * 0.1), y=int(height * 0.1), width=220, height=36),
                language_hint="en",
                line_id="line-0",
            ),
            OCRBox(
                id="",
                source_text="Start adventure",
                confidence=0.90,
                bbox=Rect(x=int(width * 0.1), y=int(height * 0.2), width=320, height=44),
                language_hint="en",
                line_id="line-1",
            ),
        ]


class FallbackOCRProvider:
    def __init__(self, primary: OCRProvider, secondary: OCRProvider) -> None:
        self.name = f"{getattr(primary, 'name', 'primary')}+fallback"
        self._primary = primary
        self._secondary = secondary
        self._primary_failed = False

    def recognize(self, frame: Frame) -> list[OCRBox]:
        if not self._primary_failed:
            try:
                return self._primary.recognize(frame)
            except Exception as exc:
                self._primary_failed = True
                print(f"[AutoTrans] OCR primary failed, switching to fallback: {exc}", flush=True)
        return self._secondary.recognize(frame)


class BaseOCRProvider:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    @staticmethod
    def _text_score(text: str) -> int:
        return sum(char.isalnum() for char in text)

    def _is_meaningful(self, text: str, bbox: Rect, confidence: float) -> bool:
        normalized = normalize_text(text)
        if not normalized or confidence < self._config.ocr_min_confidence:
            return False
        if bbox.width < 8 or bbox.height < 8:
            return False
        if self._text_score(normalized) < 1:
            return False
        if len(normalized) < 1:
            return False
        return True

    def _merge_line_boxes(self, boxes: list[OCRBox]) -> list[OCRBox]:
        if not boxes:
            return []

        boxes = sorted(boxes, key=lambda item: (item.bbox.y, item.bbox.x))
        merged: list[list[OCRBox]] = []

        for box in boxes:
            placed = False
            box_center_y = box.bbox.y + (box.bbox.height / 2)
            for group in merged:
                anchor = group[-1]
                anchor_center_y = anchor.bbox.y + (anchor.bbox.height / 2)
                avg_height = (anchor.bbox.height + box.bbox.height) / 2
                gap_x = box.bbox.x - anchor.bbox.right
                if abs(box_center_y - anchor_center_y) <= avg_height * 0.45 and gap_x <= avg_height * 1.5:
                    group.append(box)
                    placed = True
                    break
            if not placed:
                merged.append([box])

        output: list[OCRBox] = []
        for line_index, group in enumerate(merged):
            if len(group) == 1:
                output.append(group[0])
                continue
            text = " ".join(item.source_text for item in group)
            x = min(item.bbox.x for item in group)
            y = min(item.bbox.y for item in group)
            right = max(item.bbox.right for item in group)
            bottom = max(item.bbox.bottom for item in group)
            output.append(
                OCRBox(
                    id="",
                    source_text=normalize_text(text),
                    confidence=sum(item.confidence for item in group) / len(group),
                    bbox=Rect(x=x, y=y, width=right - x, height=bottom - y),
                    language_hint=group[0].language_hint,
                    line_id=f"merged-{line_index}",
                )
            )

        output.sort(key=lambda item: (item.bbox.width * item.bbox.height), reverse=True)
        if self._config.ocr_max_boxes > 0:
            output = output[: self._config.ocr_max_boxes]
        output.sort(key=lambda item: (item.bbox.y, item.bbox.x))
        return output


class RapidOCRProvider(BaseOCRProvider):
    name = "rapidocr"

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def _resize_for_ocr(self, image: np.ndarray) -> tuple[np.ndarray, float]:
        height, width = image.shape[:2]
        longest = max(height, width)
        if longest <= self._config.ocr_max_side:
            return image, 1.0

        scale = self._config.ocr_max_side / float(longest)
        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        import cv2

        resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
        return resized, 1.0 / scale

    def recognize(self, frame: Frame) -> list[OCRBox]:
        image, scale_back = self._resize_for_ocr(frame.image)
        result, _ = self._engine(image)
        boxes: list[OCRBox] = []
        if not result:
            return boxes

        for index, item in enumerate(result):
            points, text, confidence = item
            normalized = normalize_text(text)
            confidence_value = float(confidence)
            xs = [int(point[0] * scale_back) for point in points]
            ys = [int(point[1] * scale_back) for point in points]
            bbox = Rect(
                x=min(xs),
                y=min(ys),
                width=max(xs) - min(xs),
                height=max(ys) - min(ys),
            )
            if not self._is_meaningful(normalized, bbox, confidence_value):
                continue
            boxes.append(
                OCRBox(
                    id="",
                    source_text=normalized,
                    confidence=confidence_value,
                    bbox=bbox,
                    language_hint="en",
                    line_id=f"rapid-{index}",
                )
            )

        return self._merge_line_boxes(boxes)


class PaddleOCRProvider(BaseOCRProvider):
    name = "paddle"

    _LANG_MAP = {
        "en": "en",
        "jp": "japan",
        "ja": "japan",
    }

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

        from paddleocr import PaddleOCR

        requested = config.ocr_languages or ("en", "jp")
        self._ocr_engines: dict[str, object] = {}
        for language in requested:
            paddle_lang = self._LANG_MAP.get(language.lower())
            if not paddle_lang or language.lower() in self._ocr_engines:
                continue
            self._ocr_engines[language.lower()] = PaddleOCR(
                lang=paddle_lang,
                ocr_version=config.paddle_ocr_version,
                use_textline_orientation=config.paddle_use_textline_orientation,
                text_det_limit_side_len=config.paddle_text_det_limit_side_len,
                text_det_thresh=config.paddle_text_det_thresh,
                text_det_box_thresh=config.paddle_text_det_box_thresh,
                text_det_unclip_ratio=config.paddle_text_det_unclip_ratio,
                text_rec_score_thresh=config.paddle_text_rec_score_thresh,
            )
        if not self._ocr_engines:
            raise RuntimeError("No valid OCR languages configured")

    def _resize_for_ocr(self, image: np.ndarray) -> tuple[np.ndarray, float]:
        height, width = image.shape[:2]
        longest = max(height, width)
        if longest <= self._config.ocr_max_side:
            return image, 1.0

        scale = self._config.ocr_max_side / float(longest)
        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        import cv2

        resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
        return resized, 1.0 / scale

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        if not self._config.ocr_preprocess:
            return image

        import cv2

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        denoised = cv2.bilateralFilter(gray, 5, 40, 40)
        enhanced = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

    def recognize(self, frame: Frame) -> list[OCRBox]:
        processed = self._preprocess(frame.image)
        resized, scale_back = self._resize_for_ocr(processed)
        boxes: list[OCRBox] = []
        seen: set[tuple[int, int, int, int, str]] = set()

        for language_hint, engine in self._ocr_engines.items():
            results = engine.predict(resized)
            for line_index, line in enumerate(results or []):
                rec_texts = line.get('rec_texts', []) if isinstance(line, dict) else []
                rec_scores = line.get('rec_scores', []) if isinstance(line, dict) else []
                rec_polys = line.get('rec_polys', []) if isinstance(line, dict) else []
                for item_index, text in enumerate(rec_texts):
                    points = rec_polys[item_index]
                    confidence = float(rec_scores[item_index]) if item_index < len(rec_scores) else 0.0
                    normalized = normalize_text(text)
                    xs = [int(point[0] * scale_back) for point in points]
                    ys = [int(point[1] * scale_back) for point in points]
                    bbox = Rect(
                        x=min(xs),
                        y=min(ys),
                        width=max(xs) - min(xs),
                        height=max(ys) - min(ys),
                    )
                    if not self._is_meaningful(normalized, bbox, confidence):
                        continue
                    dedupe_key = (bbox.x, bbox.y, bbox.width, bbox.height, normalized)
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    boxes.append(
                        OCRBox(
                            id="",
                            source_text=normalized,
                            confidence=confidence,
                            bbox=bbox,
                            language_hint=language_hint,
                            line_id=f"{language_hint}-{line_index}-{item_index}",
                        )
                    )

        return self._merge_line_boxes(boxes)

