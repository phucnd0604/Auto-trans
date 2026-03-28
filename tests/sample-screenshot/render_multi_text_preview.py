from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from autotrans.config import AppConfig
from autotrans.models import Frame, OCRBox, QualityMode, Rect, TranslationResult
from autotrans.services.ocr import RapidOCRProvider
from autotrans.services.orchestrator import PipelineOrchestrator


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "multi_text.png"
OUTPUT = ROOT / "multi_text_grouped_preview.png"
LOG = ROOT / "multi_text_grouped_preview.txt"


class ImageCapture:
    def __init__(self, image: np.ndarray) -> None:
        self._image = image

    def capture_window(self, hwnd: int):
        h, w = self._image.shape[:2]
        return Frame(
            image=self._image.copy(),
            timestamp=0.0,
            window_rect=Rect(0, 0, w, h),
        )


class NoopTranslator:
    name = "noop"

    def translate_batch(self, items: list[OCRBox], source_lang: str, target_lang: str, mode: QualityMode):
        return [
            TranslationResult(
                source_text=item.source_text,
                translated_text=item.source_text,
                provider=self.name,
                latency_ms=0.0,
            )
            for item in items
        ]


class NoCloudPolicy:
    def select(self, text_items, mode, network_state, cost_budget=True):
        from autotrans.services.policy import ProviderDecision

        return ProviderDecision(provider="local", reason="preview")


def draw_wrapped_text(
    image: np.ndarray,
    text: str,
    rect: Rect,
    color: tuple[int, int, int] = (0, 220, 255),
    background: tuple[int, int, int] = (0, 0, 0),
    border: tuple[int, int, int] = (90, 180, 120),
) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    thickness = 1
    pad_x = 10
    pad_y = 8

    max_width = max(min(rect.width + 40, 520), 180)
    words = text.replace("\n", " \n ").split()
    lines: list[str] = []
    current = ""
    for word in words:
        if word == "\\n":
            if current:
                lines.append(current)
                current = ""
            continue
        candidate = word if not current else f"{current} {word}"
        width = cv2.getTextSize(candidate, font, font_scale, thickness)[0][0]
        if width <= max_width - (pad_x * 2):
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    if not lines:
        return

    line_height = cv2.getTextSize("Ag", font, font_scale, thickness)[0][1] + 10
    text_width = max(cv2.getTextSize(line, font, font_scale, thickness)[0][0] for line in lines)
    panel_w = text_width + (pad_x * 2)
    panel_h = (line_height * len(lines)) + (pad_y * 2)

    panel_x = rect.x + ((rect.width - panel_w) // 2)
    panel_y = rect.y + ((rect.height - panel_h) // 2)
    panel_x = max(0, min(panel_x, image.shape[1] - panel_w - 1))
    panel_y = max(0, min(panel_y, image.shape[0] - panel_h - 1))

    cv2.rectangle(image, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), background, -1)
    cv2.rectangle(image, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), border, 1)

    y = panel_y + pad_y + line_height - 4
    for line in lines:
        line_w = cv2.getTextSize(line, font, font_scale, thickness)[0][0]
        x = panel_x + ((panel_w - line_w) // 2)
        cv2.putText(image, line, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)
        y += line_height


def main() -> None:
    image = cv2.imread(str(INPUT))
    if image is None:
        raise RuntimeError(f"Failed to read {INPUT}")

    config = AppConfig()
    config.ocr_provider = "rapidocr"
    config.overlay_source_text = True
    config.subtitle_mode = False
    config.ocr_crop_subtitle_only = False
    config.ocr_max_boxes = 0
    config.ocr_preprocess = True
    config.ocr_min_confidence = 0.25
    config.translation_log_enabled = True
    config.translation_log_max_items = 20

    capture = ImageCapture(image)
    ocr = RapidOCRProvider(config)

    ocr_frame = Frame(
        image=image.copy(),
        timestamp=0.0,
        window_rect=Rect(0, 0, image.shape[1], image.shape[0]),
    )
    ocr_started = time.perf_counter()
    raw_boxes = ocr.recognize(ocr_frame)
    ocr_elapsed_ms = (time.perf_counter() - ocr_started) * 1000

    orchestrator = PipelineOrchestrator(
        config=config,
        capture_service=capture,
        ocr_provider=ocr,
        local_translator=NoopTranslator(),
        cloud_translator=None,
        policy=NoCloudPolicy(),
    )

    pipeline_started = time.perf_counter()
    items = orchestrator.process_window(1)
    pipeline_elapsed_ms = (time.perf_counter() - pipeline_started) * 1000

    preview = image.copy()
    lines = []
    for index, item in enumerate(items, start=1):
        draw_wrapped_text(preview, item.translated_text, item.bbox)
        lines.append(f"[{index}] bbox=({item.bbox.x},{item.bbox.y},{item.bbox.width},{item.bbox.height})")
        lines.append(item.translated_text)
        lines.append("")

    cv2.imwrite(str(OUTPUT), preview)
    LOG.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    print(f"Wrote {LOG}")
    print(f"RapidOCR raw boxes after line-merge: {len(raw_boxes)}")
    print(f"RapidOCR recognize: {ocr_elapsed_ms:.1f} ms")
    print(f"Grouped overlay items: {len(items)}")
    print(f"Full pipeline process_window: {pipeline_elapsed_ms:.1f} ms")


if __name__ == "__main__":
    main()
