from __future__ import annotations

import numpy as np

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, Rect
from autotrans.services.subtitle import SubtitleDetector


def _make_frame(width: int = 400, height: int = 300) -> Frame:
    return Frame(
        image=np.zeros((height, width, 3), dtype=np.uint8),
        timestamp=0.0,
        window_rect=Rect(x=0, y=0, width=width, height=height),
    )


def _make_box(text: str, x: int, y: int, width: int, height: int, confidence: float = 0.94) -> OCRBox:
    return OCRBox(
        id="",
        source_text=text,
        confidence=confidence,
        bbox=Rect(x=x, y=y, width=width, height=height),
        language_hint="en",
    )


def test_subtitle_detector_prefers_bottom_wide_lines() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = _make_frame()
    boxes = [
        _make_box("OBJECTIVES", 105, 228, 185, 28, confidence=0.98),
        _make_box("Follow Yuna to the old bridge", 58, 242, 286, 30),
    ]

    selected = detector.select(frame, boxes)

    assert len(selected) == 1
    assert selected[0].source_text == "Follow Yuna to the old bridge"


def test_subtitle_detector_accepts_left_aligned_subtitle_block() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = _make_frame(width=1280, height=720)
    boxes = [
        _make_box("Quest Updated", 42, 500, 150, 24, confidence=0.91),
        _make_box("We should leave before sunrise.", 110, 600, 420, 34, confidence=0.96),
        _make_box("The patrol will notice us here.", 112, 639, 432, 35, confidence=0.95),
    ]

    selected = detector.select(frame, boxes)

    assert len(selected) == 1
    assert selected[0].line_id.startswith("subtitle-")
    assert "leave before sunrise" in selected[0].source_text
    assert "patrol will notice us here" in selected[0].source_text


def test_subtitle_detector_no_longer_requires_crossing_screen_center() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = _make_frame(width=1280, height=720)
    subtitle = _make_box("Do not stop until we reach the gate.", 96, 610, 360, 34, confidence=0.97)

    assert detector.explain_rejection(frame, subtitle) is None
    selected = detector.select(frame, [subtitle])
    assert len(selected) == 1


def test_subtitle_detector_rejects_uppercase_menu_label() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = _make_frame()
    box = _make_box("OBJECTIVES", 100, 230, 180, 28, confidence=0.95)

    assert detector.explain_rejection(frame, box) == "uppercase_label"


def test_subtitle_detector_returns_single_box_for_dialogue_cluster() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = _make_frame(width=1280, height=720)
    boxes = [
        _make_box("I thought we were too late.", 390, 590, 500, 34, confidence=0.96),
        _make_box("But the gate is still open.", 404, 630, 468, 35, confidence=0.95),
        _make_box("HP 245", 20, 20, 90, 18, confidence=0.99),
    ]

    selected = detector.select(frame, boxes)

    assert len(selected) == 1
    assert "thought we were too late" in selected[0].source_text
    assert "gate is still open" in selected[0].source_text


def test_subtitle_detector_merges_three_line_dialogue_into_one_box() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = _make_frame(width=1280, height=720)
    boxes = [
        _make_box("If we split up now,", 388, 566, 360, 32, confidence=0.96),
        _make_box("we might still reach the village", 376, 604, 430, 34, confidence=0.95),
        _make_box("before the storm closes the pass.", 381, 643, 446, 35, confidence=0.95),
    ]

    selected = detector.select(frame, boxes)

    assert len(selected) == 1
    assert "split up now" in selected[0].source_text
    assert "reach the village" in selected[0].source_text
    assert "storm closes the pass" in selected[0].source_text


def test_subtitle_detector_keeps_speaker_name_with_dialogue_block() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = _make_frame(width=1280, height=720)
    boxes = [
        _make_box("Yuna", 455, 556, 120, 28, confidence=0.97),
        _make_box("We can still turn back if you want.", 334, 595, 514, 34, confidence=0.96),
        _make_box("No one has to know we came here.", 330, 634, 522, 35, confidence=0.95),
    ]

    selected = detector.select(frame, boxes)

    assert len(selected) == 1
    assert selected[0].source_text.startswith("Yuna\n")
    assert "turn back if you want" in selected[0].source_text
    assert "no one has to know" in selected[0].source_text.lower()


def test_subtitle_detector_preserves_visual_line_breaks() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = _make_frame(width=1280, height=720)
    boxes = [
        _make_box("We should leave before sunrise.", 110, 600, 420, 34, confidence=0.96),
        _make_box("The patrol will notice us here.", 112, 639, 432, 35, confidence=0.95),
    ]

    selected = detector.select(frame, boxes)

    assert len(selected) == 1
    assert selected[0].source_text == "We should leave before sunrise.\nThe patrol will notice us here."
