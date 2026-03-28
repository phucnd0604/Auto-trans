from __future__ import annotations

import socket
import time
from collections.abc import Callable

from rapidfuzz.fuzz import ratio

from autotrans.config import AppConfig
from autotrans.models import (
    Frame,
    OCRBox,
    OverlayItem,
    OverlayStyle,
    PipelineStats,
    QualityMode,
    Rect,
    TranslationRequest,
    VisibilityState,
)
from autotrans.services.cache import TranslationCache
from autotrans.services.capture import CaptureService
from autotrans.services.ocr import OCRProvider
from autotrans.services.policy import ProviderPolicy
from autotrans.services.subtitle import SubtitleDetector
from autotrans.services.tracker import OCRTracker
from autotrans.services.translation import TranslatorProvider
from autotrans.utils.text import canonicalize_text, is_probably_garbage_text, normalize_text, tokenize_words


class PipelineOrchestrator:
    def __init__(
        self,
        config: AppConfig,
        capture_service: CaptureService,
        ocr_provider: OCRProvider,
        local_translator: TranslatorProvider,
        cloud_translator: TranslatorProvider | None,
        cache: TranslationCache | None = None,
        policy: ProviderPolicy | None = None,
        tracker: OCRTracker | None = None,
        subtitle_detector: SubtitleDetector | None = None,
    ) -> None:
        self.config = config
        self.capture_service = capture_service
        self.ocr_provider = ocr_provider
        self.local_translator = local_translator
        self.cloud_translator = cloud_translator
        self.cache = cache or TranslationCache()
        self.policy = policy or ProviderPolicy(cloud_timeout_ms=config.cloud_timeout_ms)
        self.tracker = tracker or OCRTracker(debounce_frames=config.debounce_frames, max_missed_frames=config.subtitle_hold_frames)
        self.subtitle_detector = subtitle_detector or SubtitleDetector(config)
        self.stats = PipelineStats()
        self._stable_counts: dict[str, int] = {}

    def _log(self, message: str) -> None:
        if self.config.translation_log_enabled:
            print(f"[AutoTrans] {message}", flush=True)

    def _network_available(self) -> bool:
        if self.config.cloud_is_localhost():
            return True
        try:
            socket.gethostbyname(self.config.cloud_base_host())
            return True
        except OSError:
            return False

    def _crop_ocr_frame(self, frame: Frame) -> tuple[Frame, int]:
        if not (self.config.subtitle_mode and self.config.ocr_crop_subtitle_only):
            return frame, 0

        crop_top = int(frame.window_rect.height * self.config.subtitle_region_top_ratio)
        crop_top = max(0, min(crop_top, frame.window_rect.height - 1))
        cropped = frame.image[crop_top:, :, :]
        cropped_frame = Frame(
            image=cropped,
            timestamp=frame.timestamp,
            window_rect=Rect(0, 0, frame.window_rect.width, cropped.shape[0]),
            scale=frame.scale,
            metadata=frame.metadata,
        )
        return cropped_frame, crop_top

    def _offset_boxes(self, boxes: list[OCRBox], y_offset: int) -> list[OCRBox]:
        if y_offset <= 0:
            return boxes
        adjusted: list[OCRBox] = []
        for box in boxes:
            adjusted.append(
                OCRBox(
                    id=box.id,
                    source_text=box.source_text,
                    confidence=box.confidence,
                    bbox=Rect(
                        x=box.bbox.x,
                        y=box.bbox.y + y_offset,
                        width=box.bbox.width,
                        height=box.bbox.height,
                    ),
                    language_hint=box.language_hint,
                    line_id=box.line_id,
                )
            )
        return adjusted

    def _dedupe_boxes(self, boxes: list[OCRBox]) -> list[OCRBox]:
        kept: list[OCRBox] = []
        for box in sorted(boxes, key=lambda item: item.confidence, reverse=True):
            text = normalize_text(box.source_text)
            if not text:
                continue
            duplicate = False
            for existing in kept:
                iou = existing.bbox.iou(box.bbox)
                text_score = ratio(normalize_text(existing.source_text), text) / 100.0
                if iou >= 0.45 or (iou >= 0.2 and text_score >= 0.9):
                    duplicate = True
                    break
            if not duplicate:
                kept.append(box)
        return kept

    def _select_boxes(self, frame: Frame, boxes: list[OCRBox]) -> list[OCRBox]:
        if self.config.subtitle_mode:
            selected = self.subtitle_detector.select(frame, boxes)
        else:
            selected = boxes
        filtered: list[OCRBox] = []
        skipped_short = 0
        for box in selected:
            if len(tokenize_words(box.source_text)) < 3:
                skipped_short += 1
                continue
            filtered.append(box)
        if skipped_short:
            self._log(f"skipped {skipped_short} short OCR box(es) (<3 words)")
        return filtered

    def _stabilize_boxes(self, boxes: list[OCRBox]) -> list[OCRBox]:
        if self.config.translation_stable_scans <= 1 or self.config.overlay_source_text:
            return boxes

        next_counts: dict[str, int] = {}
        best_by_key: dict[str, OCRBox] = {}
        for box in boxes:
            key = canonicalize_text(box.source_text)
            if not key:
                continue
            next_counts[key] = self._stable_counts.get(key, 0) + 1
            existing = best_by_key.get(key)
            if existing is None or box.confidence > existing.confidence:
                best_by_key[key] = box

        stable: list[OCRBox] = []
        pending_logs: list[str] = []
        stable_logs: list[str] = []
        for key, box in best_by_key.items():
            count = next_counts[key]
            if count >= self.config.translation_stable_scans:
                stable.append(box)
                stable_logs.append(f"stable[{count}] {normalize_text(box.source_text)!r}")
            else:
                pending_logs.append(f"pending[{count}/{self.config.translation_stable_scans}] {normalize_text(box.source_text)!r}")

        self._stable_counts = next_counts

        for line in pending_logs[: self.config.translation_log_max_items]:
            self._log(line)
        for line in stable_logs[: self.config.translation_log_max_items]:
            self._log(line)
        return stable

    def _track_boxes(self, boxes: list[OCRBox]) -> list[OCRBox]:
        original_debounce = self.tracker.debounce_frames
        self.tracker.debounce_frames = 1
        try:
            return self.tracker.update(boxes)
        finally:
            self.tracker.debounce_frames = original_debounce

    def process_window(
        self,
        hwnd: int,
        emit_overlay: Callable[[list[OverlayItem]], None] | None = None,
    ) -> list[OverlayItem]:
        started = time.perf_counter()
        frame = self.capture_service.capture_window(hwnd)
        if frame is None:
            return []

        ocr_frame, y_offset = self._crop_ocr_frame(frame)
        ocr_boxes = self.ocr_provider.recognize(ocr_frame)
        ocr_boxes = self._offset_boxes(ocr_boxes, y_offset)
        ocr_boxes = self._dedupe_boxes(ocr_boxes)

        if self.config.overlay_source_text:
            selected_boxes = self._select_boxes(frame, ocr_boxes)
            tracked_boxes = self._track_boxes(selected_boxes)
            stable_boxes = tracked_boxes
            overlay_items = self._build_source_overlay(stable_boxes)
        else:
            selected_boxes = self._select_boxes(frame, ocr_boxes)
            self._log(
                f"selected {len(selected_boxes)}/{len(ocr_boxes)} OCR boxes for translation"
            )
            stable_boxes = self._stabilize_boxes(selected_boxes)
            tracked_boxes = self._track_boxes(stable_boxes)
            overlay_items = self._translate_and_build_overlay(tracked_boxes)
            stable_boxes = tracked_boxes

        if emit_overlay is not None:
            emit_overlay(overlay_items)

        elapsed = max(time.perf_counter() - started, 0.001)
        self.stats.capture_fps = 1.0 / elapsed
        self.stats.ocr_fps = 1.0 / elapsed
        self.stats.box_count = len(stable_boxes)
        self.stats.cache_hits = self.cache.hits
        return overlay_items

    def _translate_pending(self, pending: list[OCRBox], request: TranslationRequest):
        decision = self.policy.select(
            text_items=pending,
            mode=request.mode,
            network_state=self._network_available() and self.cloud_translator is not None,
        )
        preferred = (
            self.cloud_translator
            if decision.provider == "cloud" and self.cloud_translator is not None
            else self.local_translator
        )
        self._log(
            f"translator={getattr(preferred, 'name', decision.provider)} provider={decision.provider} reason={decision.reason} items={len(pending)}"
        )
        try:
            return preferred.translate_batch(
                items=pending,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                mode=request.mode,
            )
        except Exception as exc:
            if preferred is self.local_translator:
                raise
            self._log(f"cloud fallback triggered: {exc}")
            return self.local_translator.translate_batch(
                items=pending,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                mode=request.mode,
            )

    def _translation_is_usable(self, source_text: str, translated_text: str) -> bool:
        source = normalize_text(source_text)
        translated = normalize_text(translated_text)
        if not translated:
            return False
        if is_probably_garbage_text(translated):
            return False
        if len(translated) > max(len(source) * 3, 80):
            return False
        return True

    def _overlay_linger_seconds(self, latency_ms: float) -> float:
        capture_interval = 1.0 / max(self.config.capture_fps, 0.01)
        latency_seconds = max(latency_ms, 0.0) / 1000.0
        min_linger = capture_interval
        desired_linger = capture_interval + latency_seconds
        return max(min_linger, min(self.config.overlay_ttl_seconds, desired_linger))

    def _build_source_overlay(self, boxes: list[OCRBox]) -> list[OverlayItem]:
        style = OverlayStyle(
            font_size=self.config.font_size,
            background_opacity=self.config.overlay_background_opacity,
        )
        return [
            OverlayItem(
                bbox=box.bbox,
                translated_text=box.source_text,
                style=style,
                visibility_state=VisibilityState.VISIBLE,
                source_text=box.source_text,
                tracking_key=box.id or canonicalize_text(box.source_text),
                linger_seconds=self.config.overlay_ttl_seconds,
            )
            for box in boxes
            if normalize_text(box.source_text)
        ]

    def _translate_and_build_overlay(self, boxes: list[OCRBox]) -> list[OverlayItem]:
        if not boxes:
            return []

        request = TranslationRequest(
            items=boxes,
            source_lang=self.config.source_lang,
            target_lang=self.config.target_lang,
            mode=QualityMode(self.config.mode),
        )

        results_by_key: dict[str, tuple[str, str, float]] = {}
        pending: list[OCRBox] = []
        cache_hits = 0
        cache_misses = 0
        for box in request.items:
            key = canonicalize_text(box.source_text)
            if not key:
                continue
            cache_entry = self.cache.get(
                text=box.source_text,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                glossary_version=self.config.glossary_version,
            )
            if cache_entry is not None:
                results_by_key[key] = (
                    cache_entry.translated_text,
                    cache_entry.provider,
                    0.0,
                )
                cache_hits += 1
            else:
                pending.append(box)
                cache_misses += 1

        self._log(f"cache hits={cache_hits} misses={cache_misses}")

        if pending:
            translated = self._translate_pending(pending, request)
            for item in translated:
                key = canonicalize_text(item.source_text)
                if not key:
                    continue
                if not self._translation_is_usable(item.source_text, item.translated_text):
                    self._log(f"dropped unusable translation for {normalize_text(item.source_text)!r}")
                    continue
                results_by_key[key] = (
                    item.translated_text,
                    item.provider,
                    item.latency_ms,
                )
                self.cache.put(
                    text=item.source_text,
                    source_lang=request.source_lang,
                    target_lang=request.target_lang,
                    glossary_version=self.config.glossary_version,
                    translated_text=item.translated_text,
                    provider=item.provider,
                )
                self.stats.translation_latency_ms = item.latency_ms

        style = OverlayStyle(
            font_size=self.config.font_size,
            background_opacity=self.config.overlay_background_opacity,
        )
        overlay_items: list[OverlayItem] = []
        for box in boxes:
            key = canonicalize_text(box.source_text)
            translated = results_by_key.get(key, ("", "", 0.0))[0]
            if not translated:
                self._log(f"overlay skip no-translation {normalize_text(box.source_text)!r}")
                continue
            overlay_items.append(
                OverlayItem(
                    bbox=box.bbox,
                    translated_text=translated,
                    style=style,
                    visibility_state=VisibilityState.VISIBLE,
                    source_text=box.source_text,
                    tracking_key=box.id or key,
                    linger_seconds=self._overlay_linger_seconds(results_by_key.get(key, ("", "", 0.0))[2]),
                )
            )
        for item in overlay_items[: self.config.translation_log_max_items]:
            self._log(
                f"overlay add {normalize_text(item.source_text)!r} -> {normalize_text(item.translated_text)!r} @ ({item.bbox.x},{item.bbox.y},{item.bbox.width},{item.bbox.height}) linger={item.linger_seconds:.2f}s"
            )
        return overlay_items










