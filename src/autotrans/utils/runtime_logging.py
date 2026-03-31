from __future__ import annotations

import io
import sys
from pathlib import Path

from autotrans.config import AppConfig


class _LineCappedTeeStream(io.TextIOBase):
    def __init__(self, base_stream: io.TextIOBase, log_path: Path, max_lines: int, trim_to_lines: int) -> None:
        self._base_stream = base_stream
        self._log_path = log_path
        self._max_lines = max(max_lines, 100)
        self._trim_to_lines = max(1, min(trim_to_lines, self._max_lines))
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_path.open("w", encoding="utf-8", errors="replace")
        self._line_count = 0

    def write(self, text: str) -> int:
        if not text:
            return 0
        self._ensure_log_file()
        written = self._write_base(text)
        self._write_log(text)
        self._line_count += text.count("\n")
        if self._line_count >= self._max_lines:
            self._trim()
        return written

    def flush(self) -> None:
        self._flush_base()
        self._flush_log()

    def isatty(self) -> bool:
        return bool(getattr(self._base_stream, "isatty", lambda: False)())

    def fileno(self) -> int:
        return self._base_stream.fileno()

    @property
    def encoding(self) -> str:
        return getattr(self._base_stream, "encoding", "utf-8")

    def close(self) -> None:
        self._flush_base()
        self._flush_log()
        if not self.closed:
            super().close()

    def writable(self) -> bool:
        return True

    def _ensure_log_file(self) -> None:
        if getattr(self, "_log_file", None) is None or self._log_file.closed:
            self._log_file = self._log_path.open("a", encoding="utf-8", errors="replace")

    def _write_base(self, text: str) -> int:
        try:
            return self._base_stream.write(text)
        except (ValueError, OSError):
            return len(text)

    def _write_log(self, text: str) -> None:
        try:
            self._log_file.write(text)
        except (ValueError, OSError):
            pass

    def _flush_base(self) -> None:
        try:
            self._base_stream.flush()
        except (ValueError, OSError):
            pass

    def _flush_log(self) -> None:
        try:
            self._log_file.flush()
        except (ValueError, OSError):
            pass

    def _trim(self) -> None:
        self._flush_log()
        try:
            self._log_file.close()
        except (ValueError, OSError):
            pass
        try:
            with self._log_path.open("r", encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
            kept = lines[-self._trim_to_lines :]
            with self._log_path.open("w", encoding="utf-8", errors="replace") as handle:
                handle.writelines(kept)
            self._line_count = len(kept)
        except OSError:
            self._line_count = 0
        self._log_file = self._log_path.open("a", encoding="utf-8", errors="replace")


def setup_runtime_logging(config: AppConfig) -> Path:
    log_path = config.log_dir / "autotrans.log"
    if not isinstance(sys.stdout, _LineCappedTeeStream):
        sys.stdout = _LineCappedTeeStream(sys.stdout, log_path, config.log_max_lines, config.log_trim_to_lines)
    if not isinstance(sys.stderr, _LineCappedTeeStream):
        sys.stderr = _LineCappedTeeStream(sys.stderr, log_path, config.log_max_lines, config.log_trim_to_lines)
    print("[AutoTrans] Log cleared for new session", flush=True)
    print(f"[AutoTrans] Log file: {log_path}", flush=True)
    return log_path
