from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


BENCHMARK_MODULE_PATH = Path(__file__).resolve().parent / "translation_test" / "benchmark_groq_deepmode_translator.py"
_SPEC = importlib.util.spec_from_file_location("benchmark_groq_deepmode_translator", BENCHMARK_MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load benchmark module from {BENCHMARK_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault(_SPEC.name, _MODULE)
_SPEC.loader.exec_module(_MODULE)


def test_groq_benchmark_samples_are_roughly_100_words() -> None:
    word_counts = [_MODULE._word_count(sample.source_text) for sample in _MODULE.SAMPLES]
    assert len(word_counts) == 4
    assert all(80 <= count <= 120 for count in word_counts)


def test_groq_benchmark_env_loader_supports_export_and_quotes(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        '\n'.join(
            [
                'export GROQ_API_KEY="test-groq-key"',
                "AUTOTRANS_DEEP_TRANSLATION_API_KEY='override-key'",
            ]
        ),
        encoding="utf-8",
    )

    values = _MODULE._load_env_file(env_path)

    assert values["GROQ_API_KEY"] == "test-groq-key"
    assert values["AUTOTRANS_DEEP_TRANSLATION_API_KEY"] == "override-key"


def test_groq_benchmark_markdown_includes_samples() -> None:
    runs = [
        _MODULE.ParagraphRun(
            name="camp-briefing",
            source_text="We have to go now.",
            translated_text="Chung ta phai di ngay.",
            word_count=5,
            latency_ms=123.45,
        )
    ]

    markdown = _MODULE._build_markdown("moonshotai/kimi-k2-instruct", Path(".env"), runs)

    assert "# Groq Deep Mode Benchmark" in markdown
    assert "moonshotai/kimi-k2-instruct" in markdown
    assert "camp-briefing" in markdown
    assert "`We have to go now.`" not in markdown
    assert "### camp-briefing" in markdown


def test_groq_benchmark_json_payload_shape() -> None:
    payload = {
        "summary": {
            "model": "moonshotai/kimi-k2-instruct",
            "env_file": ".env",
            "paragraph_count": 1,
            "repeat": 1,
            "avg_latency_ms": 100.0,
            "median_latency_ms": 100.0,
            "total_latency_ms": 100.0,
            "word_count_avg": 100.0,
        },
        "runs": [
            {
                "name": "camp-briefing",
                "source_text": "We have to go now.",
                "translated_text": "Chung ta phai di ngay.",
                "word_count": 5,
                "latency_ms": 123.45,
            }
        ],
    }

    encoded = json.dumps(payload, ensure_ascii=False)
    decoded = json.loads(encoded)

    assert decoded["summary"]["model"] == "moonshotai/kimi-k2-instruct"
    assert decoded["runs"][0]["name"] == "camp-briefing"
