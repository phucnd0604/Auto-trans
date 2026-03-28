from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt, QRect, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QTextOption
from PySide6.QtWidgets import QWidget

from autotrans.models import OverlayItem, Rect
from autotrans.utils.text import normalize_text


class OverlayWindow(QWidget):
    def __init__(self, ttl_seconds: float = 1.5) -> None:
        super().__init__()
        self._items: list[OverlayItem] = []
        self._window_rect = Rect(0, 0, 1, 1)
        self._ttl_seconds = ttl_seconds
        self._live_items: dict[str, tuple[OverlayItem, float]] = {}
        self._prune_timer = QTimer(self)
        self._prune_timer.setInterval(250)
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
        bbox = item.bbox
        text = normalize_text(item.source_text or item.translated_text)
        return f"{bbox.x}:{bbox.y}:{bbox.width}:{bbox.height}:{text}"

    def _prune_expired_items(self) -> None:
        now = time.monotonic()
        changed = False
        for key, (_, last_seen) in list(self._live_items.items()):
            if now - last_seen > self._ttl_seconds:
                del self._live_items[key]
                changed = True
        if changed:
            self._items = [item for item, _ in self._live_items.values()]
            self.update(self.rect())

    def set_overlay_items(self, items: list[OverlayItem]) -> None:
        now = time.monotonic()
        for item in items:
            self._live_items[self._item_key(item)] = (item, now)
        self._prune_expired_items()
        self._items = [item for item, _ in self._live_items.values()]
        self.update(self.rect())

    def _fit_font(self, text: str, rect: QRect, base_size: int) -> tuple[QFont, QRect, int]:
        padding_x = 2
        padding_y = 1
        draw_rect = rect.adjusted(padding_x, padding_y, -padding_x, -padding_y)
        if draw_rect.width() <= 4 or draw_rect.height() <= 4:
            draw_rect = QRect(rect.x(), rect.y(), max(rect.width(), 1), max(rect.height(), 1))

        single_line_flags = Qt.AlignCenter | Qt.TextSingleLine
        wrapped_flags = Qt.AlignCenter | Qt.TextWordWrap
        flags = single_line_flags if rect.height() <= 34 else wrapped_flags
        max_size = max(base_size, int(rect.height() * 1.15), 12)
        max_size = min(max_size, 44)
        best_font = QFont("Segoe UI", 6)

        for font_size in range(max_size, 5, -1):
            font = QFont("Segoe UI", font_size)
            metrics = QFontMetrics(font)
            bounds = metrics.boundingRect(draw_rect, flags, text)
            if bounds.width() <= draw_rect.width() and bounds.height() <= draw_rect.height():
                best_font = font
                break

        return best_font, draw_rect, flags

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
            font, draw_rect, text_flags = self._fit_font(item.translated_text, local_rect, item.style.font_size)
            painter.setFont(font)

            panel_rect = QRectF(local_rect)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, int(255 * item.style.background_opacity)))
            painter.drawRect(panel_rect)

            painter.setPen(QColor(245, 210, 90))
            painter.drawText(QRect(draw_rect), text_flags, item.translated_text)
        painter.end()

