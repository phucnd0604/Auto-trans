from __future__ import annotations

from dataclasses import dataclass

from autotrans.models import OCRBox, QualityMode
from autotrans.utils.text import normalize_text


@dataclass(slots=True)
class ProviderDecision:
    provider: str
    reason: str


class ProviderPolicy:
    def __init__(
        self,
        cloud_timeout_ms: int = 1200,
        local_max_chars_balanced: int = 72,
    ) -> None:
        self.cloud_timeout_ms = cloud_timeout_ms
        self.local_max_chars_balanced = local_max_chars_balanced

    def select(
        self,
        text_items: list[OCRBox],
        mode: QualityMode,
        network_state: bool,
        cost_budget: bool = True,
    ) -> ProviderDecision:
        if not text_items:
            return ProviderDecision(provider="local", reason="empty-batch")

        longest = max(len(normalize_text(item.source_text)) for item in text_items)
        avg_conf = sum(item.confidence for item in text_items) / len(text_items)
        mostly_jp = any(item.language_hint.lower().startswith("jp") for item in text_items)

        if not network_state or not cost_budget:
            return ProviderDecision(provider="local", reason="no-cloud-allowed")

        if mode == QualityMode.FAST:
            return ProviderDecision(provider="local", reason="fast-mode")

        if mode == QualityMode.HIGH_QUALITY and (mostly_jp or longest > 28):
            return ProviderDecision(provider="cloud", reason="hq-contextual-text")

        if avg_conf < 0.75 and longest > 20:
            return ProviderDecision(provider="cloud", reason="low-confidence")

        if longest <= self.local_max_chars_balanced:
            return ProviderDecision(provider="local", reason="short-text")

        return ProviderDecision(provider="cloud", reason="long-text")
