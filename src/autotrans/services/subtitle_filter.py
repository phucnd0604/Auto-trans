from __future__ import annotations

from dataclasses import dataclass

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, Rect
from autotrans.utils.text import is_probably_garbage_text, normalize_text, tokenize_words


@dataclass(slots=True)
class SubtitleCandidate:
    box: OCRBox
    score: float
    region: str
    alignment: str = ""


class AdaptiveSubtitleFilter:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._alignment_scores: dict[str, float] = {"center": 0.0, "left": 0.0, "right": 0.0}

    def _normalized_length(self, text: str) -> int:
        return len(normalize_text(text))

    @staticmethod
    def _looks_like_name_tag(text: str) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        tokens = tokenize_words(normalized)
        if not (1 <= len(tokens) <= 3):
            return False
        if len(normalized) > 18:
            return False
        alpha_count = sum(char.isalpha() for char in normalized)
        digit_count = sum(char.isdigit() for char in normalized)
        if alpha_count < max(len(normalized) - 3, 2):
            return False
        if digit_count > 0:
            return False
        letters = [char for char in normalized if char.isalpha()]
        if letters:
            uppercase_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
            if uppercase_ratio >= 0.95 and len(normalized) > 6:
                return False
        return True

    @staticmethod
    def _looks_like_uppercase_label(text: str) -> bool:
        normalized = normalize_text(text)
        letters = [char for char in normalized if char.isalpha()]
        if not letters:
            return False
        uppercase = sum(1 for char in letters if char.isupper())
        return uppercase / max(len(letters), 1) >= 0.85

    def explain_rejection(self, frame: Frame, box: OCRBox) -> str | None:
        text = normalize_text(box.source_text)
        text_len = len(text)
        if text_len <= 1:
            return "text_too_short"
        if is_probably_garbage_text(text):
            return "garbage_text"

        tokens = tokenize_words(text)
        if not tokens:
            return "garbage_text"

        region_top = int(frame.window_rect.height * self._config.subtitle_region_top_ratio)
        if box.bbox.y < region_top:
            return "above_subtitle_region"

        min_chars = max(3, min(self._config.subtitle_min_chars, 6))
        if text_len < min_chars and not self._looks_like_name_tag(text):
            return "below_min_chars"

        width_ratio = box.bbox.width / max(frame.window_rect.width, 1)
        min_width_ratio = min(self._config.subtitle_min_width_ratio, 0.05)
        if width_ratio < min_width_ratio and text_len < self._config.subtitle_min_chars + 4:
            return "below_min_width_ratio"

        digits = sum(char.isdigit() for char in text)
        alnum = sum(char.isalnum() for char in text)
        digit_ratio = digits / max(alnum, 1)
        if digit_ratio >= 0.75 and text_len <= 18:
            return "numeric_noise"

        if self._looks_like_uppercase_label(text) and len(tokens) <= 3 and text_len <= 28 and not self._looks_like_name_tag(text):
            return "uppercase_label"
        return None

    def _is_subtitle_candidate(self, frame: Frame, box: OCRBox) -> bool:
        return self.explain_rejection(frame, box) is None

    def _group_can_accept(self, anchor: OCRBox, previous: OCRBox, candidate: OCRBox) -> bool:
        vertical_gap = candidate.bbox.y - previous.bbox.bottom
        if vertical_gap < -max(previous.bbox.height, candidate.bbox.height) * 0.30:
            return False
        if vertical_gap > max(previous.bbox.height, candidate.bbox.height) * 1.45 + 14:
            return False

        overlap_x = min(previous.bbox.right, candidate.bbox.right) - max(previous.bbox.x, candidate.bbox.x)
        left_delta = abs(anchor.bbox.x - candidate.bbox.x)
        center_delta = abs(
            (anchor.bbox.x + (anchor.bbox.width / 2))
            - (candidate.bbox.x + (candidate.bbox.width / 2))
        )
        width_basis = max(min(anchor.bbox.width, candidate.bbox.width), 1)
        same_column = left_delta <= max(36, int(width_basis * 0.25))
        near_center_column = center_delta <= max(64, int(width_basis * 0.40))
        enough_overlap = overlap_x > -max(18, int(width_basis * 0.08))
        return same_column or near_center_column or enough_overlap

    def _merge_candidates(self, boxes: list[OCRBox]) -> list[tuple[OCRBox, list[OCRBox]]]:
        if not boxes:
            return []

        ordered = sorted(boxes, key=lambda item: (item.bbox.y, item.bbox.x))
        groups: list[list[OCRBox]] = []
        for box in ordered:
            placed = False
            for group in groups:
                anchor = group[0]
                previous = group[-1]
                if self._group_can_accept(anchor, previous, box):
                    group.append(box)
                    placed = True
                    break
            if not placed:
                groups.append([box])

        merged: list[tuple[OCRBox, list[OCRBox]]] = []
        for index, group in enumerate(groups):
            ordered_group = sorted(group, key=lambda item: (item.bbox.y, item.bbox.x))
            text = " ".join(normalize_text(item.source_text) for item in ordered_group if normalize_text(item.source_text))
            x = min(item.bbox.x for item in ordered_group)
            y = min(item.bbox.y for item in ordered_group)
            right = max(item.bbox.right for item in ordered_group)
            bottom = max(item.bbox.bottom for item in ordered_group)
            merged_box = OCRBox(
                id="",
                source_text=normalize_text(text),
                confidence=sum(item.confidence for item in ordered_group) / len(ordered_group),
                bbox=Rect(x=x, y=y, width=right - x, height=bottom - y),
                language_hint=ordered_group[0].language_hint,
                line_id=f"subtitle-{index}",
            )
            merged.append((merged_box, ordered_group))
        return merged

    def _infer_alignment(self, frame: Frame, box: OCRBox) -> str:
        width = max(frame.window_rect.width, 1)
        center_x = width / 2
        box_center_x = box.bbox.x + (box.bbox.width / 2)
        if box.bbox.x < center_x < box.bbox.right:
            return "center"
        if box_center_x <= width * 0.42:
            return "left"
        if box_center_x >= width * 0.58:
            return "right"
        return "center"

    def _alignment_signal(self, frame: Frame, box: OCRBox) -> tuple[str, float]:
        width = max(frame.window_rect.width, 1)
        center_x = width / 2
        box_center_x = box.bbox.x + (box.bbox.width / 2)
        center_offset = abs(box_center_x - center_x)
        center_signal = 1.0 - min(center_offset / max(self._config.subtitle_center_tolerance_px, 1), 1.5) / 1.5
        left_signal = 1.0 - min(box.bbox.x / max(width * 0.35, 1), 1.0)
        right_gap = width - box.bbox.right
        right_signal = 1.0 - min(right_gap / max(width * 0.35, 1), 1.0)
        signals = {
            "center": max(center_signal, 0.0),
            "left": max(left_signal, 0.0),
            "right": max(right_signal, 0.0),
        }
        alignment = max(signals, key=signals.get)
        return alignment, signals[alignment]

    def _score(self, frame: Frame, box: OCRBox, group: list[OCRBox]) -> SubtitleCandidate:
        width_ratio = box.bbox.width / max(frame.window_rect.width, 1)
        bottom_ratio = box.bbox.bottom / max(frame.window_rect.height, 1)
        text_length = min(self._normalized_length(box.source_text), 64)
        line_count = len(group)
        tokens = tokenize_words(box.source_text)
        alpha_count = sum(char.isalpha() for char in box.source_text)
        uppercase_alpha = sum(char.isupper() for char in box.source_text if char.isalpha())
        uppercase_ratio = uppercase_alpha / max(alpha_count, 1)
        digits = sum(char.isdigit() for char in box.source_text)
        alnum = sum(char.isalnum() for char in box.source_text)
        digit_ratio = digits / max(alnum, 1)

        alignment, alignment_signal = self._alignment_signal(frame, box)
        history_boost = self._alignment_scores.get(alignment, 0.0) * 0.35
        multiline_bonus = min(max(line_count - 1, 0), 2) * 0.35
        width_bonus = min(width_ratio, 0.45) * 2.0
        bottom_bonus = min(bottom_ratio, 1.0) * 1.5
        text_bonus = text_length * 0.045
        confidence_bonus = box.confidence * 1.2

        score = confidence_bonus + text_bonus + width_bonus + bottom_bonus + multiline_bonus
        score += alignment_signal * 0.30 + history_boost

        if len(tokens) == 1 and text_length <= 10:
            score -= 0.6
        if line_count >= 2 and self._looks_like_name_tag(group[0].source_text):
            score += 0.35
        if line_count >= 3:
            score += 0.25
        if digit_ratio >= 0.3:
            score -= 0.9
        if self._looks_like_uppercase_label(box.source_text) and uppercase_ratio >= 0.9 and text_length <= 32:
            score -= 0.75
        if box.bbox.y <= frame.window_rect.height * 0.74:
            score -= 0.2

        return SubtitleCandidate(box=box, score=score, region="subtitle", alignment=alignment)

    def _update_layout_history(self, winners: list[SubtitleCandidate]) -> None:
        for key in list(self._alignment_scores):
            self._alignment_scores[key] *= 0.72
        for candidate in winners:
            self._alignment_scores[candidate.alignment] = self._alignment_scores.get(candidate.alignment, 0.0) + 1.0

    def _collapse_selected(self, selected: list[SubtitleCandidate]) -> list[OCRBox]:
        if not selected:
            return []
        best = selected[0].box
        return [
            OCRBox(
                id=best.id,
                source_text=best.source_text,
                confidence=best.confidence,
                bbox=best.bbox,
                language_hint=best.language_hint,
                line_id=best.line_id or "subtitle-0",
            )
        ]

    def select(self, frame: Frame, boxes: list[OCRBox]) -> list[OCRBox]:
        if not self._config.subtitle_mode:
            return boxes

        subtitle_boxes = [box for box in boxes if self._is_subtitle_candidate(frame, box)]
        if not subtitle_boxes:
            return []

        scored = [
            self._score(frame, merged_box, group)
            for merged_box, group in self._merge_candidates(subtitle_boxes)
            if normalize_text(merged_box.source_text)
        ]
        scored.sort(key=lambda item: -item.score)

        selected: list[SubtitleCandidate] = []
        for candidate in scored:
            if any(candidate.box.bbox.iou(existing.box.bbox) > 0.2 for existing in selected):
                continue
            selected.append(candidate)
            if len(selected) >= self._config.subtitle_max_candidates:
                break

        self._update_layout_history(selected)
        return self._collapse_selected(selected)
