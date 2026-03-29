from __future__ import annotations

import time
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


class BaseOCRProvider:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def _log(self, message: str) -> None:
        if self._config.translation_log_enabled:
            print(f"[AutoTrans][OCR] {message}", flush=True)

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
                max_gap_x = max(18, int(avg_height * 0.75))
                min_gap_x = -int(avg_height * 0.35)
                if (
                    abs(box_center_y - anchor_center_y) <= avg_height * 0.35
                    and min_gap_x <= gap_x <= max_gap_x
                ):
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

    def _merge_paragraph_boxes(self, boxes: list[OCRBox]) -> list[OCRBox]:
        if len(boxes) <= 1:
            return boxes

        ordered = sorted(boxes, key=lambda item: (item.bbox.y, item.bbox.x))
        groups: list[list[OCRBox]] = []
        for box in ordered:
            placed = False
            for group in groups:
                anchor = group[0]
                previous = group[-1]
                if self._same_paragraph(anchor, previous, box):
                    group.append(box)
                    placed = True
                    break
            if not placed:
                groups.append([box])

        if len(groups) == len(boxes):
            return boxes

        merged: list[OCRBox] = []
        for index, group in enumerate(groups):
            if len(group) == 1:
                merged.append(group[0])
                continue
            x = min(item.bbox.x for item in group)
            y = min(item.bbox.y for item in group)
            right = max(item.bbox.right for item in group)
            bottom = max(item.bbox.bottom for item in group)
            merged.append(
                OCRBox(
                    id="",
                    source_text=normalize_text(" ".join(item.source_text for item in group)),
                    confidence=sum(item.confidence for item in group) / len(group),
                    bbox=Rect(x=x, y=y, width=right - x, height=bottom - y),
                    language_hint=group[0].language_hint,
                    line_id=f"paragraph-{index}",
                )
            )
        return merged

    @staticmethod
    def _same_paragraph(anchor: OCRBox, previous: OCRBox, candidate: OCRBox) -> bool:
        anchor_box = anchor.bbox
        previous_box = previous.bbox
        candidate_box = candidate.bbox

        vertical_gap = candidate_box.y - previous_box.bottom
        if vertical_gap < -max(previous_box.height, candidate_box.height) * 0.20:
            return False
        if vertical_gap > max(previous_box.height, candidate_box.height) * 1.20 + 8:
            return False

        left_delta = abs(anchor_box.x - candidate_box.x)
        allowed_left_delta = max(20, int(min(anchor_box.width, candidate_box.width) * 0.15))
        if left_delta > allowed_left_delta:
            return False

        overlap_x = min(anchor_box.right, candidate_box.right) - max(anchor_box.x, candidate_box.x)
        if overlap_x <= 0 and left_delta > 12:
            return False

        width_ratio = candidate_box.width / max(anchor_box.width, 1)
        if width_ratio < 0.35:
            return False

        return True


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
        started = time.perf_counter()
        resize_started = started
        image, scale_back = self._resize_for_ocr(frame.image)
        resize_ms = (time.perf_counter() - resize_started) * 1000.0
        predict_started = time.perf_counter()
        result, _ = self._engine(image)
        predict_ms = (time.perf_counter() - predict_started) * 1000.0
        boxes: list[OCRBox] = []
        if not result:
            self._log(f"rapid resize={resize_ms:.0f}ms predict={predict_ms:.0f}ms raw=0 merged=0 total={(time.perf_counter() - started) * 1000.0:.0f}ms")
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

        merge_started = time.perf_counter()
        merged = self._merge_line_boxes(boxes)
        merge_ms = (time.perf_counter() - merge_started) * 1000.0
        self._log(
            f"rapid resize={resize_ms:.0f}ms predict={predict_ms:.0f}ms merge={merge_ms:.0f}ms raw={len(boxes)} merged={len(merged)} total={(time.perf_counter() - started) * 1000.0:.0f}ms"
        )
        return merged

