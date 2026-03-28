from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt, QRect, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from autotrans.models import OverlayItem, Rect
from autotrans.utils.text import normalize_text


class OverlayWindow(QWidget):
    def __init__(self, ttl_seconds: float = 1.5, overlay_fps: int = 30) -> None:
        super().__init__()
        self._items: list[OverlayItem] = []
        self._window_rect = Rect(0, 0, 1, 1)
        self._ttl_seconds = ttl_seconds
        self._live_items: dict[str, tuple[OverlayItem, float, float]] = {}
        self._prune_timer = QTimer(self)
        prune_interval_ms = max(int(round(1000.0 / max(overlay_fps, 1))), 33)
        self._prune_timer.setInterval(prune_interval_ms)
        self._prune_timer.timeout.connect(self._prune_expired_items)
        self._prune_timer.start()
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
        for key, (_, last_seen, linger_seconds) in list(self._live_items.items()):
            ttl_seconds = linger_seconds if linger_seconds > 0 else self._ttl_seconds
            if now - last_seen > ttl_seconds:
                del self._live_items[key]
                changed = True
        if changed:
            self._items = [item for item, _, _ in self._live_items.values()]
            self.update(self.rect())

    def set_overlay_items(self, items: list[OverlayItem]) -> None:
        now = time.monotonic()
        for item in items:
            linger_seconds = item.linger_seconds if item.linger_seconds > 0 else self._ttl_seconds
            self._live_items[self._item_key(item)] = (item, now, linger_seconds)
        self._prune_expired_items()
        self._items = [item for item, _, _ in self._live_items.values()]
        self.update(self.rect())

    def _fixed_font(self) -> QFont:
        return QFont("Segoe UI", 16)

    def _layout_panel(self, text: str, rect: QRect) -> tuple[QFont, QRect, QRect, int]:
        inner_padding_x = 10
        inner_padding_y = 3
        font = self._fixed_font()
        metrics = QFontMetrics(font)

        normalized = normalize_text(text)
        is_paragraph = "\n" in text or rect.height() > 40 or len(normalized) > 48
        single_line_flags = Qt.AlignCenter | Qt.TextSingleLine
        wrapped_flags = Qt.AlignCenter | Qt.TextWordWrap
        flags = wrapped_flags if is_paragraph else single_line_flags

        if is_paragraph:
            target_width = max(rect.width() // 2, 220)
            target_width = max(target_width, min(rect.width(), 420))
            target_width = min(target_width, max(self.width() - 20, 1))
            measure_rect = QRect(0, 0, max(target_width - (inner_padding_x * 2), 1), max(self.height(), 60))
            bounds = metrics.boundingRect(measure_rect, flags, text)
            panel_width = min(bounds.width() + (inner_padding_x * 2), max(self.width() - 8, 1))
            panel_height = min(bounds.height() + (inner_padding_y * 2), max(self.height() - 8, 1))
        else:
            bounds = metrics.boundingRect(text)
            panel_width = min(bounds.width() + (inner_padding_x * 2), max(self.width() - 8, 1))
            panel_height = min(max(rect.height(), bounds.height() + (inner_padding_y * 2)), max(self.height() - 8, 1))

        panel_x = rect.x() + ((rect.width() - panel_width) // 2)
        panel_y = rect.y() + ((rect.height() - panel_height) // 2)
        panel_x = max(0, min(panel_x, max(self.width() - panel_width, 0)))
        panel_y = max(0, min(panel_y, max(self.height() - panel_height, 0)))

        panel_rect = QRect(panel_x, panel_y, max(panel_width, 1), max(panel_height, 1))
        text_rect = panel_rect.adjusted(inner_padding_x, inner_padding_y, -inner_padding_x, -inner_padding_y)
        if text_rect.width() <= 2 or text_rect.height() <= 2:
            text_rect = QRect(panel_rect)
        return font, panel_rect, text_rect, flags

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

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        if not self._items:
            painter.end()
            return

        placed_rects: list[QRect] = []
        for item in sorted(self._items, key=lambda current: (current.bbox.y, current.bbox.x)):
            local_rect = QRect(
                item.bbox.x,
                item.bbox.y,
                max(item.bbox.width, 1),
                max(item.bbox.height, 1),
            )
            font, panel_rect, text_rect, text_flags = self._layout_panel(item.translated_text, local_rect)
            resolved_panel = self._resolve_overlap(panel_rect, placed_rects)
            offset_x = resolved_panel.x() - panel_rect.x()
            offset_y = resolved_panel.y() - panel_rect.y()
            resolved_text = QRect(text_rect)
            resolved_text.translate(offset_x, offset_y)

            painter.setFont(font)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, int(255 * item.style.background_opacity)))
            painter.drawRect(QRectF(resolved_panel))

            painter.setPen(QColor(245, 210, 90))
            painter.drawText(QRect(resolved_text), text_flags, item.translated_text)
            placed_rects.append(QRect(resolved_panel))
        painter.end()
