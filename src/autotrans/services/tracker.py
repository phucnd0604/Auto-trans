from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz.fuzz import ratio

from autotrans.models import OCRBox
from autotrans.utils.text import normalize_text


@dataclass(slots=True)
class TrackedBox:
    stable_id: str
    candidate: OCRBox
    hits: int
    missed: int = 0


class OCRTracker:
    def __init__(self, debounce_frames: int = 2, max_missed_frames: int = 2) -> None:
        self.debounce_frames = debounce_frames
        self.max_missed_frames = max_missed_frames
        self._tracked: dict[str, TrackedBox] = {}
        self._counter = 0

    def _match(self, box: OCRBox) -> str | None:
        best_key = None
        best_score = 0.0
        current_text = normalize_text(box.source_text)
        for key, tracked in self._tracked.items():
            iou = tracked.candidate.bbox.iou(box.bbox)
            text_score = ratio(
                normalize_text(tracked.candidate.source_text),
                current_text,
            ) / 100.0
            score = (iou * 0.7) + (text_score * 0.3)
            if score > best_score and iou >= 0.25:
                best_key = key
                best_score = score
        return best_key

    def update(self, boxes: list[OCRBox]) -> list[OCRBox]:
        next_tracked: dict[str, TrackedBox] = {}
        stable_boxes: list[OCRBox] = []
        matched_ids: set[str] = set()

        for box in boxes:
            matched_key = self._match(box)
            if matched_key is None:
                stable_id = f"box-{self._counter}"
                self._counter += 1
                tracked = TrackedBox(stable_id=stable_id, candidate=box, hits=1, missed=0)
            else:
                previous = self._tracked[matched_key]
                tracked = TrackedBox(
                    stable_id=previous.stable_id,
                    candidate=box,
                    hits=previous.hits + 1,
                    missed=0,
                )
                matched_ids.add(previous.stable_id)

            next_tracked[tracked.stable_id] = tracked
            if tracked.hits >= self.debounce_frames:
                box.id = tracked.stable_id
                stable_boxes.append(box)

        for stable_id, tracked in self._tracked.items():
            if stable_id in matched_ids or stable_id in next_tracked:
                continue
            missed = tracked.missed + 1
            if missed > self.max_missed_frames:
                continue
            retained = TrackedBox(
                stable_id=tracked.stable_id,
                candidate=tracked.candidate,
                hits=tracked.hits,
                missed=missed,
            )
            next_tracked[stable_id] = retained
            if retained.hits >= self.debounce_frames:
                retained_box = retained.candidate
                retained_box.id = retained.stable_id
                stable_boxes.append(retained_box)

        self._tracked = next_tracked
        return stable_boxes
