from __future__ import annotations

import json
import importlib.util
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import onnxruntime as ort

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, QualityMode, Rect, TranslationResult
from autotrans.services.ocr import PaddleOCRProvider, RapidOCRProvider
from autotrans.services.orchestrator import PipelineOrchestrator


ROOT = Path(__file__).resolve().parent
IMAGE_GLOB = "sub*.png"
MODEL_ROOT = ROOT / "models"


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


class _BenchmarkRapidOCRProvider(RapidOCRProvider):
    def __init__(
        self,
        config: AppConfig,
        engine_kwargs: dict[str, object] | None = None,
        *,
        use_directml: bool = False,
    ) -> None:
        super().__init__(config)
        if engine_kwargs or use_directml:
            from rapidocr_onnxruntime import RapidOCR

            with _rapidocr_directml_patch(enabled=use_directml):
                self._engine = RapidOCR(**(engine_kwargs or {}))


class _BenchmarkPaddleOCRProvider(PaddleOCRProvider):
    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)


@contextmanager
def _rapidocr_directml_patch(enabled: bool):
    if not enabled:
        yield
        return

    import onnxruntime as ort
    import rapidocr_onnxruntime.ch_ppocr_v2_cls.text_cls as text_cls_module
    import rapidocr_onnxruntime.ch_ppocr_v3_det.text_detect as text_detect_module
    import rapidocr_onnxruntime.ch_ppocr_v3_rec.text_recognize as text_recognize_module
    import rapidocr_onnxruntime.utils as rapid_utils
    from onnxruntime import GraphOptimizationLevel, SessionOptions
    from pathlib import Path as _Path

    original_utils = rapid_utils.OrtInferSession
    original_cls = text_cls_module.OrtInferSession
    original_det = text_detect_module.OrtInferSession
    original_rec = text_recognize_module.OrtInferSession

    class DirectMLOrtInferSession:
        def __init__(self, config):
            sess_opt = SessionOptions()
            sess_opt.log_severity_level = 4
            sess_opt.enable_cpu_mem_arena = False
            sess_opt.graph_optimization_level = GraphOptimizationLevel.ORT_ENABLE_ALL
            model_path = _Path(config["model_path"])
            if not model_path.exists():
                raise FileNotFoundError(f"{model_path} does not exists.")
            self.session = ort.InferenceSession(
                str(model_path),
                sess_options=sess_opt,
                providers=["DmlExecutionProvider", "CPUExecutionProvider"],
            )

        def __call__(self, input_content):
            input_dict = dict(zip(self.get_input_names(), [input_content]))
            return self.session.run(self.get_output_names(), input_dict)

        def get_input_names(self):
            return [v.name for v in self.session.get_inputs()]

        def get_output_names(self):
            return [v.name for v in self.session.get_outputs()]

        def get_character_list(self, key: str = "character"):
            self.meta_dict = self.session.get_modelmeta().custom_metadata_map
            return self.meta_dict[key].splitlines()

        def have_key(self, key: str = "character") -> bool:
            self.meta_dict = self.session.get_modelmeta().custom_metadata_map
            return key in self.meta_dict.keys()

    rapid_utils.OrtInferSession = DirectMLOrtInferSession
    text_cls_module.OrtInferSession = DirectMLOrtInferSession
    text_detect_module.OrtInferSession = DirectMLOrtInferSession
    text_recognize_module.OrtInferSession = DirectMLOrtInferSession
    try:
        yield
    finally:
        rapid_utils.OrtInferSession = original_utils
        text_cls_module.OrtInferSession = original_cls
        text_detect_module.OrtInferSession = original_det
        text_recognize_module.OrtInferSession = original_rec


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
    config.ocr_provider = "rapidocr"
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
    provider_name: str,
    name: str,
    *,
    crop_subtitle_only: bool,
    ocr_max_side: int,
    engine_kwargs: dict[str, object] | None = None,
    use_directml: bool = False,
) -> dict[str, object]:
    config = _make_config(crop_subtitle_only=crop_subtitle_only, ocr_max_side=ocr_max_side)
    config.ocr_provider = provider_name
    frames = {index: _load_frame(path) for index, path in enumerate(sorted(ROOT.glob(IMAGE_GLOB)), start=1)}
    capture_service = _StaticCaptureService(frames)
    if provider_name == "paddleocr":
        realtime_provider = _BenchmarkPaddleOCRProvider(config)
    else:
        realtime_provider = _BenchmarkRapidOCRProvider(config, engine_kwargs, use_directml=use_directml)
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
        "provider": provider_name,
        "config": {
            "ocr_crop_subtitle_only": crop_subtitle_only,
            "ocr_max_side": ocr_max_side,
            "subtitle_mode": True,
            "translation_stable_scans": config.translation_stable_scans,
            "debounce_frames": config.debounce_frames,
            "engine_kwargs": engine_kwargs or {},
            "use_directml": use_directml,
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
        ("runtime-default", {"crop_subtitle_only": True, "ocr_max_side": 960, "engine_kwargs": {}}),
        ("runtime-no-crop", {"crop_subtitle_only": False, "ocr_max_side": 960, "engine_kwargs": {}}),
        ("runtime-no-cls", {"crop_subtitle_only": True, "ocr_max_side": 960, "engine_kwargs": {"use_angle_cls": False}}),
        (
            "runtime-no-cls-no-crop",
            {"crop_subtitle_only": False, "ocr_max_side": 960, "engine_kwargs": {"use_angle_cls": False}},
        ),
        (
            "runtime-det-640",
            {
                "crop_subtitle_only": True,
                "ocr_max_side": 960,
                "engine_kwargs": {"det_model_path": None, "det_limit_side_len": 640},
            },
        ),
        (
            "runtime-det-512",
            {
                "crop_subtitle_only": True,
                "ocr_max_side": 960,
                "engine_kwargs": {"det_model_path": None, "det_limit_side_len": 512},
            },
        ),
        (
            "runtime-no-cls-det-640",
            {
                "crop_subtitle_only": True,
                "ocr_max_side": 960,
                "engine_kwargs": {"use_angle_cls": False, "det_model_path": None, "det_limit_side_len": 640},
            },
        ),
        ("runtime-no-det", {"crop_subtitle_only": True, "ocr_max_side": 960, "engine_kwargs": {"use_text_det": False}}),
        (
            "runtime-en-v4-rec",
            {
                "crop_subtitle_only": True,
                "ocr_max_side": 960,
                "engine_kwargs": {"rec_model_path": str((MODEL_ROOT / "en_PP-OCRv4_rec_infer.onnx").resolve())},
            },
        ),
        (
            "runtime-en-v5-rec",
            {
                "crop_subtitle_only": True,
                "ocr_max_side": 960,
                "engine_kwargs": {"rec_model_path": str((MODEL_ROOT / "en_PP-OCRv5_rec_mobile_infer.onnx").resolve())},
            },
        ),
        (
            "runtime-latin-v5-rec",
            {
                "crop_subtitle_only": True,
                "ocr_max_side": 960,
                "engine_kwargs": {"rec_model_path": str((MODEL_ROOT / "latin_PP-OCRv5_rec_mobile_infer.onnx").resolve())},
            },
        ),
        (
            "runtime-v5-det-en-v5-rec",
            {
                "crop_subtitle_only": True,
                "ocr_max_side": 960,
                "engine_kwargs": {
                    "det_model_path": str((MODEL_ROOT / "ch_PP-OCRv5_mobile_det.onnx").resolve()),
                    "rec_model_path": str((MODEL_ROOT / "en_PP-OCRv5_rec_mobile_infer.onnx").resolve()),
                },
            },
        ),
        (
            "runtime-v5-det-latin-v5-rec",
            {
                "crop_subtitle_only": True,
                "ocr_max_side": 960,
                "engine_kwargs": {
                    "det_model_path": str((MODEL_ROOT / "ch_PP-OCRv5_mobile_det.onnx").resolve()),
                    "rec_model_path": str((MODEL_ROOT / "latin_PP-OCRv5_rec_mobile_infer.onnx").resolve()),
                },
            },
        ),
        (
            "runtime-directml-latin-v5-rec",
            {
                "crop_subtitle_only": True,
                "ocr_max_side": 960,
                "engine_kwargs": {"rec_model_path": str((MODEL_ROOT / "latin_PP-OCRv5_rec_mobile_infer.onnx").resolve())},
                "use_directml": True,
            },
        ),
    ]

    available_providers = set(ort.get_available_providers())
    filtered_scenarios: list[tuple[str, str, dict[str, object]]] = []
    for provider_name in ("rapidocr", "paddleocr"):
        if provider_name == "paddleocr" and importlib.util.find_spec("paddleocr") is None:
            print("- paddleocr: skipped (dependency not installed)")
            continue
        for scenario_name, kwargs in scenarios:
            if provider_name == "paddleocr" and kwargs.get("use_directml"):
                continue
            engine_kwargs = kwargs.get("engine_kwargs", {})
            required_paths = [
                Path(str(value))
                for key, value in engine_kwargs.items()
                if key.endswith("_model_path") and value
            ]
            if any(not path.exists() for path in required_paths):
                print(f"- {provider_name}/{scenario_name}: skipped (missing model file)")
                continue
            if kwargs.get("use_directml") and "DmlExecutionProvider" not in available_providers:
                print(f"- {provider_name}/{scenario_name}: skipped (DmlExecutionProvider unavailable)")
                continue
            filtered_scenarios.append((provider_name, scenario_name, kwargs))

    report = {"root": str(ROOT), "results": []}
    print("Subtitle OCR runtime benchmark")
    print(f"Image root: {ROOT}")
    for provider_name, scenario_name, kwargs in filtered_scenarios:
        started = time.perf_counter()
        result = _run_scenario(provider_name, scenario_name, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        report["results"].append(result)
        summary = result["summary"]
        print(
            f"- {provider_name}/{scenario_name}: avg_total={summary['avg_total_ms']}ms "
            f"avg_ocr={summary['avg_ocr_ms']}ms avg_selected={summary['avg_selected_boxes']} "
            f"scenario_wall={elapsed_ms:.0f}ms"
        )
        for snapshot in result["snapshots"]:
            print(
                f"  {Path(snapshot['file']).name}: total={snapshot['total_ms']:.1f}ms "
                f"ocr={snapshot['ocr_ms']:.1f}ms crop={snapshot['crop_ms']:.1f}ms "
                f"raw={snapshot['raw_boxes']} deduped={snapshot['deduped_boxes']} "
                f"selected={snapshot['selected_boxes']} tracked={snapshot['tracked_boxes']}"
            )
            for text in snapshot["texts"]:
                print(f"    - {text}")

    report_path = ROOT / "subtitle_runtime_benchmark.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved report: {report_path}")


if __name__ == "__main__":
    main()
