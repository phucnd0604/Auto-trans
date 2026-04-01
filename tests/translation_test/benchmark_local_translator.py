from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
from pathlib import Path

from autotrans.config import AppConfig
from autotrans.models import OCRBox, QualityMode, Rect
from autotrans.services.translation import CTranslate2Translator


ROOT = Path(__file__).resolve().parent
DATASET_PATH = ROOT / "local_translator_dataset.json"
DEFAULT_JSON_OUTPUT = ROOT / "local_translator_benchmark.json"
DEFAULT_MARKDOWN_OUTPUT = ROOT / "local_translator_benchmark.md"

DEFAULT_SCENARIOS = [
    {
        "name": "quickmt-en-vi",
        "repo": "quickmt/quickmt-en-vi",
        "dir_name": "quickmt-en-vi",
        "enabled": True,
    },
    {
        "name": "opus-mt-en-vi-ctranslate2",
        "repo": "gaudi/opus-mt-en-vi-ctranslate2",
        "dir_name": "opus-mt-en-vi-ctranslate2",
        "enabled": True,
    },
    {
        "name": "nllb-200-distilled-600m",
        "repo": "gaudi/nllb-200-distilled-600M-ctranslate2",
        "dir_name": "nllb-200-distilled-600m-ctranslate2",
        "enabled": False,
    },
]


@dataclass(slots=True)
class DatasetItem:
    category: str
    source_text: str


@dataclass(slots=True)
class ScenarioConfig:
    name: str
    repo: str
    model_dir: Path
    enabled: bool = True


@dataclass(slots=True)
class TranslationSample:
    category: str
    source_text: str
    translated_text: str
    latency_ms: float


