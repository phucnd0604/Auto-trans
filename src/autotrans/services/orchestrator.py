from __future__ import annotations

import socket
import time
from collections import Counter
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
from autotrans.services.subtitle import SubtitleDetector
from autotrans.services.tracker import OCRTracker
from autotrans.services.translation import TranslatorProvider
from autotrans.utils.runtime_diagnostics import RuntimeDiagnostics
from autotrans.utils.text import canonicalize_text, is_probably_garbage_text, normalize_text, tokenize_words


class PipelineOrchestrator:
    def __init__(
        self,
        config: AppConfig,
        capture_service: CaptureService,
        ocr_provider: OCRProvider,
        local_translator: TranslatorProvider,
        cloud_translator: TranslatorProvider | None,
        deep_ocr_provider: OCRProvider | None = None,
        cache: TranslationCache | None = None,
        tracker: OCRTracker | None = None,
        subtitle_detector: SubtitleDetector | None = None,
        diagnostics: RuntimeDiagnostics | None = None,
    ) -> None:
        self.config = config
        self.capture_service = capture_service
        self.ocr_provider = ocr_provider
        self.deep_ocr_provider = deep_ocr_provider or ocr_provider
        self.local_translator = local_translator
        self.cloud_translator = cloud_translator
        self.cache = cache or TranslationCache()
        self.tracker = tracker or OCRTracker(
            debounce_frames=config.debounce_frames,
            max_missed_frames=config.subtitle_hold_frames,
        )
        self.subtitle_detector = subtitle_detector or SubtitleDetector(config)
        self.diagnostics = diagnostics
        self.stats = PipelineStats()
        self._stable_counts: dict[str, int] = {}
        self._last_text_signature = ""
        self._last_overlay_items: list[OverlayItem] = []
        self._last_window_height = 1080
        self._last_window_width = 1920
        self._last_translate_step_ms = 0.0

    def _select_deep_translator(self) -> tuple[TranslatorProvider, str]:
        translator = self.cloud_translator
        if translator is not None and self._network_available():
            return translator, "cloud"
        return self.local_translator, "local"

    def _log(self, message: str) -> None:
        if self.config.runtime_verbose_log:
            print(f"[AutoTrans] {message}", flush=True)

    def _record_runtime_sample(
        self,
        kind: str,
        *,
        timings_ms: dict[str, float],
        counts: dict[str, int],
        state: dict[str, object],
    ) -> None:
        if self.diagnostics is None:
            return
        self.diagnostics.record_sample(kind, timings_ms=timings_ms, counts=counts, state=state)
        spike_threshold = max(self.config.diagnostics_trigger_threshold_ms, 1)
        ocr_ms = float(timings_ms.get("ocr", 0.0))
        total_ms = float(timings_ms.get("total", 0.0))
        if ocr_ms < spike_threshold and total_ms < spike_threshold:
            return
        event_kind = "ocr_spike" if ocr_ms >= spike_threshold else "pipeline_spike"
        self.diagnostics.record_event(
            event_kind,
            f"{kind} runtime spike detected",
            details={
                "threshold_ms": spike_threshold,
                "ocr_ms": round(ocr_ms, 1),
                "total_ms": round(total_ms, 1),
            },
            snapshot={
                "kind": kind,
                "timings_ms": timings_ms,
                "counts": counts,
                "state": state,
            },
        )

    def _record_event(
        self,
        kind: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
        snapshot: dict[str, object] | None = None,
    ) -> None:
        if self.diagnostics is None:
            return
        self.diagnostics.record_event(kind, message, details=details, snapshot=snapshot)

    def _network_available(self) -> bool:
        try:
            socket.gethostbyname(self.config.deep_translation_host(self.config.deep_translation_provider))
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
            self._log_subtitle_selection_diagnostics(frame, boxes)
            selected = self.subtitle_detector.select(frame, boxes)
        else:
            selected = boxes
        filtered: list[OCRBox] = []
        skipped_short = 0
        skipped_hud = 0
        for box in selected:
            normalized = normalize_text(box.source_text)
            alnum_count = sum(char.isalnum() for char in normalized)
            if alnum_count <= 2:
                skipped_short += 1
                continue
            if not self.config.subtitle_mode and self._should_skip_hud_noise(frame, box, normalized):
                skipped_hud += 1
                continue
            filtered.append(box)
        if skipped_short:
            self._log(f"skipped {skipped_short} short OCR box(es) (<=2 chars)")
        if skipped_hud:
            self._log(f"skipped {skipped_hud} HUD/menu OCR box(es)")
        return filtered

    def _log_subtitle_selection_diagnostics(self, frame: Frame, boxes: list[OCRBox]) -> None:
        if not self.config.runtime_verbose_log or not boxes:
            return
        rejection_counts: Counter[str] = Counter()
        accepted = 0
        for box in boxes:
            reason = self.subtitle_detector.explain_rejection(frame, box)
            if reason is None:
                accepted += 1
            else:
                rejection_counts[reason] += 1
        reasons = ", ".join(f"{key}={value}" for key, value in rejection_counts.most_common(4))
        self._log(
            f"subtitle filter raw={len(boxes)} accepted={accepted} rejected={len(boxes) - accepted}"
            + (f" reasons: {reasons}" if reasons else "")
        )

    @staticmethod
    def _should_skip_hud_noise(frame: Frame, box: OCRBox, normalized: str) -> bool:
        tokens = tokenize_words(normalized)
        if not tokens:
            return True

        alnum_count = sum(char.isalnum() for char in normalized)
        alpha_count = sum(char.isalpha() for char in normalized)
        digit_count = sum(char.isdigit() for char in normalized)
        uppercase_alpha = sum(char.isupper() for char in normalized if char.isalpha())
        digit_ratio = digit_count / max(alnum_count, 1)
        uppercase_ratio = uppercase_alpha / max(alpha_count, 1)

        top_band = frame.window_rect.height * 0.18
        side_band = frame.window_rect.width * 0.22
        near_top = box.bbox.y <= top_band
        near_side = box.bbox.x <= side_band or box.bbox.right >= frame.window_rect.width - side_band
        short_label = len(tokens) <= 2 and len(normalized) <= 24

        if digit_ratio >= 0.7 and alnum_count <= 16:
            return True

        if near_top and near_side and short_label and (digit_ratio >= 0.2 or uppercase_ratio >= 0.85):
            return True

        return False

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
                pending_logs.append(
                    f"pending[{count}/{self.config.translation_stable_scans}] {normalize_text(box.source_text)!r}"
                )

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

    @staticmethod
    def _boxes_form_block(anchor: OCRBox, previous: OCRBox, candidate: OCRBox) -> bool:
        vertical_gap = candidate.bbox.y - previous.bbox.bottom
        if vertical_gap < -max(previous.bbox.height, candidate.bbox.height) * 0.25:
            return False
        if vertical_gap > max(previous.bbox.height, candidate.bbox.height) * 1.3 + 14:
            return False

        left_delta = abs(anchor.bbox.x - candidate.bbox.x)
        allowed_left_delta = max(32, int(min(anchor.bbox.width, candidate.bbox.width) * 0.18))
        if left_delta > allowed_left_delta:
            return False

        horizontal_overlap = min(previous.bbox.right, candidate.bbox.right) - max(previous.bbox.x, candidate.bbox.x)
        if horizontal_overlap <= 0 and left_delta > 16:
            return False

        return True

    def _group_boxes_for_deep_translation(self, boxes: list[OCRBox]) -> list[OCRBox]:
        if len(boxes) <= 1:
            return boxes

        ordered = sorted(boxes, key=lambda item: (item.bbox.y, item.bbox.x))
        groups: list[list[OCRBox]] = []
        for box in ordered:
            placed = False
            for group in groups:
                anchor = group[0]
                previous = group[-1]
                if self._boxes_form_block(anchor, previous, box):
                    group.append(box)
                    placed = True
                    break
            if not placed:
                groups.append([box])

        merged: list[OCRBox] = []
        for index, group in enumerate(groups, start=1):
            x = min(item.bbox.x for item in group)
            y = min(item.bbox.y for item in group)
            right = max(item.bbox.right for item in group)
            bottom = max(item.bbox.bottom for item in group)
            merged.append(
                OCRBox(
                    id=f"deep-block-{index}",
                    source_text="\n".join(
                        normalize_text(item.source_text)
                        for item in group
                        if normalize_text(item.source_text)
                    ),
                    confidence=min(item.confidence for item in group),
                    bbox=Rect(x=x, y=y, width=right - x, height=bottom - y),
                    language_hint=group[0].language_hint,
                    line_id="deep-ui-block",
                )
            )
        return merged

    @staticmethod
    def _split_deep_batches(boxes: list[OCRBox], max_items: int = 6, max_chars: int = 900) -> list[list[OCRBox]]:
        batches: list[list[OCRBox]] = []
        current: list[OCRBox] = []
        current_chars = 0
        for box in boxes:
            text_len = len(normalize_text(box.source_text))
            would_exceed_items = len(current) >= max_items
            would_exceed_chars = current and (current_chars + text_len) > max_chars
            if would_exceed_items or would_exceed_chars:
                batches.append(current)
                current = []
                current_chars = 0
            current.append(box)
            current_chars += text_len
        if current:
            batches.append(current)
        return batches

    def _select_deep_boxes(self, boxes: list[OCRBox]) -> list[OCRBox]:
        filtered: list[OCRBox] = []
        for box in boxes:
            normalized = normalize_text(box.source_text)
            if not normalized:
                continue
            alnum_count = sum(char.isalnum() for char in normalized)
            if alnum_count <= 2:
                continue
            if len(normalized) <= 3 and any(char.isdigit() for char in normalized):
                continue
            if is_probably_garbage_text(normalized):
                continue
            filtered.append(box)
        return filtered

    @staticmethod
    def _smooth_rect(previous: Rect, current: Rect) -> Rect:
        return Rect(
            x=int(round((previous.x * 0.65) + (current.x * 0.35))),
            y=int(round((previous.y * 0.65) + (current.y * 0.35))),
            width=int(round((previous.width * 0.65) + (current.width * 0.35))),
            height=int(round((previous.height * 0.65) + (current.height * 0.35))),
        )

    def _overlay_match_score(self, previous: OverlayItem, current: OverlayItem) -> float:
        iou = previous.bbox.iou(current.bbox)
        prev_text = normalize_text(previous.source_text or previous.translated_text)
        curr_text = normalize_text(current.source_text or current.translated_text)
        text_score = ratio(prev_text, curr_text) / 100.0 if prev_text and curr_text else 0.0
        prev_canonical = canonicalize_text(previous.source_text or previous.translated_text)
        curr_canonical = canonicalize_text(current.source_text or current.translated_text)
        canonical_score = ratio(prev_canonical, curr_canonical) / 100.0 if prev_canonical and curr_canonical else 0.0
        center_dx = abs((previous.bbox.x + previous.bbox.width / 2) - (current.bbox.x + current.bbox.width / 2))
        center_dy = abs((previous.bbox.y + previous.bbox.height / 2) - (current.bbox.y + current.bbox.height / 2))
        max_dx = max(previous.bbox.width, current.bbox.width, 1) * 0.35 + 12
        max_dy = max(previous.bbox.height, current.bbox.height, 1) * 0.6 + 12
        if center_dx > max_dx or center_dy > max_dy:
            return 0.0
        return max(iou, 0.0) * 0.45 + text_score * 0.2 + canonical_score * 0.35

    def _reconcile_overlay_items(self, items: list[OverlayItem]) -> list[OverlayItem]:
        if not items or not self._last_overlay_items:
            return items

        remaining_previous = list(self._last_overlay_items)
        reconciled: list[OverlayItem] = []
        reused = 0

        for item in items:
            best_index = -1
            best_score = 0.0
            for index, previous in enumerate(remaining_previous):
                score = self._overlay_match_score(previous, item)
                if score > best_score:
                    best_score = score
                    best_index = index

            if best_index >= 0 and best_score >= 0.82:
                previous = remaining_previous.pop(best_index)
                reconciled.append(
                    OverlayItem(
                        bbox=self._smooth_rect(previous.bbox, item.bbox),
                        translated_text=previous.translated_text,
                        style=item.style,
                        visibility_state=item.visibility_state,
                        source_text=previous.source_text or item.source_text,
                        tracking_key=previous.tracking_key or item.tracking_key,
                        linger_seconds=1.5
                        if self._is_subtitle_bbox(item.bbox)
                        else max(previous.linger_seconds, item.linger_seconds, self.config.overlay_ttl_seconds),
                        region=previous.region or item.region,
                    )
                )
                reused += 1
            else:
                reconciled.append(item)

        if reused:
            self._log(f"overlay reconciled {reused} item(s) with previous frame")
        return reconciled

    def _text_signature(self, boxes: list[OCRBox]) -> str:
        if not boxes:
            return ""
        ordered = sorted(boxes, key=lambda item: (item.bbox.y, item.bbox.x, canonicalize_text(item.source_text)))
        parts: list[str] = []
        for box in ordered:
            key = canonicalize_text(box.source_text)
            if not key:
                continue
            parts.append(
                f"{key}@{box.bbox.x // 16}:{box.bbox.y // 16}:{box.bbox.width // 16}:{box.bbox.height // 16}"
            )
        return "|".join(parts)

    def _collect_deep_grouped_boxes(self, hwnd: int) -> list[OCRBox]:
        started = time.perf_counter()
        frame = self.capture_service.capture_window(hwnd)
        if frame is None:
            self._record_event(
                "deep_prepare_skipped",
                "Deep translation prepare skipped because capture returned no frame",
                details={"hwnd": hwnd},
            )
            return []

        self._last_window_height = max(frame.window_rect.height, 1)
        self._last_window_width = max(frame.window_rect.width, 1)
        recognize_paragraphs = getattr(self.deep_ocr_provider, "recognize_paragraphs", None)
        used_paragraph_ocr = callable(recognize_paragraphs)
        if used_paragraph_ocr:
            ocr_boxes = recognize_paragraphs(frame)
        else:
            ocr_boxes = self.deep_ocr_provider.recognize(frame)
        ocr_boxes = self._dedupe_boxes(ocr_boxes)
        selected_boxes = self._select_deep_boxes(ocr_boxes)
        grouped_boxes = self._group_boxes_for_deep_translation(selected_boxes)
        self._log(
            f"deep ocr blocks raw={len(ocr_boxes)} selected={len(selected_boxes)} grouped={len(grouped_boxes)} paragraph_ocr={used_paragraph_ocr}"
        )
        total_ms = (time.perf_counter() - started) * 1000.0
        self._log(f"deep prepare total_ms={total_ms:.0f}")
        self._record_runtime_sample(
            "deep_prepare",
            timings_ms={"capture": 0.0, "ocr": total_ms, "total": total_ms},
            counts={
                "raw_boxes": len(ocr_boxes),
                "selected_boxes": len(selected_boxes),
                "grouped_boxes": len(grouped_boxes),
            },
            state={
                "hwnd": hwnd,
                "paragraph_ocr": used_paragraph_ocr,
                "translator": getattr(self.cloud_translator or self.local_translator, "name", "unknown"),
            },
        )
        return [box for box in grouped_boxes if normalize_text(box.source_text)]

    def _deep_overlay_style(self) -> OverlayStyle:
        return OverlayStyle(
            font_size=max(self.config.font_size, 18),
            background_opacity=min(0.96, max(self.config.overlay_background_opacity, 0.82)),
        )

    def build_pending_deep_overlay(self, boxes: list[OCRBox]) -> list[OverlayItem]:
        style = self._deep_overlay_style()
        pending_overlay_items = [
            OverlayItem(
                bbox=box.bbox,
                translated_text="Đang dịch...",
                style=style,
                visibility_state=VisibilityState.PENDING,
                source_text=box.source_text,
                tracking_key=box.id or canonicalize_text(box.source_text),
                linger_seconds=0.0,
                region="deep-ui",
            )
            for box in boxes
        ]
        return self._limit_overlay_groups(
            sorted(pending_overlay_items, key=lambda item: (item.bbox.y, item.bbox.x)),
            max_groups=self._deep_overlay_max_groups(),
        )

    def process_window(
        self,
        hwnd: int,
        emit_overlay: Callable[[list[OverlayItem]], None] | None = None,
    ) -> list[OverlayItem]:
        started = time.perf_counter()
        capture_started = started
        frame = self.capture_service.capture_window(hwnd)
        capture_elapsed_ms = (time.perf_counter() - capture_started) * 1000.0
        if frame is None:
            self._log(f"timing capture={capture_elapsed_ms:.0f}ms total={capture_elapsed_ms:.0f}ms boxes=0->0->0 items=0")
            self._record_runtime_sample(
                "live",
                timings_ms={"capture": capture_elapsed_ms, "ocr": 0.0, "select": 0.0, "translate": 0.0, "overlay": 0.0, "total": capture_elapsed_ms},
                counts={"raw_boxes": 0, "selected_boxes": 0, "stable_boxes": 0, "overlay_items": 0},
                state={"hwnd": hwnd, "translator": getattr(self.local_translator, "name", "local"), "frame_captured": False},
            )
            return []

        self._last_window_height = max(frame.window_rect.height, 1)
        self._last_window_width = max(frame.window_rect.width, 1)

        ocr_started = time.perf_counter()
        ocr_frame, y_offset = self._crop_ocr_frame(frame)
        ocr_boxes = self.ocr_provider.recognize(ocr_frame)
        ocr_boxes = self._offset_boxes(ocr_boxes, y_offset)
        ocr_boxes = self._dedupe_boxes(ocr_boxes)
        ocr_elapsed_ms = (time.perf_counter() - ocr_started) * 1000.0

        select_started = time.perf_counter()
        if self.config.overlay_source_text:
            selected_boxes = self._select_boxes(frame, ocr_boxes)
            tracked_boxes = self._track_boxes(selected_boxes)
            stable_boxes = tracked_boxes
            select_elapsed_ms = (time.perf_counter() - select_started) * 1000.0
            overlay_started = time.perf_counter()
            overlay_items = self._build_source_overlay(stable_boxes)
            translate_elapsed_ms = 0.0
        else:
            selected_boxes = self._select_boxes(frame, ocr_boxes)
            self._log(f"selected {len(selected_boxes)}/{len(ocr_boxes)} OCR boxes for translation")
            stable_boxes = self._stabilize_boxes(selected_boxes)
            tracked_boxes = self._track_boxes(stable_boxes)
            select_elapsed_ms = (time.perf_counter() - select_started) * 1000.0
            overlay_started = time.perf_counter()
            signature = self._text_signature(tracked_boxes)
            if signature and signature == self._last_text_signature:
                self._log(
                    f"text unchanged, reusing previous overlay items={len(self._last_overlay_items)} signature={signature[:96]}"
                )
                overlay_items = list(self._last_overlay_items)
                self._last_translate_step_ms = 0.0
            else:
                overlay_items = self._translate_and_build_overlay(tracked_boxes)
                overlay_items = self._reconcile_overlay_items(overlay_items)
                self._last_text_signature = signature
            stable_boxes = tracked_boxes
            translate_elapsed_ms = getattr(self, "_last_translate_step_ms", 0.0)
        overlay_elapsed_ms = (time.perf_counter() - overlay_started) * 1000.0

        if emit_overlay is not None:
            emit_overlay(overlay_items)
        self._last_overlay_items = list(overlay_items)

        elapsed = max(time.perf_counter() - started, 0.001)
        self.stats.capture_fps = 1.0 / elapsed
        self.stats.ocr_fps = 1.0 / elapsed
        self.stats.box_count = len(stable_boxes)
        self.stats.cache_hits = self.cache.hits
        self._log(
            "timing "
            f"capture={capture_elapsed_ms:.0f}ms "
            f"ocr={ocr_elapsed_ms:.0f}ms "
            f"select={select_elapsed_ms:.0f}ms "
            f"translate={translate_elapsed_ms:.0f}ms "
            f"overlay={overlay_elapsed_ms:.0f}ms "
            f"total={elapsed * 1000.0:.0f}ms "
            f"boxes={len(ocr_boxes)}->{len(selected_boxes)}->{len(stable_boxes)} "
            f"items={len(overlay_items)}"
        )
        self._record_runtime_sample(
            "live",
            timings_ms={
                "capture": capture_elapsed_ms,
                "ocr": ocr_elapsed_ms,
                "select": select_elapsed_ms,
                "translate": translate_elapsed_ms,
                "overlay": overlay_elapsed_ms,
                "total": elapsed * 1000.0,
            },
            counts={
                "raw_boxes": len(ocr_boxes),
                "selected_boxes": len(selected_boxes),
                "stable_boxes": len(stable_boxes),
                "overlay_items": len(overlay_items),
            },
            state={
                "hwnd": hwnd,
                "translator": getattr(self.local_translator, "name", "local"),
                "capture_backend": self.config.capture_backend,
                "subtitle_mode": self.config.subtitle_mode,
                "overlay_source_text": self.config.overlay_source_text,
                "cache_hits": self.cache.hits,
            },
        )
        return overlay_items

    def prepare_deep_translation(self, hwnd: int) -> tuple[list[OCRBox], list[OverlayItem]]:
        grouped_boxes = self._collect_deep_grouped_boxes(hwnd)
        if not grouped_boxes:
            self._log("deep translate skipped: no usable OCR blocks")
            self._record_event(
                "deep_prepare_empty",
                "Deep translation found no usable OCR blocks",
                details={"hwnd": hwnd},
            )
            return [], []
        return grouped_boxes, self.build_pending_deep_overlay(grouped_boxes)

    def translate_deep_boxes(self, grouped_boxes: list[OCRBox]) -> list[OverlayItem]:
        started = time.perf_counter()
        translator, translator_kind = self._select_deep_translator()
        translator_name = getattr(translator, "name", translator_kind)
        if not grouped_boxes:
            return []

        results_by_key: dict[str, tuple[str, str, float]] = {}
        pending: list[OCRBox] = []
        deep_glossary_version = f"{self.config.glossary_version}:deep:{translator_name}"
        cache_hits = 0
        for box in grouped_boxes:
            key = canonicalize_text(box.source_text)
            if not key:
                continue
            cache_entry = self.cache.get(
                text=box.source_text,
                source_lang=self.config.source_lang,
                target_lang=self.config.target_lang,
                glossary_version=deep_glossary_version,
            )
            if cache_entry is not None:
                results_by_key[key] = (cache_entry.translated_text, cache_entry.provider, 0.0)
                cache_hits += 1
            else:
                pending.append(box)

        if pending:
            translate_started = time.perf_counter()
            try:
                self._log(f"deep request pending={len(pending)} translator={translator_name}")
                translated = translator.translate_screen_blocks(
                    items=pending,
                    source_lang=self.config.source_lang,
                    target_lang=self.config.target_lang,
                )
            except Exception as exc:
                if translator is self.local_translator:
                    raise
                self._log(f"deep cloud fallback triggered: {exc}")
                self._record_event(
                    "deep_cloud_fallback",
                    "Deep cloud translation failed and fell back to local translator",
                    details={
                        "from_translator": translator_name,
                        "provider": translator_kind,
                        "pending_items": len(pending),
                        "error": repr(exc),
                    },
                    snapshot={
                        "grouped_boxes": len(grouped_boxes),
                        "pending_items": len(pending),
                    },
                )
                translator = self.local_translator
                translator_kind = "local"
                translator_name = getattr(translator, "name", translator_kind)
                deep_glossary_version = f"{self.config.glossary_version}:deep:{translator_name}"
                translated = translator.translate_screen_blocks(
                    items=pending,
                    source_lang=self.config.source_lang,
                    target_lang=self.config.target_lang,
                )
            self._last_translate_step_ms = (time.perf_counter() - translate_started) * 1000.0
            for item in translated:
                key = canonicalize_text(item.source_text)
                if not key or not self._translation_is_usable(item.source_text, item.translated_text):
                    continue
                results_by_key[key] = (item.translated_text, item.provider, item.latency_ms)
                self.cache.put(
                    text=item.source_text,
                    source_lang=self.config.source_lang,
                    target_lang=self.config.target_lang,
                    glossary_version=deep_glossary_version,
                    translated_text=item.translated_text,
                    provider=item.provider,
                )

        style = self._deep_overlay_style()
        overlay_items: list[OverlayItem] = []
        for box in grouped_boxes:
            key = canonicalize_text(box.source_text)
            translated_entry = results_by_key.get(key)
            translated_text = translated_entry[0] if translated_entry else ""
            if not translated_text:
                continue
            overlay_items.append(
                OverlayItem(
                    bbox=box.bbox,
                    translated_text=translated_text,
                    style=style,
                    visibility_state=VisibilityState.VISIBLE,
                    source_text=box.source_text,
                    tracking_key=box.id or key,
                    linger_seconds=0.0,
                    region="deep-ui",
                )
            )

        overlay_items = self._limit_overlay_groups(
            sorted(overlay_items, key=lambda item: (item.bbox.y, item.bbox.x)),
            max_groups=self._deep_overlay_max_groups(),
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._log(
            f"deep summary translator={translator_name} provider={translator_kind} "
            f"cache_hits={cache_hits} misses={len(pending)} grouped={len(grouped_boxes)} shown={len(overlay_items)} total_ms={elapsed_ms:.0f}"
        )
        self._record_runtime_sample(
            "deep_translate",
            timings_ms={
                "translate": getattr(self, "_last_translate_step_ms", 0.0),
                "total": elapsed_ms,
            },
            counts={
                "grouped_boxes": len(grouped_boxes),
                "pending_boxes": len(pending),
                "cache_hits": cache_hits,
                "overlay_items": len(overlay_items),
            },
            state={
                "translator": translator_name,
                "provider": translator_kind,
                "cloud_provider": self.config.deep_translation_provider,
                "cloud_model": self.config.deep_translation_model,
            },
        )
        return overlay_items


    def _translate_pending(self, pending: list[OCRBox], request: TranslationRequest):
        preferred = self.local_translator
        self._log(
            f"live translator={getattr(preferred, 'name', 'local')} provider=local reason=live-local-only items={len(pending)}"
        )
        return preferred.translate_batch(
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

    @staticmethod
    def _overlay_region_for_box(box: OCRBox) -> str:
        line_id = (box.line_id or "").strip().lower()
        if line_id.startswith("subtitle-"):
            return "subtitle"
        if line_id.startswith("objective-"):
            return "objective"
        if line_id.startswith("interaction-"):
            return "interaction"
        if line_id.startswith("ui-"):
            return "ui"
        return ""

    def _is_subtitle_bbox(self, bbox: Rect) -> bool:
        window_height = max(self._last_window_height, 1)
        window_width = max(self._last_window_width, 1)
        region_top = window_height * self.config.subtitle_region_top_ratio
        return (
            bbox.y >= region_top
            and bbox.x < (window_width / 2) < bbox.right
        )

    def _should_skip_similar_subtitle(self, box: OCRBox, translated_text: str) -> bool:
        if not self._is_subtitle_bbox(box.bbox):
            return False

        current_source = canonicalize_text(box.source_text)
        current_translated = canonicalize_text(translated_text)
        for previous in reversed(self._last_overlay_items):
            if not self._is_subtitle_bbox(previous.bbox):
                continue
            prev_source = canonicalize_text(previous.source_text)
            prev_translated = canonicalize_text(previous.translated_text)
            source_score = ratio(prev_source, current_source) / 100.0 if prev_source and current_source else 0.0
            translated_score = ratio(prev_translated, current_translated) / 100.0 if prev_translated and current_translated else 0.0
            position_score = previous.bbox.iou(box.bbox)
            if max(source_score, translated_score) >= 0.9 and position_score >= 0.35:
                self._log(f"subtitle skip similar {normalize_text(box.source_text)!r}")
                return True
            break
        return False

    @staticmethod
    def _boxes_belong_to_same_paragraph(
        anchor: OverlayItem,
        previous: OverlayItem,
        candidate: OverlayItem,
    ) -> bool:
        anchor_box = anchor.bbox
        current_box = previous.bbox
        candidate_box = candidate.bbox
        vertical_gap = candidate_box.y - current_box.bottom
        if vertical_gap < -max(current_box.height, candidate_box.height) * 0.25:
            return False
        if vertical_gap > max(current_box.height, candidate_box.height) * 1.15 + 8:
            return False

        left_delta = abs(anchor_box.x - candidate_box.x)
        allowed_left_delta = max(24, int(min(anchor_box.width, candidate_box.width) * 0.12))
        if left_delta > allowed_left_delta:
            return False

        overlap_x = min(anchor_box.right, candidate_box.right) - max(anchor_box.x, candidate_box.x)
        if overlap_x <= 0 and left_delta > 12:
            return False

        return True

    def _group_overlay_items(self, items: list[OverlayItem]) -> list[OverlayItem]:
        if len(items) <= 1:
            return items

        ordered = sorted(items, key=lambda item: (item.bbox.y, item.bbox.x))
        groups: list[list[OverlayItem]] = []
        for item in ordered:
            placed = False
            for group in groups:
                anchor = group[0]
                previous = group[-1]
                if self._boxes_belong_to_same_paragraph(anchor, previous, item):
                    group.append(item)
                    placed = True
                    break
            if not placed:
                groups.append([item])

        if len(groups) == len(items):
            return items

        merged_items: list[OverlayItem] = []
        merged_count = 0
        for group in groups:
            if len(group) == 1:
                merged_items.append(group[0])
                continue

            merged_count += len(group) - 1
            x = min(item.bbox.x for item in group)
            y = min(item.bbox.y for item in group)
            right = max(item.bbox.right for item in group)
            bottom = max(item.bbox.bottom for item in group)
            merged_items.append(
                OverlayItem(
                    bbox=Rect(x=x, y=y, width=right - x, height=bottom - y),
                    translated_text="\n".join(
                        normalize_text(item.translated_text)
                        for item in group
                        if normalize_text(item.translated_text)
                    ),
                    style=group[0].style,
                    visibility_state=group[0].visibility_state,
                    source_text="\n".join(
                        normalize_text(item.source_text)
                        for item in group
                        if normalize_text(item.source_text)
                    ),
                    tracking_key="paragraph-" + "-".join(
                        item.tracking_key or canonicalize_text(item.source_text)
                        for item in group
                    ),
                    linger_seconds=max(item.linger_seconds for item in group),
                    region=group[0].region,
                )
            )

        if merged_count:
            self._log(f"grouped {merged_count} overlay box(es) into paragraph blocks")
        return self._limit_overlay_groups(merged_items)

    def _deep_overlay_max_groups(self) -> int:
        base = max(self.config.overlay_max_groups, 0)
        if base == 0:
            return 0
        return max(base * 3, 24)

    def _limit_overlay_groups(self, items: list[OverlayItem], max_groups: int | None = None) -> list[OverlayItem]:
        if max_groups is None:
            max_groups = max(self.config.overlay_max_groups, 0)
        else:
            max_groups = max(max_groups, 0)
        if max_groups == 0 or len(items) <= max_groups:
            return items

        def score(item: OverlayItem) -> tuple[int, int, int]:
            text_len = len(normalize_text(item.source_text))
            lower_bias = item.bbox.y + item.bbox.height
            area = item.bbox.width * item.bbox.height
            return (area + (lower_bias * 4) + (text_len * 8), lower_bias, text_len)

        kept = sorted(items, key=score, reverse=True)[:max_groups]
        kept_sorted = sorted(kept, key=lambda item: (item.bbox.y, item.bbox.x))
        skipped = len(items) - len(kept_sorted)
        if skipped > 0:
            self._log(f"limited overlay groups, dropped {skipped} low-priority block(s)")
        return kept_sorted

    def _build_source_overlay(self, boxes: list[OCRBox]) -> list[OverlayItem]:
        style = OverlayStyle(
            font_size=self.config.font_size,
            background_opacity=self.config.overlay_background_opacity,
        )
        items = [
            OverlayItem(
                bbox=box.bbox,
                translated_text=box.source_text,
                style=style,
                visibility_state=VisibilityState.VISIBLE,
                source_text=box.source_text,
                tracking_key=box.id or canonicalize_text(box.source_text),
                linger_seconds=1.5 if self._is_subtitle_bbox(box.bbox) else self.config.overlay_ttl_seconds,
                region=self._overlay_region_for_box(box),
            )
            for box in boxes
            if normalize_text(box.source_text)
        ]
        return self._group_overlay_items(items)

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
                results_by_key[key] = (cache_entry.translated_text, cache_entry.provider, 0.0)
                cache_hits += 1
            else:
                pending.append(box)
                cache_misses += 1

        self._log(f"live cache hits={cache_hits} misses={cache_misses} request_items={len(request.items)}")

        if pending:
            translate_started = time.perf_counter()
            translated = self._translate_pending(pending, request)
            self._last_translate_step_ms = (time.perf_counter() - translate_started) * 1000.0
            self._log(
                f"live translate_ms={self._last_translate_step_ms:.0f} pending_items={len(pending)} translator={getattr(self.local_translator, 'name', 'local')}"
            )
            for item in translated:
                key = canonicalize_text(item.source_text)
                if not key:
                    continue
                if not self._translation_is_usable(item.source_text, item.translated_text):
                    self._log(f"dropped unusable translation for {normalize_text(item.source_text)!r}")
                    continue
                results_by_key[key] = (item.translated_text, item.provider, item.latency_ms)
                self.cache.put(
                    text=item.source_text,
                    source_lang=request.source_lang,
                    target_lang=request.target_lang,
                    glossary_version=self.config.glossary_version,
                    translated_text=item.translated_text,
                    provider=item.provider,
                )
                self.stats.translation_latency_ms = item.latency_ms
        else:
            self._last_translate_step_ms = 0.0

        style = OverlayStyle(
            font_size=self.config.font_size,
            background_opacity=self.config.overlay_background_opacity,
        )
        overlay_items: list[OverlayItem] = []
        for box in boxes:
            key = canonicalize_text(box.source_text)
            translated_entry = results_by_key.get(key)
            translated = translated_entry[0] if translated_entry else ""
            if not translated:
                self._log(f"overlay skip no-translation {normalize_text(box.source_text)!r}")
                continue
            if self._should_skip_similar_subtitle(box, translated):
                continue
            latency_ms = translated_entry[2] if translated_entry else 0.0
            overlay_items.append(
                OverlayItem(
                    bbox=box.bbox,
                    translated_text=translated,
                    style=style,
                    visibility_state=VisibilityState.VISIBLE,
                    source_text=box.source_text,
                    tracking_key=box.id or key,
                    linger_seconds=1.5 if self._is_subtitle_bbox(box.bbox) else self._overlay_linger_seconds(latency_ms),
                    region=self._overlay_region_for_box(box),
                )
            )

        overlay_items = self._group_overlay_items(overlay_items)
        for item in overlay_items[: self.config.translation_log_max_items]:
            self._log(
                f"overlay add {normalize_text(item.source_text)!r} -> {normalize_text(item.translated_text)!r} @ ({item.bbox.x},{item.bbox.y},{item.bbox.width},{item.bbox.height}) linger={item.linger_seconds:.2f}s"
            )
        self._log(
            f"live summary translator={getattr(self.local_translator, 'name', 'local')} cache_hits={cache_hits} misses={cache_misses} shown={len(overlay_items)}"
        )
        return overlay_items
