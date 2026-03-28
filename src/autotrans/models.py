from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


class QualityMode(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    HIGH_QUALITY = "high_quality"


@dataclass(slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    def iou(self, other: "Rect") -> float:
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        width = max(0, right - left)
        height = max(0, bottom - top)
        intersection = width * height
        union = self.area() + other.area() - intersection
        if union <= 0:
            return 0.0
        return intersection / union


@dataclass(slots=True)
class Frame:
    image: np.ndarray
    timestamp: float
    window_rect: Rect
    scale: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OCRBox:
    id: str
    source_text: str
    confidence: float
    bbox: Rect
    language_hint: str = "unknown"
    line_id: str = ""


@dataclass(slots=True)
class TranslationRequest:
    items: list[OCRBox]
    source_lang: str
    target_lang: str
    mode: QualityMode


@dataclass(slots=True)
class TranslationResult:
    source_text: str
    translated_text: str
    provider: str
    latency_ms: float


class VisibilityState(str, Enum):
    HIDDEN = "hidden"
    VISIBLE = "visible"
    PENDING = "pending"


@dataclass(slots=True)
class OverlayStyle:
    font_size: int = 18
    background_opacity: float = 0.72
    padding: int = 4


@dataclass(slots=True)
class OverlayItem:
    bbox: Rect
    translated_text: str
    style: OverlayStyle
    visibility_state: VisibilityState = VisibilityState.VISIBLE
    source_text: str = ""
    tracking_key: str = ""


@dataclass(slots=True)
class PipelineStats:
    capture_fps: float = 0.0
    ocr_fps: float = 0.0
    translation_latency_ms: float = 0.0
    box_count: int = 0
    cache_hits: int = 0
