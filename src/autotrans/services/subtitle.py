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

    def _center_offset(self, frame: Frame, box: OCRBox) -> float:
        center_x = box.bbox.x + (box.bbox.width / 2)
        return abs(center_x - (frame.window_rect.width / 2)) / max(frame.window_rect.width / 2, 1)

    def _normalized_length(self, text: str) -> int:
        return len(normalize_text(text))

    def _detect_region(self, frame: Frame, box: OCRBox) -> str | None:
        text_len = self._normalized_length(box.source_text)
        if text_len <= 1 or is_probably_garbage_text(box.source_text):
            return None

        width_ratio = box.bbox.width / max(frame.window_rect.width, 1)
        height_ratio = box.bbox.height / max(frame.window_rect.height, 1)
        top_ratio = box.bbox.y / max(frame.window_rect.height, 1)
        center_offset = self._center_offset(frame, box)

        if top_ratio <= 0.35 and box.bbox.x <= frame.window_rect.width * 0.45 and text_len >= 6:
            return 'objective'

        region_top = int(frame.window_rect.height * self._config.subtitle_region_top_ratio)
        if box.bbox.y >= region_top and width_ratio >= self._config.subtitle_min_width_ratio and text_len >= 6:
            return 'subtitle'

        if 0.35 <= top_ratio <= 0.85 and width_ratio >= 0.04 and height_ratio >= 0.015 and text_len >= 2:
            if center_offset <= 0.4 or box.bbox.x >= frame.window_rect.width * 0.55:
                return 'interaction'

        if width_ratio >= 0.12 and text_len >= 6:
            return 'ui'

        return None

    def _merge_candidates(self, region: str, boxes: list[OCRBox]) -> list[OCRBox]:
        if not boxes:
            return []
        if region == 'interaction':
            return boxes

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
                    line_id=f'{region}-{index}',
                )
            )
        return merged

    def _score(self, frame: Frame, box: OCRBox, region: str) -> float:
        width_ratio = box.bbox.width / max(frame.window_rect.width, 1)
        bottom_proximity = box.bbox.bottom / max(frame.window_rect.height, 1)
        top_proximity = 1.0 - (box.bbox.y / max(frame.window_rect.height, 1))
        center_offset = self._center_offset(frame, box)
        text_length = min(self._normalized_length(box.source_text), 48)
        base = (box.confidence * 1.2) + (text_length * 0.05)
        if region == 'subtitle':
            return base + (width_ratio * 2.0) + (bottom_proximity * 1.0) - (center_offset * 0.8)
        if region == 'objective':
            return base + (top_proximity * 1.2) + ((1.0 - center_offset) * 0.3) + (width_ratio * 0.8)
        if region == 'interaction':
            return base + (width_ratio * 0.7) + ((1.0 - center_offset) * 0.6)
        return base + (width_ratio * 0.6) - (center_offset * 0.4)

    def select(self, frame: Frame, boxes: list[OCRBox]) -> list[OCRBox]:
        if not self._config.subtitle_mode:
            return boxes

        region_groups: dict[str, list[OCRBox]] = {'objective': [], 'subtitle': [], 'interaction': [], 'ui': []}
        for box in boxes:
            region = self._detect_region(frame, box)
            if region is not None:
                region_groups[region].append(box)

        scored: list[SubtitleCandidate] = []
        for region, region_boxes in region_groups.items():
            for merged in self._merge_candidates(region, region_boxes):
                scored.append(SubtitleCandidate(box=merged, score=self._score(frame, merged, region), region=region))

        if not scored:
            fallback = sorted(
                [box for box in boxes if self._normalized_length(box.source_text) > 5 and not is_probably_garbage_text(box.source_text)],
                key=lambda item: item.confidence,
                reverse=True,
            )
            return fallback[: self._config.subtitle_max_candidates]

        region_priority = {'subtitle': 0, 'objective': 1, 'interaction': 2, 'ui': 3}
        scored.sort(key=lambda item: (region_priority[item.region], -item.score))

        selected: list[OCRBox] = []
        for candidate in scored:
            if any(candidate.box.bbox.iou(existing.bbox) > 0.2 for existing in selected):
                continue
            selected.append(candidate.box)
            if len(selected) >= self._config.subtitle_max_candidates:
                break
        return selected
