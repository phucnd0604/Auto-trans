from __future__ import annotations

import io
import sys
from pathlib import Path

from autotrans.config import AppConfig
from autotrans.models import OCRBox, Rect
from autotrans.services.subtitle import SubtitleDetector
from autotrans.utils.runtime_logging import _LineCappedTeeStream, setup_runtime_logging
from autotrans.models import Frame
import numpy as np


def test_line_capped_tee_stream_truncates_previous_log(tmp_path: Path) -> None:
    log_path = tmp_path / "autotrans.log"
    log_path.write_text("old-line\n", encoding="utf-8")

    stream = _LineCappedTeeStream(io.StringIO(), log_path, max_lines=100, trim_to_lines=50)
    stream.write("new-line\n")
    stream.flush()

    content = log_path.read_text(encoding="utf-8")
    assert "old-line" not in content
    assert "new-line" in content


def test_setup_runtime_logging_clears_previous_session(tmp_path: Path, monkeypatch) -> None:
    config = AppConfig()
    config.log_dir = tmp_path
    log_path = tmp_path / "autotrans.log"
    log_path.write_text("old-session\n", encoding="utf-8")

    stdout = sys.stdout
    stderr = sys.stderr
    try:
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        monkeypatch.setattr(sys, "stderr", io.StringIO())
        setup_runtime_logging(config)
        sys.stdout.flush()
        content = log_path.read_text(encoding="utf-8")
    finally:
        sys.stdout = stdout
        sys.stderr = stderr

    assert "old-session" not in content
    assert "Log cleared for new session" in content


def test_subtitle_detector_explains_rejection_reason() -> None:
    config = AppConfig()
    detector = SubtitleDetector(config)
    frame = Frame(
        image=np.zeros((300, 400, 3), dtype=np.uint8),
        timestamp=0.0,
        window_rect=Rect(x=0, y=0, width=400, height=300),
    )
    box = OCRBox(
        id="label",
        source_text="OBJECTIVES",
        confidence=0.9,
        bbox=Rect(x=100, y=230, width=180, height=28),
    )

    assert detector.explain_rejection(frame, box) == "uppercase_label"
