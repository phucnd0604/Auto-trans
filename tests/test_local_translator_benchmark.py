from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from autotrans.services.translation import CTranslate2Translator


BENCHMARK_MODULE_PATH = Path(__file__).resolve().parent / "translation_test" / "benchmark_local_translator.py"
_SPEC = importlib.util.spec_from_file_location("benchmark_local_translator", BENCHMARK_MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load benchmark module from {BENCHMARK_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault(_SPEC.name, _MODULE)
_SPEC.loader.exec_module(_MODULE)


def test_safe_log_text_escapes_unencodable_characters(monkeypatch) -> None:
    class _Stdout:
        encoding = "cp1252"

    monkeypatch.setattr("sys.stdout", _Stdout())
    escaped = CTranslate2Translator._safe_log_text("Chúng ta phải đi")
    assert "\\u00fa" not in escaped
    assert "\\u" in escaped


def test_benchmark_dataset_contains_expected_categories() -> None:
    dataset = json.loads((_MODULE.DATASET_PATH).read_text(encoding="utf-8"))
    categories = {str(item["category"]) for item in dataset}
    assert categories == {"subtitle_dialogue", "quest_narrative", "ui_menu"}
    assert len(dataset) >= 9


def test_markdown_builder_includes_summary_and_samples() -> None:
    markdown = _MODULE._build_markdown(
        [
            {
                "scenario": "quickmt-en-vi",
                "summary": {
                    "cold_start_ms": 100.0,
                    "warm_single_avg_ms": 10.0,
                    "warm_single_p50_ms": 9.0,
                    "warm_single_p95_ms": 12.0,
                    "warm_small_batch_ms": 20.0,
                    "throughput_items_per_second": 50.0,
                    "consistency_mismatches": 0,
                },
                "samples": [
                    {
                        "category": "subtitle_dialogue",
                        "source_text": "We have to go.",
                        "translated_text": "Chúng ta phải đi.",
                        "latency_ms": 9.5,
                    }
                ],
            }
        ]
    )
    assert "| Scenario | Cold start (ms) |" in markdown
    assert "### quickmt-en-vi" in markdown
    assert "`We have to go.`" in markdown
