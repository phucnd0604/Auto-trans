from __future__ import annotations

import json
import importlib.util
import sys
import time
import types
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, QualityMode, Rect, TranslationResult
from autotrans.services.ocr import PaddleOCRProvider


capture_stub = types.ModuleType("autotrans.services.capture")


class CaptureService:
    def capture_window(self, hwnd: int):
        raise NotImplementedError


capture_stub.CaptureService = CaptureService
sys.modules.setdefault("autotrans.services.capture", capture_stub)

from autotrans.services.orchestrator import PipelineOrchestrator


ROOT = Path(__file__).resolve().parent
IMAGE_GLOB = "sub*.png"


class _NoopTranslator:
    name = "noop"

    def translate_batch(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
        mode: QualityMode,
    ) -> list[TranslationResult]:
        return []

    def translate_screen_blocks(
        self,
        items: list[OCRBox],
        source_lang: str,
        target_lang: str,
    ) -> list[TranslationResult]:
        return []


class _StaticCaptureService:
    def __init__(self, frames: dict[int, Frame]) -> None:
        self._frames = frames

    def capture_window(self, hwnd: int) -> Frame | None:
        return self._frames.get(hwnd)

    def list_windows(self) -> list[object]:
        return []


class _BenchmarkPaddleOCRProvider(PaddleOCRProvider):
    def __init__(
        self,
        config: AppConfig,
        *,
        det_limit_side_len: int | None = None,
        recognition_model_name: str | None = None,
    ) -> None:
        self._override_det_limit_side_len = det_limit_side_len
        self._override_recognition_model_name = recognition_model_name
        super().__init__(config)

    def _resolve_recognition_model_name(self) -> str:
        return self._override_recognition_model_name or super()._resolve_recognition_model_name()

    def _build_ocr_kwargs(self) -> dict[str, object]:
        kwargs = super()._build_ocr_kwargs()
        if self._override_det_limit_side_len is not None:
            kwargs["text_det_limit_side_len"] = self._override_det_limit_side_len
        return kwargs


@dataclass(slots=True)
class StepSnapshot:
    file: str
    capture_ms: float
    crop_ms: float
    ocr_ms: float
    dedupe_ms: float
    select_ms: float
    stabilize_ms: float
    track_ms: float
    total_ms: float
    raw_boxes: int
    deduped_boxes: int
    selected_boxes: int
    stable_boxes: int
    tracked_boxes: int
    capture_backend: str
    crop_offset: int
    texts: list[str]


def _load_frame(image_path: Path) -> Frame:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Failed to read image: {image_path}")
    return Frame(
        image=image,
        timestamp=time.time(),
        window_rect=Rect(x=0, y=0, width=image.shape[1], height=image.shape[0]),
        metadata={"capture_backend": "image-file"},
    )


def _make_config(*, crop_subtitle_only: bool, ocr_max_side: int) -> AppConfig:
    config = AppConfig()
    config.ocr_provider = "paddleocr"
    config.capture_backend = "printwindow"
    config.subtitle_mode = True
    config.ocr_crop_subtitle_only = crop_subtitle_only
    config.ocr_max_side = ocr_max_side
    config.translation_stable_scans = 1
    config.subtitle_hold_frames = 1
    config.debounce_frames = 1
    config.translation_log_enabled = False
    return config


def _run_subtitle_runtime_pass(
    orchestrator: PipelineOrchestrator,
    frame: Frame,
    image_name: str,
) -> StepSnapshot:
    started = time.perf_counter()

    capture_started = time.perf_counter()
    runtime_frame = Frame(
        image=frame.image.copy(),
        timestamp=frame.timestamp,
        window_rect=frame.window_rect,
        scale=frame.scale,
        metadata=dict(frame.metadata),
    )
    capture_ms = (time.perf_counter() - capture_started) * 1000.0

    orchestrator._last_window_height = max(runtime_frame.window_rect.height, 1)
    orchestrator._last_window_width = max(runtime_frame.window_rect.width, 1)

    crop_started = time.perf_counter()
    ocr_frame, y_offset = orchestrator._crop_ocr_frame(runtime_frame)
    crop_ms = (time.perf_counter() - crop_started) * 1000.0

    ocr_started = time.perf_counter()
    ocr_boxes = orchestrator.ocr_provider.recognize(ocr_frame)
    ocr_boxes = orchestrator._offset_boxes(ocr_boxes, y_offset)
    ocr_ms = (time.perf_counter() - ocr_started) * 1000.0

    dedupe_started = time.perf_counter()
    deduped_boxes = orchestrator._dedupe_boxes(ocr_boxes)
    dedupe_ms = (time.perf_counter() - dedupe_started) * 1000.0

    select_started = time.perf_counter()
    selected_boxes = orchestrator._select_boxes(runtime_frame, deduped_boxes)
    select_ms = (time.perf_counter() - select_started) * 1000.0

    stabilize_started = time.perf_counter()
    stable_boxes = orchestrator._stabilize_boxes(selected_boxes)
    stabilize_ms = (time.perf_counter() - stabilize_started) * 1000.0

    track_started = time.perf_counter()
    tracked_boxes = orchestrator._track_boxes(stable_boxes)
    track_ms = (time.perf_counter() - track_started) * 1000.0

    total_ms = (time.perf_counter() - started) * 1000.0
    return StepSnapshot(
        file=image_name,
        capture_ms=capture_ms,
        crop_ms=crop_ms,
        ocr_ms=ocr_ms,
        dedupe_ms=dedupe_ms,
        select_ms=select_ms,
        stabilize_ms=stabilize_ms,
        track_ms=track_ms,
        total_ms=total_ms,
        raw_boxes=len(ocr_boxes),
        deduped_boxes=len(deduped_boxes),
        selected_boxes=len(selected_boxes),
        stable_boxes=len(stable_boxes),
        tracked_boxes=len(tracked_boxes),
        capture_backend=str(runtime_frame.metadata.get("capture_backend", "unknown")),
        crop_offset=y_offset,
        texts=[box.source_text for box in tracked_boxes],
    )


