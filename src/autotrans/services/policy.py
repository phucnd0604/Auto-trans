from __future__ import annotations

from dataclasses import dataclass

from autotrans.models import OCRBox, QualityMode


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

        if not network_state or not cost_budget:
            return ProviderDecision(provider="local", reason="no-cloud-allowed")

        return ProviderDecision(provider="cloud", reason="ai-first")
