from __future__ import annotations

from autotrans.config import AppConfig
from autotrans.services.translation import CTranslate2Translator


class _FakeSentencePiece:
    def encode(self, text: str, out_type=str):  # noqa: ANN001
        return text.split()

    def decode(self, tokens: list[str]) -> str:
        return " ".join(tokens)


class _FakeTranslationResult:
    def __init__(self, hypothesis: list[str]) -> None:
        self.hypotheses = [hypothesis]


class _FakeTranslatorBackend:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def translate_batch(self, source: list[list[str]], **kwargs: object) -> list[_FakeTranslationResult]:
        self.calls.append({"source": source, **kwargs})
        return [_FakeTranslationResult(tokens) for tokens in source]


def test_ctranslate2_uses_configured_decode_options() -> None:
    config = AppConfig()
    config.local_beam_size = 3
    config.local_repetition_penalty = 1.2
    config.local_no_repeat_ngram_size = 4
    config.local_max_decoding_length = 96

    translator = CTranslate2Translator.__new__(CTranslate2Translator)
    translator._config = config
    translator._source_sp = _FakeSentencePiece()
    translator._target_sp = _FakeSentencePiece()
    translator._translator = _FakeTranslatorBackend()

    translated = translator._translate_texts(["We have to go now"])

    assert translated == ["We have to go now"]
    assert translator._translator.calls == [
        {
            "source": [["We", "have", "to", "go", "now"]],
            "beam_size": 3,
            "repetition_penalty": 1.2,
            "no_repeat_ngram_size": 4,
            "max_decoding_length": 96,
            "return_scores": False,
        }
    ]
