from autotrans.models import OCRBox, QualityMode, Rect, TranslationResult
from autotrans.services.translation import HybridLocalTranslator, OpenAITranslator


class FakeDelegate:
    name = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def translate_batch(self, items, source_lang, target_lang, mode):
        self.calls += 1
        return [
            TranslationResult(
                source_text=item.source_text,
                translated_text=f"VI:{item.source_text}",
                provider=self.name,
                latency_ms=5.0,
            )
            for item in items
        ]


def make_item(text: str) -> OCRBox:
    return OCRBox(
        id="",
        source_text=text,
        confidence=0.99,
        bbox=Rect(0, 0, 100, 20),
        language_hint="en",
        line_id="line-0",
    )


def test_hybrid_local_translator_uses_glossary_for_glued_ui_text() -> None:
    translator = HybridLocalTranslator(delegate=None)

    result = translator.translate_batch(
        [make_item("SAVEGAME"), make_item("RESTARTFROMLASTCHECKPOINT")],
        "en",
        "vi",
        QualityMode.BALANCED,
    )

    assert result[0].translated_text == "Luu game"
    assert result[1].translated_text == "Choi lai tu diem luu gan nhat"


def test_hybrid_local_translator_uses_delegate_for_sentences() -> None:
    delegate = FakeDelegate()
    translator = HybridLocalTranslator(delegate=delegate)

    result = translator.translate_batch(
        [make_item("Yuna and Taka reached Komatsu Forge safely.")],
        "en",
        "vi",
        QualityMode.BALANCED,
    )

    assert delegate.calls == 1
    assert result[0].translated_text == "VI:Yuna and Taka reached Komatsu Forge safely."


def test_openai_translator_sanitizes_numbering_and_quotes() -> None:
    assert OpenAITranslator._sanitize_line('1. "Restart from last checkpoint"') == "Restart from last checkpoint"
    assert OpenAITranslator._sanitize_line("- 'Save game'") == "Save game"