def _load_dataset(path: Path) -> list[DatasetItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [DatasetItem(category=str(item["category"]), source_text=str(item["source_text"])) for item in raw]


def _make_config(model_repo: str, model_dir: Path) -> AppConfig:
    config = AppConfig()
    config.local_model_enabled = True
    config.local_translator_backend = "ctranslate2"
    config.local_model_repo = model_repo
    config.local_model_dir = model_dir
    config.local_model_device = "cpu"
    config.local_model_compute_type = "int8"
    config.local_inter_threads = 1
    return config


def _make_ocr_box(item: DatasetItem, index: int) -> OCRBox:
    return OCRBox(
        id=f"sample-{index}",
        source_text=item.source_text,
        confidence=1.0,
        bbox=Rect(x=0, y=0, width=100, height=20),
    )


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def _translation_call(
    translator: CTranslate2Translator,
    items: list[OCRBox],
) -> tuple[list[str], float]:
    sink = io.StringIO()
    started = time.perf_counter()
    with redirect_stdout(sink), redirect_stderr(sink):
        results = translator.translate_batch(items, "en", "vi", QualityMode.BALANCED)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return [result.translated_text for result in results], elapsed_ms


def _run_scenario(scenario: ScenarioConfig, dataset: list[DatasetItem]) -> dict[str, object]:
    _safe_mkdir(scenario.model_dir)
    init_started = time.perf_counter()
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        translator = CTranslate2Translator(_make_config(scenario.repo, scenario.model_dir))
    cold_start_ms = (time.perf_counter() - init_started) * 1000.0

    single_latencies: list[float] = []
    samples: list[TranslationSample] = []
    per_category: dict[str, list[float]] = {}
    consistency_mismatches = 0

    for index, item in enumerate(dataset, start=1):
        box = _make_ocr_box(item, index)
        translated_texts, elapsed_ms = _translation_call(translator, [box])
        translated_text = translated_texts[0] if translated_texts else ""
        single_latencies.append(elapsed_ms)
        per_category.setdefault(item.category, []).append(elapsed_ms)
        samples.append(
            TranslationSample(
                category=item.category,
                source_text=item.source_text,
                translated_text=translated_text,
                latency_ms=elapsed_ms,
            )
        )

        repeated_texts, _ = _translation_call(translator, [box])
        if repeated_texts[:1] != [translated_text]:
            consistency_mismatches += 1

    batch_items = [_make_ocr_box(item, index) for index, item in enumerate(dataset[:4], start=1)]
    _, warm_small_batch_ms = _translation_call(translator, batch_items)

    throughput_items = [_make_ocr_box(item, index) for index, item in enumerate(dataset, start=1)]
    _, throughput_ms = _translation_call(translator, throughput_items)
    throughput_items_per_second = (len(throughput_items) / throughput_ms) * 1000.0 if throughput_ms > 0 else 0.0

    summary = {
        "dataset_size": len(dataset),
        "cold_start_ms": round(cold_start_ms, 2),
        "warm_single_avg_ms": round(statistics.mean(single_latencies), 2),
        "warm_single_p50_ms": round(statistics.median(single_latencies), 2),
        "warm_single_p95_ms": round(_percentile(single_latencies, 0.95), 2),
        "warm_small_batch_ms": round(warm_small_batch_ms, 2),
        "throughput_batch_ms": round(throughput_ms, 2),
        "throughput_items_per_second": round(throughput_items_per_second, 2),
        "consistency_mismatches": consistency_mismatches,
    }
    category_summary = {
        category: {
            "count": len(values),
            "avg_ms": round(statistics.mean(values), 2),
            "p95_ms": round(_percentile(values, 0.95), 2),
        }
        for category, values in sorted(per_category.items())
    }
    return {
        "scenario": scenario.name,
        "repo": scenario.repo,
        "model_dir": str(scenario.model_dir),
        "summary": summary,
        "category_summary": category_summary,
        "samples": [asdict(sample) for sample in samples],
    }


def _build_markdown(results: list[dict[str, object]]) -> str:
    lines = [
        "# Local Translator Benchmark",
        "",
        "## Summary",
        "",
        "| Scenario | Cold start (ms) | Single avg (ms) | Single p50 (ms) | Single p95 (ms) | Small batch (ms) | Throughput items/s | Mismatches |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        summary = result["summary"]
        lines.append(
            "| {scenario} | {cold_start_ms} | {warm_single_avg_ms} | {warm_single_p50_ms} | "
            "{warm_single_p95_ms} | {warm_small_batch_ms} | {throughput_items_per_second} | "
            "{consistency_mismatches} |".format(
                scenario=result["scenario"],
                cold_start_ms=summary["cold_start_ms"],
                warm_single_avg_ms=summary["warm_single_avg_ms"],
                warm_single_p50_ms=summary["warm_single_p50_ms"],
                warm_single_p95_ms=summary["warm_single_p95_ms"],
                warm_small_batch_ms=summary["warm_small_batch_ms"],
                throughput_items_per_second=summary["throughput_items_per_second"],
                consistency_mismatches=summary["consistency_mismatches"],
            )
        )

    lines.extend(["", "## Samples", ""])
    for result in results:
        lines.append(f"### {result['scenario']}")
        lines.append("")
        for sample in result["samples"]:
            lines.append(f"- [{sample['category']}] `{sample['source_text']}`")
            lines.append(f"  -> `{sample['translated_text']}` ({sample['latency_ms']:.2f}ms)")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark local CTranslate2 EN->VI translators.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DATASET_PATH,
        help="Path to benchmark dataset JSON.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_JSON_OUTPUT,
        help="Where to write the JSON benchmark report.",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=DEFAULT_MARKDOWN_OUTPUT,
        help="Where to write the Markdown benchmark summary.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Optional custom scenario in the form name=repo_id=model_dir.",
    )
    parser.add_argument(
        "--include-slow",
        action="store_true",
        help="Include the slower NLLB candidate in the run.",
    )
    return parser.parse_args()


def _default_scenarios(runtime_root: Path, include_slow: bool) -> list[ScenarioConfig]:
    scenarios: list[ScenarioConfig] = []
    for item in DEFAULT_SCENARIOS:
        if not item["enabled"] and not include_slow:
            continue
        scenarios.append(
            ScenarioConfig(
                name=str(item["name"]),
                repo=str(item["repo"]),
                model_dir=runtime_root / "models" / str(item["dir_name"]),
                enabled=bool(item["enabled"]) or include_slow,
            )
        )
    return scenarios


def _parse_custom_scenarios(raw_values: list[str]) -> list[ScenarioConfig]:
    scenarios: list[ScenarioConfig] = []
    for raw in raw_values:
        parts = raw.split("=", 2)
        if len(parts) != 3:
            raise SystemExit(f"Invalid --scenario value: {raw!r}. Expected name=repo_id=model_dir.")
        name, repo, model_dir = parts
        scenarios.append(ScenarioConfig(name=name, repo=repo, model_dir=Path(model_dir)))
    return scenarios


def main() -> None:
    args = _parse_args()
    dataset = _load_dataset(args.dataset)
    runtime_root = AppConfig().runtime_root_dir
    scenarios = _default_scenarios(runtime_root, include_slow=args.include_slow) + _parse_custom_scenarios(args.scenario)

    results: list[dict[str, object]] = []
    for scenario in scenarios:
        try:
            result = _run_scenario(scenario, dataset)
            summary = result["summary"]
            print(
                f"- {scenario.name}: cold_start={summary['cold_start_ms']}ms "
                f"single_avg={summary['warm_single_avg_ms']}ms "
                f"single_p95={summary['warm_single_p95_ms']}ms "
                f"throughput={summary['throughput_items_per_second']} items/s"
            )
            results.append(result)
        except Exception as exc:
            print(f"- {scenario.name}: skipped ({exc})")
            results.append(
                {
                    "scenario": scenario.name,
                    "repo": scenario.repo,
                    "model_dir": str(scenario.model_dir),
                    "error": str(exc),
                }
            )

    args.output_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_markdown.write_text(_build_markdown([result for result in results if "summary" in result]), encoding="utf-8")
    print(f"Wrote JSON report to {args.output_json}")
    print(f"Wrote Markdown report to {args.output_markdown}")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
