from __future__ import annotations

import atexit
import ctypes
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autotrans.config import AppConfig


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class RuntimeDiagnosticsSample:
    timestamp: str
    kind: str
    timings_ms: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    process: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeDiagnosticsEvent:
    timestamp: str
    kind: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    snapshot: dict[str, Any] | None = None


class RuntimeDiagnostics:
    _SAMPLE_INTERVAL_S = 2.0
    _MAX_SAMPLES = 1800
    _MAX_EVENTS = 500

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._enabled = bool(config.diagnostics_enabled)
        self._lock = threading.Lock()
        self._closed = False
        self._last_sample_at = 0.0
        self.session_id = self._build_session_id()
        self.session_dir = (config.log_dir / "sessions").resolve()
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_path = self.session_dir / f"{self.session_id}.json"
        self._session: dict[str, Any] = {
            "session_id": self.session_id,
            "session_start": _utc_timestamp(),
            "session_end": None,
            "config": self._build_config_snapshot(config),
            "samples": [],
            "events": [],
            "last_state": {},
        }
        if self._enabled:
            self._flush_locked()
        atexit.register(self.close)

    @staticmethod
    def _build_session_id() -> str:
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{now}-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _build_config_snapshot(config: AppConfig) -> dict[str, Any]:
        return {
            "capture_backend": config.capture_backend,
            "capture_fps": config.capture_fps,
            "overlay_fps": config.overlay_fps,
            "subtitle_mode": config.subtitle_mode,
            "ocr_crop_subtitle_only": config.ocr_crop_subtitle_only,
            "ocr_provider": config.ocr_provider,
            "translation_mode": config.mode,
            "deep_translation_provider": config.deep_translation_provider,
            "deep_translation_model": config.deep_translation_model,
            "runtime_verbose_log": config.runtime_verbose_log,
            "diagnostics_enabled": config.diagnostics_enabled,
            "diagnostics_trigger_threshold_ms": config.diagnostics_trigger_threshold_ms,
            "runtime_root_dir": str(config.runtime_root_dir),
            "cache_root_dir": str(config.cache_root_dir),
            "local_model_dir": str(config.local_model_dir),
            "paddle_cache_dir": str(config.paddle_cache_dir),
            "hf_home": str(config.hf_home),
            "log_dir": str(config.log_dir),
        }

    def is_enabled(self) -> bool:
        return self._enabled

    def record_state(self, **state: Any) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._session["last_state"] = self._normalize_json_value(state)

    def record_sample(
        self,
        kind: str,
        *,
        timings_ms: dict[str, float] | None = None,
        counts: dict[str, int] | None = None,
        state: dict[str, Any] | None = None,
        force: bool = False,
    ) -> None:
        if not self._enabled:
            return
        process = self._capture_process_metrics()
        sample = RuntimeDiagnosticsSample(
            timestamp=_utc_timestamp(),
            kind=kind,
            timings_ms={key: float(value) for key, value in (timings_ms or {}).items()},
            counts={key: int(value) for key, value in (counts or {}).items()},
            state=self._normalize_json_value(state or {}),
            process=process,
        )
        now = time.monotonic()
        with self._lock:
            self._session["last_state"] = asdict(sample)
            should_append = force or not self._session["samples"] or (now - self._last_sample_at) >= self._SAMPLE_INTERVAL_S
            if should_append:
                samples: list[dict[str, Any]] = self._session["samples"]
                samples.append(asdict(sample))
                if len(samples) > self._MAX_SAMPLES:
                    del samples[: len(samples) - self._MAX_SAMPLES]
                self._last_sample_at = now
                self._flush_locked()

    def record_event(
        self,
        kind: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        snapshot: dict[str, Any] | None = None,
        flush: bool = True,
    ) -> None:
        if not self._enabled:
            return
        event = RuntimeDiagnosticsEvent(
            timestamp=_utc_timestamp(),
            kind=kind,
            message=message,
            details=self._normalize_json_value(details or {}),
            snapshot=self._normalize_json_value(snapshot) if snapshot is not None else None,
        )
        with self._lock:
            events: list[dict[str, Any]] = self._session["events"]
            events.append(asdict(event))
            if len(events) > self._MAX_EVENTS:
                del events[: len(events) - self._MAX_EVENTS]
            if flush:
                self._flush_locked()

    def close(self) -> None:
        if not self._enabled:
            return
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._session["session_end"] = _utc_timestamp()
            self._flush_locked()

    def _flush_locked(self) -> None:
        try:
            self.session_path.write_text(
                json.dumps(self._session, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    @classmethod
    def _normalize_json_value(cls, value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): cls._normalize_json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._normalize_json_value(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _capture_process_metrics() -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "cpu_process_time_s": round(time.process_time(), 4),
            "python_thread_count": threading.active_count(),
        }
        working_set = _working_set_bytes()
        if working_set is not None:
            metrics["working_set_bytes"] = working_set
        return metrics


def _working_set_bytes() -> int | None:
    if not hasattr(ctypes, "windll"):
        return None

    class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    counters = PROCESS_MEMORY_COUNTERS_EX()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
    try:
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            process,
            ctypes.byref(counters),
            counters.cb,
        )
        if ok:
            return int(counters.WorkingSetSize)
    except Exception:
        return None
    return None
