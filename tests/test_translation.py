from autotrans.models import OCRBox, QualityMode, Rect
from autotrans.services.translation import OpenAITranslator, WordByWordTranslator


def make_item(text: str) -> OCRBox:
    return OCRBox(
        id="",
        source_text=text,
        confidence=0.99,
        bbox=Rect(0, 0, 100, 20),
        language_hint="en",
        line_id="line-0",
    )


def test_word_by_word_translator_handles_menu_text() -> None:
    translator = WordByWordTranslator()

    result = translator.translate_batch(
        [make_item("SAVE GAME"), make_item("RESTART FROM LAST CHECKPOINT")],
        "en",
        "vi",
        QualityMode.BALANCED,
    )

    assert result[0].translated_text == "luu game"
    assert result[1].translated_text == "khoi dong lai tu cuoi diem kiem soat"


def test_word_by_word_translator_handles_objectives() -> None:
    translator = WordByWordTranslator()

    result = translator.translate_batch(
        [make_item("Follow Yuna"), make_item("Do not raise the alarm")],
        "en",
        "vi",
        QualityMode.BALANCED,
    )

    assert result[0].translated_text == "theo Yuna"
    assert result[1].translated_text == "khong gay bao dong"


def test_openai_translator_sanitizes_numbering_and_quotes() -> None:
    assert OpenAITranslator._sanitize_line('1. "Restart from last checkpoint"') == "Restart from last checkpoint"
    assert OpenAITranslator._sanitize_line("- 'Save game'") == "Save game"
