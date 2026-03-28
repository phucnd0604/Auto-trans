from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, Rect
from autotrans.services.subtitle import SubtitleDetector

import numpy as np


def make_box(text: str, x: int, y: int, width: int, height: int) -> OCRBox:
    return OCRBox(
        id="",
        source_text=text,
        confidence=0.95,
        bbox=Rect(x, y, width, height),
        language_hint="en",
        line_id="line-0",
    )


def test_subtitle_detector_prefers_bottom_wide_lines() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = Frame(
        image=np.zeros((1080, 1920, 3), dtype=np.uint8),
        timestamp=1.0,
        window_rect=Rect(0, 0, 1920, 1080),
    )
    boxes = [
        make_box("File Edit Window Help", 100, 20, 320, 24),
        make_box("then drop him with one strike.", 500, 880, 760, 42),
        make_box("This is another bottom line", 520, 926, 700, 36),
        make_box("tiny", 1700, 980, 60, 16),
    ]

    selected = detector.select(frame, boxes)

    assert len(selected) >= 1
    assert "then drop him with one strike." in selected[0].source_text
    assert "This is another bottom line" in selected[0].source_text


def test_subtitle_detector_handles_glued_uppercase_menu_text() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = Frame(
        image=np.zeros((1080, 1920, 3), dtype=np.uint8),
        timestamp=1.0,
        window_rect=Rect(0, 0, 1920, 1080),
    )
    boxes = [
        make_box("RESTARTFROMLASTCHECKPOINT", 765, 591, 388, 24),
        make_box("EXITTOTITLE SCREEN", 833, 841, 254, 30),
        make_box("ESC EXIT PRIVACY SETTINGS", 1475, 1021, 414, 38),
    ]

    selected = detector.select(frame, boxes)

    assert len(selected) >= 1
    assert selected[0].source_text == "RESTARTFROMLASTCHECKPOINT"
    assert any(box.source_text == "EXITTOTITLE SCREEN" for box in selected)


def test_subtitle_detector_ignores_short_bottom_text() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = Frame(
        image=np.zeros((1080, 1920, 3), dtype=np.uint8),
        timestamp=1.0,
        window_rect=Rect(0, 0, 1920, 1080),
    )
    boxes = [
        make_box("QUIT", 900, 920, 120, 28),
        make_box("ESC", 1500, 1020, 100, 32),
    ]

    selected = detector.select(frame, boxes)

    assert selected == []