def _run_scenario(
    name: str,
    *,
    crop_subtitle_only: bool,
    ocr_max_side: int,
    det_limit_side_len: int | None = None,
    recognition_model_name: str | None = None,
) -> dict[str, object]:
    config = _make_config(crop_subtitle_only=crop_subtitle_only, ocr_max_side=ocr_max_side)
    frames = {index: _load_frame(path) for index, path in enumerate(sorted(ROOT.glob(IMAGE_GLOB)), start=1)}
    capture_service = _StaticCaptureService(frames)
    realtime_provider = _BenchmarkPaddleOCRProvider(
        config,
        det_limit_side_len=det_limit_side_len,
        recognition_model_name=recognition_model_name,
    )
    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=capture_service,
        ocr_provider=realtime_provider,
        local_translator=_NoopTranslator(),
        cloud_translator=None,
    )

    snapshots: list[StepSnapshot] = []
    for hwnd, frame in frames.items():
        snapshots.append(_run_subtitle_runtime_pass(orchestrator, frame, f"{hwnd}:{ROOT / f'sub{hwnd}.png'}"))

    average_total = sum(item.total_ms for item in snapshots) / max(len(snapshots), 1)
    average_ocr = sum(item.ocr_ms for item in snapshots) / max(len(snapshots), 1)
    average_selected = sum(item.selected_boxes for item in snapshots) / max(len(snapshots), 1)
    return {
        "scenario": name,
        "provider": "paddleocr",
        "config": {
            "ocr_crop_subtitle_only": crop_subtitle_only,
            "ocr_max_side": ocr_max_side,
            "subtitle_mode": True,
            "translation_stable_scans": config.translation_stable_scans,
            "debounce_frames": config.debounce_frames,
            "det_limit_side_len": det_limit_side_len,
            "recognition_model_name": recognition_model_name or realtime_provider._resolve_recognition_model_name(),
        },
        "summary": {
            "images": len(snapshots),
            "avg_total_ms": round(average_total, 2),
            "avg_ocr_ms": round(average_ocr, 2),
            "avg_selected_boxes": round(average_selected, 2),
        },
        "snapshots": [asdict(item) for item in snapshots],
    }


def main() -> None:
    scenarios = [
        ("runtime-default", {"crop_subtitle_only": True, "ocr_max_side": 960}),
        ("runtime-no-crop", {"crop_subtitle_only": False, "ocr_max_side": 960}),
        ("runtime-det-640", {"crop_subtitle_only": True, "ocr_max_side": 960, "det_limit_side_len": 640}),
        (
            "runtime-latin-rec",
            {
                "crop_subtitle_only": True,
                "ocr_max_side": 960,
                "recognition_model_name": "latin_PP-OCRv5_rec_mobile",
            },
        ),
    ]

    if importlib.util.find_spec("paddleocr") is None:
        print("- paddleocr: skipped (dependency not installed)")
        return

    results = []
    for scenario_name, kwargs in scenarios:
        started = time.perf_counter()
        result = _run_scenario(scenario_name, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        summary = result["summary"]
        print(
            f"- paddleocr/{scenario_name}: avg_ocr={summary['avg_ocr_ms']}ms "
            f"avg_total={summary['avg_total_ms']}ms selected={summary['avg_selected_boxes']} "
            f"elapsed={elapsed_ms:.0f}ms"
        )
        results.append(result)

    output_path = ROOT / "subtitle_runtime_benchmark.json"
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote benchmark report to {output_path}")


if __name__ == "__main__":
    main()
