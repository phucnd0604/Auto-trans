from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QRect, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from autotrans.models import OverlayItem, Rect
from autotrans.models import VisibilityState
from autotrans.utils.text import normalize_text


class OverlayWindow(QWidget):
    def __init__(self, ttl_seconds: float = 1.5, overlay_fps: int = 30) -> None:
        super().__init__()
        self._items: list[OverlayItem] = []
        self._persistent_items: list[OverlayItem] = []
        self._window_rect = Rect(0, 0, 1, 1)
        self._ttl_seconds = ttl_seconds
        self._fade_in_seconds = 0.12
        self._fade_out_seconds = 0.18
        self._live_items: dict[str, tuple[OverlayItem, float, float, float]] = {}
        self._prune_timer = QTimer(self)
        prune_interval_ms = max(int(round(1000.0 / max(overlay_fps, 1))), 33)
        self._prune_timer.setInterval(prune_interval_ms)
        self._prune_timer.timeout.connect(self._prune_expired_items)
        self._prune_timer.start()
        self._overlay_brush = QPixmap(str(Path(__file__).resolve().parent / "assets" / "overlay-brush.png"))
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

    def sync_window_rect(self, rect: Rect) -> None:
        self._window_rect = rect
        self.setGeometry(rect.x, rect.y, rect.width, rect.height)
        self.update()

    def _item_key(self, item: OverlayItem) -> str:
        if item.tracking_key:
            return item.tracking_key
        bbox = item.bbox
        text = normalize_text(item.source_text or item.translated_text)
        return f"{bbox.x}:{bbox.y}:{bbox.width}:{bbox.height}:{text}"

    def _prune_expired_items(self) -> None:
        now = time.monotonic()
        changed = False
        for key, (_, first_seen, last_seen, linger_seconds) in list(self._live_items.items()):
            ttl_seconds = linger_seconds if linger_seconds > 0 else self._ttl_seconds
            if now - last_seen > ttl_seconds + self._fade_out_seconds:
                del self._live_items[key]
                changed = True
        if changed:
            self._items = [item for item, _, _, _ in self._live_items.values()]
            self.update(self.rect())

    def set_overlay_items(self, items: list[OverlayItem]) -> None:
        now = time.monotonic()
        for item in items:
            linger_seconds = item.linger_seconds if item.linger_seconds > 0 else self._ttl_seconds
            key = self._item_key(item)
            existing = self._live_items.get(key)
            first_seen = existing[1] if existing is not None else now
            self._live_items[key] = (item, first_seen, now, linger_seconds)
        self._prune_expired_items()
        self._items = [item for item, _, _, _ in self._live_items.values()]
        self.update(self.rect())

    def clear_overlay_items(self) -> None:
        self._live_items.clear()
        self._items = []
        self.update(self.rect())

    def set_persistent_overlay_items(self, items: list[OverlayItem]) -> None:
        self._persistent_items = list(items)
        self.update(self.rect())

    def clear_persistent_overlay_items(self) -> None:
        self._persistent_items = []
        self.update(self.rect())

    def _font_for_size(self, size: int) -> QFont:
        return QFont("Segoe UI", size)

    def _styled_font(self, size: int, *, subtitle: bool = False, deep_ui: bool = False) -> QFont:
        font = self._font_for_size(size)
        if subtitle:
            font.setWeight(QFont.DemiBold)
        elif deep_ui:
            font.setWeight(QFont.DemiBold)
        return font

    def _looks_like_subtitle_region(self, rect: QRect) -> bool:
        if self.height() <= 0:
            return False
        center_y = rect.y() + (rect.height() / 2)
        return center_y >= self.height() * 0.72

    @staticmethod
    def _is_subtitle_item(item: OverlayItem) -> bool:
        return (item.region or "").lower() == "subtitle"

    @staticmethod
    def _is_deep_ui_item(item: OverlayItem) -> bool:
        return (item.region or "").lower() == "deep-ui"

    def _fit_font_and_panel(
        self,
        text: str,
        rect: QRect,
        *,
        is_subtitle: bool | None = None,
        deep_ui: bool = False,
    ) -> tuple[QFont, QRect, QRect, int]:
        normalized = normalize_text(text)
        if is_subtitle is None:
            is_subtitle = self._looks_like_subtitle_region(rect)
        inner_padding_x = 10 if is_subtitle else 7
        inner_padding_y = 4 if is_subtitle else 2
        is_paragraph = "\n" in text or rect.height() > 40 or len(normalized) > 48
        single_line_flags = Qt.AlignCenter | Qt.TextSingleLine
        wrapped_flags = Qt.AlignCenter | Qt.TextWordWrap
        flags = wrapped_flags if (is_paragraph or is_subtitle) else single_line_flags

        max_panel_width = max(rect.width(), 1)
        max_panel_height = max(rect.height(), 1)

        if is_subtitle:
            max_panel_width = max(max_panel_width, min(int(self.width() * 0.82), max(self.width() - 24, 1)))
            max_panel_height = max(max_panel_height, min(260, max(self.height() // 3, 72)))
            preferred_width = max(min(max_panel_width - 4, int(max_panel_width * 0.72)), 260)
            max_font = 22
            min_font = 22
        elif is_paragraph:
            # Deep UI blocks should stay visually anchored to the detected OCR block.
            max_panel_width = max(rect.width(), 1)
            max_panel_height = max(rect.height(), 1)
            preferred_width = max(max_panel_width - (inner_padding_x * 2), 40)
            max_font = min(16, max(10, int(rect.height() * 0.42)))
            min_font = 6
        else:
            max_panel_width = max(rect.width(), 1)
            max_panel_height = max(rect.height(), 1)
            preferred_width = max(max_panel_width - (inner_padding_x * 2), 30)
            max_font = min(16, max(10, int(rect.height() * 0.54)))
            min_font = 6

        best_font = self._styled_font(min_font, subtitle=is_subtitle, deep_ui=deep_ui)
        best_bounds = QRect(0, 0, max(rect.width(), 1), max(rect.height(), 1))
        best_panel_width = min(max(best_bounds.width() + (inner_padding_x * 2), 1), max_panel_width)
        best_panel_height = max(best_bounds.height() + (inner_padding_y * 2), 1)

        for font_size in range(max_font, min_font - 1, -1):
            font = self._styled_font(font_size, subtitle=is_subtitle, deep_ui=deep_ui)
            metrics = QFontMetrics(font)
            if is_paragraph or is_subtitle:
                measure_width = max(min(preferred_width, max_panel_width) - (inner_padding_x * 2), 1)
                measure_rect = QRect(0, 0, measure_width, max(self.height(), 80))
                bounds = metrics.boundingRect(measure_rect, flags, text)
                panel_width = min(bounds.width() + (inner_padding_x * 2), max_panel_width)
                panel_height = bounds.height() + (inner_padding_y * 2)
            else:
                bounds = metrics.boundingRect(text)
                panel_width = min(bounds.width() + (inner_padding_x * 2), max_panel_width)
                panel_height = bounds.height() + (inner_padding_y * 2)

            best_font = font
            best_bounds = bounds
            best_panel_width = max(panel_width, 1)
            best_panel_height = min(max(panel_height, 1), max_panel_height)

            if is_paragraph or is_subtitle:
                if bounds.height() + (inner_padding_y * 2) <= max_panel_height:
                    break
            else:
                if (
                    bounds.width() + (inner_padding_x * 2) <= max_panel_width
                    and bounds.height() + (inner_padding_y * 2) <= max_panel_height
                ):
                    break

        if not is_subtitle:
            # Deep/UI overlays should occupy the detected OCR box exactly.
            panel_rect = QRect(rect)
            panel_rect.moveLeft(max(0, min(panel_rect.x(), max(self.width() - panel_rect.width(), 0))))
            panel_rect.moveTop(max(0, min(panel_rect.y(), max(self.height() - panel_rect.height(), 0))))
        else:
            panel_x = rect.x() + ((rect.width() - best_panel_width) // 2)
            panel_y = rect.y() + ((rect.height() - best_panel_height) // 2)
            panel_x = max(0, min(panel_x, max(self.width() - best_panel_width, 0)))
            panel_y = max(0, min(panel_y, max(self.height() - best_panel_height, 0)))
            panel_rect = QRect(panel_x, panel_y, best_panel_width, best_panel_height)
        text_rect = panel_rect.adjusted(inner_padding_x, inner_padding_y, -inner_padding_x, -inner_padding_y)
        if text_rect.width() <= 2 or text_rect.height() <= 2:
            text_rect = QRect(panel_rect)
        return best_font, panel_rect, text_rect, flags

    def _resolve_overlap(self, panel_rect: QRect, placed_rects: list[QRect]) -> QRect:
        gap_y = 6
        resolved = QRect(panel_rect)
        moved = True
        while moved:
            moved = False
            for existing in placed_rects:
                if resolved.intersects(existing):
                    resolved.moveTop(existing.top() - resolved.height() - gap_y)
                    moved = True
        if resolved.top() < 0:
            resolved.moveTop(0)
        if resolved.left() < 0:
            resolved.moveLeft(0)
        if resolved.right() > self.width():
            resolved.moveLeft(max(self.width() - resolved.width(), 0))
        if resolved.bottom() > self.height():
            resolved.moveTop(max(self.height() - resolved.height(), 0))
        return resolved

    def _alpha_multiplier(self, item: OverlayItem) -> float:
        key = self._item_key(item)
        data = self._live_items.get(key)
        if data is None:
            return 1.0
        _, first_seen, last_seen, linger_seconds = data
        now = time.monotonic()
        ttl_seconds = linger_seconds if linger_seconds > 0 else self._ttl_seconds
        age = max(now - first_seen, 0.0)
        since_seen = max(now - last_seen, 0.0)
        fade_in = min(age / self._fade_in_seconds, 1.0) if self._fade_in_seconds > 0 else 1.0
        fade_out_start = max(ttl_seconds - self._fade_out_seconds, 0.0)
        if since_seen <= fade_out_start:
            fade_out = 1.0
        else:
            remaining = max((ttl_seconds + self._fade_out_seconds) - since_seen, 0.0)
            fade_out = min(remaining / self._fade_out_seconds, 1.0) if self._fade_out_seconds > 0 else 1.0
        return max(0.0, min(fade_in, fade_out))

    def _expanded_text_rect(
        self,
        text: str,
        font: QFont,
        text_rect: QRect,
        text_flags: int,
        *,
        is_subtitle: bool,
        container_rect: QRect | None = None,
    ) -> QRect:
        metrics = QFontMetrics(font)
        expanded = QRect(text_rect)
        if not is_subtitle:
            return expanded if container_rect is None else expanded.intersected(container_rect)
        if text_flags & Qt.TextWordWrap:
            preferred_width = expanded.width()
            if not is_subtitle:
                preferred_width = min(max(expanded.width() + 120, int(expanded.width() * 1.35)), max(self.width() - 24, 1))
            measure = metrics.boundingRect(QRect(0, 0, max(preferred_width, 1), max(self.height(), 80)), text_flags, text)
        else:
            measure = metrics.boundingRect(text)

        if measure.width() > expanded.width():
            extra_width = measure.width() - expanded.width()
            expanded.adjust(-(extra_width // 2) - 4, 0, (extra_width - (extra_width // 2)) + 4, 0)
        if measure.height() > expanded.height():
            extra_height = measure.height() - expanded.height()
            expanded.adjust(0, -(extra_height // 2) - 2, 0, (extra_height - (extra_height // 2)) + 2)

        if expanded.width() > self.width():
            expanded.setWidth(max(self.width() - 8, 1))
        if expanded.height() > self.height():
            expanded.setHeight(max(self.height() - 8, 1))
        expanded.moveLeft(max(0, min(expanded.x(), max(self.width() - expanded.width(), 0))))
        expanded.moveTop(max(0, min(expanded.y(), max(self.height() - expanded.height(), 0))))
        if container_rect is not None:
            expanded = expanded.intersected(container_rect)
        return expanded

    def _shrink_font_to_fit_rect(
        self,
        text: str,
        font: QFont,
        text_rect: QRect,
        text_flags: int,
        *,
        is_subtitle: bool,
        deep_ui: bool = False,
    ) -> QFont:
        if text_rect.width() <= 0 or text_rect.height() <= 0:
            return font

        current_size = max(font.pointSize(), 1)
        fitted_font = QFont(font)
        min_size = 6 if not is_subtitle else 22

        while current_size >= min_size:
            metrics = QFontMetrics(fitted_font)
            bounds = metrics.boundingRect(QRect(text_rect), text_flags, text)
            if bounds.width() <= text_rect.width() and bounds.height() <= text_rect.height():
                return fitted_font
            current_size -= 1
            if current_size < min_size:
                break
            fitted_font = self._styled_font(current_size, subtitle=is_subtitle, deep_ui=deep_ui)

        return fitted_font

    def _timing_data(self, item: OverlayItem) -> tuple[float, float, float] | None:
        key = self._item_key(item)
        data = self._live_items.get(key)
        if data is None:
            return None
        _, first_seen, last_seen, linger_seconds = data
        return first_seen, last_seen, linger_seconds

    def _subtitle_stack_layout(
        self, subtitle_items: list[OverlayItem]
    ) -> list[tuple[OverlayItem, QRect, QRect, float, QColor]]:
        prepared: list[tuple[OverlayItem, QRect, QRect, float, float]] = []
        for item in subtitle_items:
            alpha = self._alpha_multiplier(item)
            if alpha <= 0.01:
                continue
            local_rect = QRect(
                item.bbox.x,
                item.bbox.y,
                max(item.bbox.width, 1),
                max(item.bbox.height, 1),
            )
            _, panel_rect, text_rect, _ = self._fit_font_and_panel(
                item.translated_text,
                local_rect,
                is_subtitle=True,
                deep_ui=False,
            )
            timing = self._timing_data(item)
            first_seen = timing[0] if timing is not None else time.monotonic()
            prepared.append((item, panel_rect, text_rect, alpha, first_seen))

        if not prepared:
            return []

        prepared.sort(key=lambda current: current[4])
        gap_y = 8
        base_bottom = min(
            max(max(panel.bottom() for _, panel, _, _, _ in prepared), int(self.height() * 0.9)),
            max(self.height() - 16, 1),
        )
        total_height = sum(panel.height() for _, panel, _, _, _ in prepared) + (gap_y * (len(prepared) - 1))
        current_top = max(base_bottom - total_height, 0)

        colors = [
            QColor(255, 251, 0),
        ]
        layout: list[tuple[OverlayItem, QRect, QRect, float, QColor]] = []
        for index, (item, panel_rect, text_rect, alpha, _) in enumerate(prepared):
            resolved_panel = QRect(panel_rect)
            resolved_panel.moveTop(current_top)
            resolved_panel.moveLeft(max(min(panel_rect.x(), self.width() - resolved_panel.width()), 0))
            resolved_text = QRect(text_rect)
            resolved_text.moveTop(resolved_panel.y() + (text_rect.y() - panel_rect.y()))
            resolved_text.moveLeft(resolved_panel.x() + (text_rect.x() - panel_rect.x()))
            color = colors[index % len(colors)]
            layout.append((item, resolved_panel, resolved_text, alpha, color))
            current_top = resolved_panel.bottom() + gap_y
        return layout

    def _draw_overlay_item(
        self,
        painter: QPainter,
        item: OverlayItem,
        panel_rect: QRect,
        text_rect: QRect,
        alpha: float,
        text_color: QColor,
    ) -> None:
        is_subtitle = self._is_subtitle_item(item)
        is_deep_ui = self._is_deep_ui_item(item)
        font, _, _, text_flags = self._fit_font_and_panel(
            item.translated_text,
            panel_rect,
            is_subtitle=is_subtitle,
            deep_ui=is_deep_ui,
        )
        draw_rect = self._expanded_text_rect(
            item.translated_text,
            font,
            QRect(text_rect),
            text_flags,
            is_subtitle=is_subtitle,
            container_rect=panel_rect,
        )
        font = self._shrink_font_to_fit_rect(
            item.translated_text,
            font,
            draw_rect,
            text_flags,
            is_subtitle=is_subtitle,
            deep_ui=is_deep_ui,
        )
        painter.setFont(font)
        draw_rect = self._expanded_text_rect(
            item.translated_text,
            font,
            QRect(text_rect),
            text_flags,
            is_subtitle=is_subtitle,
            container_rect=panel_rect,
        )
        background_rect = panel_rect if not is_subtitle else draw_rect.adjusted(-12, -6, 12, 6).intersected(panel_rect)
        painter.save()
        painter.setOpacity(max(0.0, min(alpha, 1.0)))
        painter.setClipRect(panel_rect)
        if not self._overlay_brush.isNull():
            painter.drawPixmap(background_rect, self._overlay_brush)
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, int(255 * alpha)))
            painter.drawRoundedRect(QRectF(background_rect), 6, 6)
        painter.restore()

        if item.visibility_state == VisibilityState.PENDING:
            painter.save()
            painter.setClipRect(panel_rect)
            border_pen = QPen(QColor(90, 220, 255, int(255 * alpha)))
            border_pen.setWidth(1)
            painter.setPen(border_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(background_rect), 6, 6)
            painter.restore()

        painter.save()
        painter.setClipRect(panel_rect)
        painter.setPen(QColor(text_color.red(), text_color.green(), text_color.blue(), int(255 * alpha)))
        painter.drawText(draw_rect, text_flags, item.translated_text)
        painter.restore()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        all_items = [*self._items, *self._persistent_items]
        if not all_items:
            painter.end()
            return

        subtitle_items: list[OverlayItem] = []
        normal_items: list[OverlayItem] = []
        for item in all_items:
            if self._is_subtitle_item(item):
                subtitle_items.append(item)
            else:
                normal_items.append(item)

        placed_rects: list[QRect] = []
        for item in sorted(normal_items, key=lambda current: (current.bbox.y, current.bbox.x)):
            alpha = self._alpha_multiplier(item)
            if alpha <= 0.01:
                continue

            local_rect = QRect(
                item.bbox.x,
                item.bbox.y,
                max(item.bbox.width, 1),
                max(item.bbox.height, 1),
            )
            font, panel_rect, text_rect, text_flags = self._fit_font_and_panel(
                item.translated_text,
                local_rect,
                is_subtitle=False,
                deep_ui=self._is_deep_ui_item(item),
            )
            resolved_panel = self._resolve_overlap(panel_rect, placed_rects)
            offset_x = resolved_panel.x() - panel_rect.x()
            offset_y = resolved_panel.y() - panel_rect.y()
            resolved_text = QRect(text_rect)
            resolved_text.translate(offset_x, offset_y)
            painter.setFont(font)
            self._draw_overlay_item(
                painter,
                item,
                resolved_panel,
                resolved_text,
                alpha,
                QColor(255, 251, 0),
            )
            placed_rects.append(QRect(resolved_panel))

        for item, resolved_panel, resolved_text, alpha, color in self._subtitle_stack_layout(subtitle_items):
            self._draw_overlay_item(
                painter,
                item,
                resolved_panel,
                resolved_text,
                alpha,
                color,
            )
        painter.end()
