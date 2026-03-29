from __future__ import annotations

import io
import sys
from pathlib import Path

from autotrans.config import AppConfig


class _RotatingTeeStream(io.TextIOBase):
    def __init__(self, base_stream: io.TextIOBase, log_path: Path, max_bytes: int) -> None:
        self._base_stream = base_stream
        self._log_path = log_path
        self._max_bytes = max(max_bytes, 1024)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_path.open("a", encoding="utf-8", errors="replace")

    def write(self, text: str) -> int:
        if not text:
            return 0
        if self._log_file.tell() + len(text.encode("utf-8", errors="replace")) > self._max_bytes:
            self._rotate()
        written = self._base_stream.write(text)
        self._log_file.write(text)
        return written

    def flush(self) -> None:
        self._base_stream.flush()
        self._log_file.flush()

    def isatty(self) -> bool:
        return bool(getattr(self._base_stream, "isatty", lambda: False)())

    def fileno(self) -> int:
        return self._base_stream.fileno()

    @property
    def encoding(self) -> str:
        return getattr(self._base_stream, "encoding", "utf-8")

    def _rotate(self) -> None:
        self._log_file.flush()
        self._log_file.close()
        rotated = self._log_path.with_suffix(self._log_path.suffix + ".1")
        if rotated.exists():
            rotated.unlink()
        if self._log_path.exists():
            self._log_path.replace(rotated)
        self._log_file = self._log_path.open("w", encoding="utf-8", errors="replace")


def setup_runtime_logging(config: AppConfig) -> Path:
    log_path = config.log_dir / "autotrans.log"
    if not isinstance(sys.stdout, _RotatingTeeStream):
        sys.stdout = _RotatingTeeStream(sys.stdout, log_path, config.log_max_bytes)
    if not isinstance(sys.stderr, _RotatingTeeStream):
        sys.stderr = _RotatingTeeStream(sys.stderr, log_path, config.log_max_bytes)
    print(f"[AutoTrans] Log file: {log_path}", flush=True)
    return log_path
