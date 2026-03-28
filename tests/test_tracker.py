from autotrans.models import OCRBox, Rect
from autotrans.services.tracker import OCRTracker


def make_box(text: str, x: int) -> OCRBox:
    return OCRBox(
        id="",
        source_text=text,
        confidence=0.9,
        bbox=Rect(x, 10, 100, 20),
        language_hint="en",
        line_id="line-0",
    )


def test_tracker_debounces_until_second_hit() -> None:
    tracker = OCRTracker(debounce_frames=2, max_missed_frames=2)
    assert tracker.update([make_box("Quest accepted", 10)]) == []
    stable = tracker.update([make_box("Quest accepted", 12)])
    assert len(stable) == 1
    assert stable[0].id.startswith("box-")


def test_tracker_keeps_box_alive_across_short_miss() -> None:
    tracker = OCRTracker(debounce_frames=1, max_missed_frames=2)
    first = tracker.update([make_box("START", 10)])
    second = tracker.update([])
    third = tracker.update([])
    fourth = tracker.update([])

    assert len(first) == 1
    assert len(second) == 1
    assert len(third) == 1
    assert fourth == []
