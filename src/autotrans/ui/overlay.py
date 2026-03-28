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

    def _fit_font(self, text: str, rect: QRect, base_size: int) -> tuple[QFont, QRect, QRect, int]:
        inner_padding_x = 10
        inner_padding_y = 3
        single_line_flags = Qt.AlignCenter | Qt.TextSingleLine
        wrapped_flags = Qt.AlignCenter | Qt.TextWordWrap
        flags = single_line_flags if rect.height() <= 34 else wrapped_flags
        max_size = max(base_size, int(rect.height() * 1.15), 16)
        max_size = min(max_size, 44)
        min_size = 16

        candidate_rect = rect.adjusted(2, 1, -2, -1)
        if candidate_rect.width() <= 4 or candidate_rect.height() <= 4:
            candidate_rect = QRect(rect.x(), rect.y(), max(rect.width(), 1), max(rect.height(), 1))

        best_font = QFont("Segoe UI", min_size)
        best_font.setBold(True)
        best_bounds = QRect(0, 0, max(candidate_rect.width() - (inner_padding_x * 2), 1), max(candidate_rect.height() - (inner_padding_y * 2), 1))

        for font_size in range(max_size, min_size - 1, -1):
            font = QFont("Segoe UI", font_size)
            font.setBold(True)
            metrics = QFontMetrics(font)
            bounds = metrics.boundingRect(candidate_rect, flags, text)
            if bounds.width() <= candidate_rect.width() and bounds.height() <= candidate_rect.height():
                best_font = font
                best_bounds = bounds
                break
            best_font = font
            best_bounds = bounds

        text_width = max(best_bounds.width(), 1)
        text_height = max(best_bounds.height(), 1)
        panel_width = max(text_width + (inner_padding_x * 2), rect.width())
        panel_height = max(text_height + (inner_padding_y * 2), rect.height())
        panel_x = rect.x() + ((rect.width() - panel_width) // 2)
        panel_y = rect.y() + ((rect.height() - panel_height) // 2)
        panel_rect = QRect(panel_x, panel_y, max(panel_width, 1), max(panel_height, 1))
        text_rect = panel_rect.adjusted(inner_padding_x, inner_padding_y, -inner_padding_x, -inner_padding_y)
        if text_rect.width() <= 2 or text_rect.height() <= 2:
            text_rect = QRect(panel_rect)

        return best_font, panel_rect, text_rect, flags

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        if not self._items:
            painter.end()
            return

        for item in self._items:
            local_rect = QRect(
                item.bbox.x,
                item.bbox.y,
                max(item.bbox.width, 1),
                max(item.bbox.height, 1),
            )
            font, panel_rect, text_rect, text_flags = self._fit_font(item.translated_text, local_rect, item.style.font_size)
            painter.setFont(font)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, int(255 * item.style.background_opacity)))
            painter.drawRect(QRectF(panel_rect))

            painter.setPen(QColor(245, 210, 90))
            painter.drawText(QRect(text_rect), text_flags, item.translated_text)
        painter.end()

