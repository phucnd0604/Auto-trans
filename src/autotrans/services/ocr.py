from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Protocol

import numpy as np

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, Rect
from autotrans.utils.text import normalize_text


class OCRProvider(Protocol):
    name: str

    def recognize(self, frame: Frame) -> list[OCRBox]:
        ...

    def recognize_paragraphs(self, frame: Frame) -> list[OCRBox]:
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

    def recognize_paragraphs(self, frame: Frame) -> list[OCRBox]:
        return self.recognize(frame)


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
    def _rect_intersection_area(left: Rect, right: Rect) -> int:
        x1 = max(left.x, right.x)
        y1 = max(left.y, right.y)
        x2 = min(left.right, right.right)
        y2 = min(left.bottom, right.bottom)
        return max(0, x2 - x1) * max(0, y2 - y1)

    def _merge_layout_regions(
        self,
        boxes: list[OCRBox],
        layout_regions: list[tuple[Rect, str, float]],
    ) -> list[OCRBox]:
        if not boxes or not layout_regions:
            return boxes

        allowed_labels = {"text", "title"}
        target_regions = [
            (region_rect, region_label, region_score)
            for region_rect, region_label, region_score in layout_regions
            if region_label.strip().lower() in allowed_labels and region_score >= 0.35
        ]
        if not target_regions:
            return boxes

        assigned_groups: list[list[OCRBox]] = [[] for _ in target_regions]
        unassigned: list[OCRBox] = []

        for box in sorted(boxes, key=lambda item: (item.bbox.y, item.bbox.x)):
            best_index = -1
            best_score = 0.0
            for index, (region_rect, _, region_score) in enumerate(target_regions):
                intersection = self._rect_intersection_area(box.bbox, region_rect)
                if intersection <= 0:
                    continue
                overlap_ratio = intersection / max(box.bbox.area(), 1)
                coverage_ratio = intersection / max(region_rect.area(), 1)
                center_x = box.bbox.x + (box.bbox.width / 2)
                center_y = box.bbox.y + (box.bbox.height / 2)
                center_inside = (
                    region_rect.x <= center_x <= region_rect.right
                    and region_rect.y <= center_y <= region_rect.bottom
                )
                if not center_inside and overlap_ratio < 0.55:
                    continue
                score = max(overlap_ratio, coverage_ratio * 4.0) + region_score * 0.1
                if score > best_score:
                    best_score = score
                    best_index = index
            if best_index >= 0:
                assigned_groups[best_index].append(box)
            else:
                unassigned.append(box)

        merged: list[OCRBox] = []
        for group in assigned_groups:
            if not group:
                continue
            paragraph_boxes = self._merge_paragraph_boxes(group)
            merged.extend(paragraph_boxes)

        if unassigned:
            merged.extend(self._merge_paragraph_boxes(unassigned))

        merged.sort(key=lambda item: (item.bbox.y, item.bbox.x))
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

        self._engine = RapidOCR(**self._engine_kwargs())
        self._layout_engine = None
        self._layout_disabled = False

    def _engine_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {}
        rec_model_path = self._resolve_rec_model_path()
        if rec_model_path is not None:
            kwargs["rec_model_path"] = str(rec_model_path)
            self._log(f"rapidocr rec model override={rec_model_path}")
        return kwargs

    def _resolve_rec_model_path(self) -> Path | None:
        if self._config.ocr_rec_model_path is not None and self._config.ocr_rec_model_path.exists():
            return self._config.ocr_rec_model_path

        default_candidate = self._config.ocr_model_dir / "latin_PP-OCRv5_rec_mobile_infer.onnx"
        if default_candidate.exists():
            return default_candidate
        return None

    def _get_layout_engine(self):
        if self._layout_disabled:
            return None
        if self._layout_engine is not None:
            return self._layout_engine
        try:
            from rapid_layout import RapidLayout
        except ImportError:
            self._layout_disabled = True
            self._log("rapid-layout is not installed; deep mode will use line/paragraph OCR only")
            return None
        try:
            self._layout_engine = RapidLayout(
                model_type="yolov8n_layout_general6",
                conf_thresh=0.35,
                iou_thresh=0.45,
            )
        except Exception as exc:
            self._layout_disabled = True
            self._log(f"rapid-layout init failed: {exc}")
            return None
        return self._layout_engine

    def _detect_layout_regions(self, frame: Frame) -> tuple[list[tuple[Rect, str, float]], float]:
        layout_engine = self._get_layout_engine()
        if layout_engine is None:
            return [], 0.0
        started = time.perf_counter()
        try:
            result = layout_engine(frame.image)
        except Exception as exc:
            self._log(f"rapid-layout detect failed: {exc}")
            return [], (time.perf_counter() - started) * 1000.0
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        boxes = result.boxes if result.boxes is not None else []
        class_names = result.class_names if result.class_names is not None else []
        scores = result.scores if result.scores is not None else []
        regions: list[tuple[Rect, str, float]] = []
        for raw_box, class_name, score in zip(boxes, class_names, scores, strict=False):
            if isinstance(raw_box, np.ndarray):
                raw_box = raw_box.tolist()
            if not isinstance(raw_box, list | tuple) or len(raw_box) < 4:
                continue
            x1, y1, x2, y2 = [int(round(float(value))) for value in raw_box[:4]]
            rect = Rect(
                x=min(x1, x2),
                y=min(y1, y2),
                width=max(0, abs(x2 - x1)),
                height=max(0, abs(y2 - y1)),
            )
            if rect.width < 8 or rect.height < 8:
                continue
            regions.append((rect, normalize_text(str(class_name)), float(score)))
        if regions:
            self._log(
                f"deep-layout backend=rapid-layout model=yolov8n_layout_general6 regions={len(regions)} elapsed={elapsed_ms:.0f}ms"
            )
        return regions, elapsed_ms

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

    def _run_engine(self, frame: Frame) -> tuple[list[OCRBox], float, float, float]:
        started = time.perf_counter()
        resize_started = started
        image, scale_back = self._resize_for_ocr(frame.image)
        resize_ms = (time.perf_counter() - resize_started) * 1000.0
        predict_started = time.perf_counter()
        result, _ = self._engine(image)
        predict_ms = (time.perf_counter() - predict_started) * 1000.0
        boxes: list[OCRBox] = []
        if not result:
            return boxes, resize_ms, predict_ms, (time.perf_counter() - started) * 1000.0

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
        total_ms = (time.perf_counter() - started) * 1000.0
        return boxes, resize_ms, predict_ms, total_ms

    def recognize(self, frame: Frame) -> list[OCRBox]:
        boxes, resize_ms, predict_ms, total_ms = self._run_engine(frame)
        if not boxes:
            self._log(f"rapid resize={resize_ms:.0f}ms predict={predict_ms:.0f}ms raw=0 merged=0 total={total_ms:.0f}ms")
            return boxes
        merge_started = time.perf_counter()
        merged = self._merge_line_boxes(boxes)
        merge_ms = (time.perf_counter() - merge_started) * 1000.0
        self._log(
            f"rapid resize={resize_ms:.0f}ms predict={predict_ms:.0f}ms merge={merge_ms:.0f}ms raw={len(boxes)} merged={len(merged)} total={total_ms:.0f}ms"
        )
        return merged

    def recognize_paragraphs(self, frame: Frame) -> list[OCRBox]:
        boxes, resize_ms, predict_ms, total_ms = self._run_engine(frame)
        if not boxes:
            self._log(f"rapid-deep resize={resize_ms:.0f}ms predict={predict_ms:.0f}ms raw=0 lines=0 paragraphs=0 total={total_ms:.0f}ms")
            return boxes
        line_merge_started = time.perf_counter()
        line_boxes = self._merge_line_boxes(boxes)
        line_merge_ms = (time.perf_counter() - line_merge_started) * 1000.0
        layout_regions, layout_ms = self._detect_layout_regions(frame)
        paragraph_merge_started = time.perf_counter()
        paragraph_boxes = self._merge_layout_regions(line_boxes, layout_regions)
        paragraph_merge_ms = (time.perf_counter() - paragraph_merge_started) * 1000.0
        self._log(
            "rapid-deep "
            f"resize={resize_ms:.0f}ms "
            f"predict={predict_ms:.0f}ms "
            f"layout={layout_ms:.0f}ms "
            f"line_merge={line_merge_ms:.0f}ms "
            f"paragraph_merge={paragraph_merge_ms:.0f}ms "
            f"layout_regions={len(layout_regions)} "
            f"raw={len(boxes)} lines={len(line_boxes)} paragraphs={len(paragraph_boxes)} "
            f"total={total_ms:.0f}ms"
        )
        return paragraph_boxes


