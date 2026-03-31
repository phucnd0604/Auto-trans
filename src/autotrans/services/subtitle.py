from __future__ import annotations

from dataclasses import dataclass

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, Rect
from autotrans.utils.text import is_probably_garbage_text, normalize_text


@dataclass(slots=True)
class SubtitleCandidate:
    box: OCRBox
    score: float
    region: str


class SubtitleDetector:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def _normalized_length(self, text: str) -> int:
        return len(normalize_text(text))

    @staticmethod
    def _looks_like_uppercase_label(text: str) -> bool:
        normalized = normalize_text(text)
        letters = [char for char in normalized if char.isalpha()]
        if not letters:
            return False
        uppercase = sum(1 for char in letters if char.isupper())
        return uppercase / max(len(letters), 1) >= 0.85

    def explain_rejection(self, frame: Frame, box: OCRBox) -> str | None:
        text_len = self._normalized_length(box.source_text)
        if text_len <= 1:
            return "text_too_short"
        if is_probably_garbage_text(box.source_text):
            return "garbage_text"
        if self._looks_like_uppercase_label(box.source_text):
            return "uppercase_label"

        region_top = int(frame.window_rect.height * self._config.subtitle_region_top_ratio)
        if box.bbox.y < region_top:
            return "above_subtitle_region"

        if text_len < self._config.subtitle_min_chars:
            return "below_min_chars"

        width_ratio = box.bbox.width / max(frame.window_rect.width, 1)
        if width_ratio < self._config.subtitle_min_width_ratio:
            return "below_min_width_ratio"

        center_x = frame.window_rect.width / 2
        box_center_x = box.bbox.x + (box.bbox.width / 2)
        center_offset = abs(box_center_x - center_x)
        crosses_center = box.bbox.x < center_x < box.bbox.right
        near_center = center_offset <= self._config.subtitle_center_tolerance_px
        if not (crosses_center or near_center):
            return "outside_center_tolerance"
        return None

    def _is_subtitle_candidate(self, frame: Frame, box: OCRBox) -> bool:
        return self.explain_rejection(frame, box) is None

    def _merge_candidates(self, boxes: list[OCRBox]) -> list[OCRBox]:
        if not boxes:
            return []

        boxes = sorted(boxes, key=lambda item: (item.bbox.y, item.bbox.x))
        groups: list[list[OCRBox]] = []
        for box in boxes:
            placed = False
            for group in groups:
                anchor = group[-1]
                gap_y = box.bbox.y - anchor.bbox.bottom
                overlap_x = min(box.bbox.right, anchor.bbox.right) - max(box.bbox.x, anchor.bbox.x)
                same_band = abs(box.bbox.y - anchor.bbox.y) <= max(anchor.bbox.height, box.bbox.height) * 0.9
                if same_band or (gap_y <= max(anchor.bbox.height, box.bbox.height) * 0.8 and overlap_x > min(anchor.bbox.width, box.bbox.width) * 0.15):
                    group.append(box)
                    placed = True
                    break
            if not placed:
                groups.append([box])

        merged: list[OCRBox] = []
        for index, group in enumerate(groups):
            text = ' '.join(item.source_text for item in group)
            x = min(item.bbox.x for item in group)
            y = min(item.bbox.y for item in group)
            right = max(item.bbox.right for item in group)
            bottom = max(item.bbox.bottom for item in group)
            merged.append(
                OCRBox(
                    id='',
                    source_text=normalize_text(text),
                    confidence=sum(item.confidence for item in group) / len(group),
                    bbox=Rect(x=x, y=y, width=right - x, height=bottom - y),
                    language_hint=group[0].language_hint,
                    line_id=f'subtitle-{index}',
                )
            )
        return merged

    def _score(self, frame: Frame, box: OCRBox) -> float:
        width_ratio = box.bbox.width / max(frame.window_rect.width, 1)
        bottom_proximity = box.bbox.bottom / max(frame.window_rect.height, 1)
        center_x = box.bbox.x + (box.bbox.width / 2)
        center_offset = abs(center_x - (frame.window_rect.width / 2)) / max(frame.window_rect.width / 2, 1)
        text_length = min(self._normalized_length(box.source_text), 48)
        base = (box.confidence * 1.2) + (text_length * 0.05)
        return base + (width_ratio * 2.0) + (bottom_proximity * 1.0) - (center_offset * 0.8)

    def select(self, frame: Frame, boxes: list[OCRBox]) -> list[OCRBox]:
        if not self._config.subtitle_mode:
            return boxes

        subtitle_boxes = [box for box in boxes if self._is_subtitle_candidate(frame, box)]
        if not subtitle_boxes:
            return []

        scored: list[SubtitleCandidate] = []
        for merged in self._merge_candidates(subtitle_boxes):
            scored.append(SubtitleCandidate(box=merged, score=self._score(frame, merged), region='subtitle'))

        scored.sort(key=lambda item: -item.score)

        selected: list[OCRBox] = []
        for candidate in scored:
            if any(candidate.box.bbox.iou(existing.bbox) > 0.2 for existing in selected):
                continue
            selected.append(candidate.box)
            if len(selected) >= self._config.subtitle_max_candidates:
                break
        return selected
