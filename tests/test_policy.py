from autotrans.models import OCRBox, QualityMode, Rect
from autotrans.services.policy import ProviderPolicy


def make_box(text: str, confidence: float = 0.95, language_hint: str = "en") -> OCRBox:
    return OCRBox(
        id="",
        source_text=text,
        confidence=confidence,
        bbox=Rect(0, 0, 100, 20),
        language_hint=language_hint,
        line_id="line-0",
    )


def test_ai_first_prefers_cloud_when_available() -> None:
    policy = ProviderPolicy()
    decision = policy.select([make_box("Quest accepted")], QualityMode.FAST, network_state=True)
    assert decision.provider == "cloud"


def test_falls_back_to_local_when_cloud_unavailable() -> None:
    policy = ProviderPolicy()
    decision = policy.select(
        [make_box("???????", confidence=0.8, language_hint="jp")],
        QualityMode.HIGH_QUALITY,
        network_state=False,
    )
    assert decision.provider == "local"