class PaddleOCRProvider(BaseOCRProvider):
    name = "paddleocr"

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PaddleOCR

        self._language = self._resolve_language()
        self._engine = PaddleOCR(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name=self._resolve_recognition_model_name(),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_det_limit_side_len=192,
            text_recognition_batch_size=8,
            lang=self._language,
        )

    def _resolve_language(self) -> str:
        supported_languages = {
            "en": "en",
            "english": "en",
            "latin": "en",
            "jp": "japan",
            "ja": "japan",
            "japanese": "japan",
            "ch": "ch",
            "zh": "ch",
            "zh-cn": "ch",
            "zh-hans": "ch",
        }
        for language in self._config.ocr_languages:
            normalized = normalize_text(language).lower()
            if normalized in supported_languages:
                resolved = supported_languages[normalized]
                if resolved != normalized:
                    self._log(f"paddleocr language fallback {language!r} -> {resolved!r}")
                return resolved
        self._log("paddleocr language fallback -> 'en'")
        return "en"

    def _resolve_recognition_model_name(self) -> str:
        mapping = {
            "en": "en_PP-OCRv5_mobile_rec",
            "japan": "japan_PP-OCRv5_mobile_rec",
            "ch": "ch_PP-OCRv5_mobile_rec",
        }
        return mapping.get(self._language, "en_PP-OCRv5_mobile_rec")

    @staticmethod
    def _extract_result_fields(item: object) -> tuple[object, object, object] | None:
        if isinstance(item, dict):
            return (
                item.get("rec_polys") or item.get("dt_polys") or [],
                item.get("rec_texts") or [],
                item.get("rec_scores") or [],
            )
        if hasattr(item, "get"):
            return (
                item.get("rec_polys") or item.get("dt_polys") or [],
                item.get("rec_texts") or [],
                item.get("rec_scores") or [],
            )
        return None

    def _extract_lines(self, raw_result: object) -> list[tuple[object, str, float]]:
        if not isinstance(raw_result, list):
            return []

        # PaddleOCR result shape varies by version; normalize the common list/dict forms.
        extracted_fields = self._extract_result_fields(raw_result[0]) if raw_result else None
        if extracted_fields is not None:
            rec_polys, rec_texts, rec_scores = extracted_fields
            output: list[tuple[object, str, float]] = []
            for points, text, confidence in zip(rec_polys, rec_texts, rec_scores, strict=False):
                output.append((points, str(text), float(confidence)))
            return output

        if raw_result and isinstance(raw_result[0], list) and raw_result[0]:
            first_item = raw_result[0][0]
            if isinstance(first_item, list | tuple) and len(first_item) == 2:
                output = []
                for item in raw_result[0]:
                    points, recognition = item
                    if not isinstance(recognition, list | tuple) or len(recognition) < 2:
                        continue
                    output.append((points, str(recognition[0]), float(recognition[1])))
                return output

        output = []
        for item in raw_result:
            if not isinstance(item, list | tuple) or len(item) < 2:
                continue
            points, recognition = item
            if not isinstance(recognition, list | tuple) or len(recognition) < 2:
                continue
            output.append((points, str(recognition[0]), float(recognition[1])))
        return output

    def _run_engine(self, frame: Frame) -> tuple[list[OCRBox], float]:
        started = time.perf_counter()
        image, scale_back = RapidOCRProvider._resize_for_ocr(self, frame.image)
        result = self._engine.predict(image)
        predict_ms = (time.perf_counter() - started) * 1000.0
        boxes: list[OCRBox] = []
        for index, (points, text, confidence) in enumerate(self._extract_lines(result)):
            if isinstance(points, np.ndarray):
                points = points.tolist()
            if not isinstance(points, list | tuple) or not points:
                continue
            try:
                xs = [int(round(float(point[0]) * scale_back)) for point in points]
                ys = [int(round(float(point[1]) * scale_back)) for point in points]
            except (TypeError, ValueError, IndexError):
                continue
            bbox = Rect(
                x=min(xs),
                y=min(ys),
                width=max(xs) - min(xs),
                height=max(ys) - min(ys),
            )
            normalized = normalize_text(text)
            confidence_value = float(confidence)
            if not self._is_meaningful(normalized, bbox, confidence_value):
                continue
            boxes.append(
                OCRBox(
                    id="",
                    source_text=normalized,
                    confidence=confidence_value,
                    bbox=bbox,
                    language_hint=self._language,
                    line_id=f"paddle-{index}",
                )
            )
        return boxes, predict_ms

    def recognize(self, frame: Frame) -> list[OCRBox]:
        boxes, predict_ms = self._run_engine(frame)
        if not boxes:
            self._log(f"paddle predict={predict_ms:.0f}ms raw=0 merged=0")
            return boxes
        merge_started = time.perf_counter()
        merged = self._merge_line_boxes(boxes)
        merge_ms = (time.perf_counter() - merge_started) * 1000.0
        self._log(
            f"paddle predict={predict_ms:.0f}ms merge={merge_ms:.0f}ms raw={len(boxes)} merged={len(merged)}"
        )
        return merged

    def recognize_paragraphs(self, frame: Frame) -> list[OCRBox]:
        # Deep mode never uses PaddleOCR in this app, but keep protocol compatibility.
        return self.recognize(frame)

