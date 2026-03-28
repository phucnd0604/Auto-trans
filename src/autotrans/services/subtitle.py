from __future__ import annotations

from dataclasses import dataclass

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, Rect
from autotrans.utils.text import is_probably_garbage_text, normalize_text


@dataclass(slots=True)
class SubtitleCandidate:
    box: OCRBox
    score: float


class SubtitleDetector:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def _center_offset(self, frame: Frame, box: OCRBox) -> float:
        center_x = box.bbox.x + (box.bbox.width / 2)
        return abs(center_x - (frame.window_rect.width / 2)) / max(frame.window_rect.width / 2, 1)

    def _normalized_length(self, text: str) -> int:
        return len(normalize_text(text))

    def _is_subtitle_like(self, frame: Frame, box: OCRBox) -> bool:
        region_top = int(frame.window_rect.height * self._config.subtitle_region_top_ratio)
        if box.bbox.y < region_top:
            return False
        if box.bbox.width < int(frame.window_rect.width * self._config.subtitle_min_width_ratio):
            return False
        if self._normalized_length(box.source_text) <= 5:
            return False
        if is_probably_garbage_text(box.source_text):
            return False

        width_ratio = box.bbox.width / max(frame.window_rect.width, 1)
        bottom_proximity = box.bbox.bottom / max(frame.window_rect.height, 1)
        if bottom_proximity > 0.9 and self._center_offset(frame, box) > 0.42 and width_ratio < 0.36:
            return False
        return True

    def _merge_candidates(self, frame: Frame, boxes: list[OCRBox]) -> list[OCRBox]:
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
                if gap_y <= max(anchor.bbox.height, box.bbox.height) * 0.8 and overlap_x > min(anchor.bbox.width, box.bbox.width) * 0.15:
                    group.append(box)
                    placed = True
                    break
            if not placed:
                groups.append([box])

        merged: list[OCRBox] = []
        for index, group in enumerate(groups):
            text = " ".join(item.source_text for item in group)
            x = min(item.bbox.x for item in group)
            y = min(item.bbox.y for item in group)
            right = max(item.bbox.right for item in group)
            bottom = max(item.bbox.bottom for item in group)
            merged.append(
                OCRBox(
                    id="",
                    source_text=normalize_text(text),
                    confidence=sum(item.confidence for item in group) / len(group),
                    bbox=Rect(x=x, y=y, width=right - x, height=bottom - y),
                    language_hint=group[0].language_hint,
                    line_id=f"subtitle-{index}",
                )
            )
        return merged

    def _score(self, frame: Frame, box: OCRBox) -> float:
        width_ratio = box.bbox.width / max(frame.window_rect.width, 1)
        bottom_proximity = box.bbox.bottom / max(frame.window_rect.height, 1)
        center_offset = self._center_offset(frame, box)
        text_length = self._normalized_length(box.source_text)
        top_penalty = 0.25 if box.bbox.y < frame.window_rect.height * 0.12 else 0.0
        return (
            width_ratio * 2.0
            + bottom_proximity * 0.9
            + min(text_length, 32) * 0.05
            - center_offset * 0.8
            - top_penalty
        )

    def select(self, frame: Frame, boxes: list[OCRBox]) -> list[OCRBox]:
        if not self._config.subtitle_mode:
            return boxes

        candidates = [box for box in boxes if self._is_subtitle_like(frame, box)]
        merged = self._merge_candidates(frame, candidates)
        scored = [SubtitleCandidate(box=box, score=self._score(frame, box)) for box in merged]
        scored.sort(key=lambda item: item.score, reverse=True)

        if not scored:
            fallback = sorted(
                [
                    box
                    for box in boxes
                    if self._normalized_length(box.source_text) > 5
                    and not is_probably_garbage_text(box.source_text)
                ],
                key=lambda item: self._score(frame, item),
                reverse=True,
            )
            return fallback[: self._config.subtitle_max_candidates]

        selected: list[OCRBox] = []
        for candidate in scored:
            if any(candidate.box.bbox.iou(existing.bbox) > 0.2 for existing in selected):
                continue
            selected.append(candidate.box)
            if len(selected) >= self._config.subtitle_max_candidates:
                break
        return selected
