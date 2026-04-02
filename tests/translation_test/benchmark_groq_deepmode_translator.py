from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from autotrans.config import AppConfig
from autotrans.models import OCRBox, QualityMode, Rect
from autotrans.services.translation import GroqTranslator


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
DEFAULT_ENV_PATH = REPO_ROOT / ".env"
DEFAULT_JSON_OUTPUT = ROOT / "groq_deepmode_benchmark.json"
DEFAULT_MARKDOWN_OUTPUT = ROOT / "groq_deepmode_benchmark.md"
DEFAULT_MODEL = "moonshotai/kimi-k2-instruct"


@dataclass(slots=True)
class BenchmarkParagraph:
    name: str
    source_text: str


@dataclass(slots=True)
class ParagraphRun:
    name: str
    source_text: str
    translated_text: str
    word_count: int
    latency_ms: float


SAMPLES: list[BenchmarkParagraph] = [
    BenchmarkParagraph(
        name="camp-briefing",
        source_text=(
            "The captain gathered the team beside the fire and pointed toward the broken bridge "
            "that cut the village off from the north road. He explained that the storm had not only "
            "damaged the planks, but also washed away the supply crates that the hunters had been "
            "expecting. Everyone listened quietly while the wind rattled the tents and the horses "
            "shifted in place. The scout offered to go first at sunrise, and the healer suggested "
            "packing rope, dried food, and spare lantern oil before the path disappeared in the fog."
        ),
    ),
    BenchmarkParagraph(
        name="ruined-library",
        source_text=(
            "Inside the ruined library, dust floated through the sunbeams like tiny sparks, and each "
            "step stirred a smell of old paper and wet stone. The scholar moved carefully between "
            "the fallen shelves, searching for a map that might explain the sealed tower beyond the "
            "courtyard. When she found a cracked tablet covered in faded notes, she called the others "
            "over and traced the symbols with a gloved finger. The markings mentioned a hidden stair, "
            "a key carved from bone, and a warning that the tower only opened when the bells stopped."
        ),
    ),
    BenchmarkParagraph(
        name="market-errand",
        source_text=(
            "The market district was loud enough to swallow every private thought, yet the merchant "
            "kept smiling as if the noise were part of the bargain. He weighed apples, silk thread, "
            "and metal charms on the same brass scale, then told the traveler that the price would "
            "change again after noon. A pair of children raced past with a stolen bun, and a guard "
            "pretended not to notice because the bakery owner had already promised him a discount. "
            "By the time the traveler counted the coins twice, the merchant had already wrapped the "
            "goods and asked whether the road to the harbor was still safe."
        ),
    ),
    BenchmarkParagraph(
        name="night-escape",
        source_text=(
            "When the lanterns went dark, the prisoner slipped the latch with a bent spoon and eased "
            "the door open just enough to hear the courtyard. The sentries were laughing at the far "
            "gate, distracted by a dice game and a bottle passed between them too quickly. She moved "
            "along the wall, counting the steps between each shadow, and paused whenever a hawk cried "
            "from the roofline. The plan had been simple on paper, but every breath felt heavier once "
            "she saw the horses already saddled by the stable and the thin line of moonlight across "
            "the escape route."
        ),
    ),
]


def _word_count(text: str) -> int:
    return len([word for word in text.split() if word.strip()])


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _ensure_env_loaded(env_path: Path) -> None:
    if os.environ.get("AUTOTRANS_DEEP_TRANSLATION_API_KEY") or os.environ.get("GROQ_API_KEY"):
        return
    env_values = _load_env_file(env_path)
    for key in ("AUTOTRANS_DEEP_TRANSLATION_API_KEY", "GROQ_API_KEY"):
        value = env_values.get(key)
        if value and not os.environ.get(key):
            os.environ[key] = value


def _resolve_api_key() -> str:
    for key in ("AUTOTRANS_DEEP_TRANSLATION_API_KEY", "GROQ_API_KEY"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    raise RuntimeError(
        "Missing Groq API key. Set AUTOTRANS_DEEP_TRANSLATION_API_KEY or GROQ_API_KEY in .env or environment."
    )


def _make_config(model: str, api_key: str, timeout_ms: int, verbose: bool) -> AppConfig:
    config = AppConfig()
    config.deep_translation_provider = "groq"
    config.deep_translation_model = model
    config.deep_translation_api_key = api_key
    config.deep_translation_timeout_ms = timeout_ms
    config.translation_log_enabled = verbose
    return config


def _make_translator(config: AppConfig) -> GroqTranslator:
    return GroqTranslator(
        model=config.deep_translation_model,
        api_key=config.deep_translation_api_key,
        config=config,
        timeout_s=config.deep_translation_timeout_ms / 1000.0,
        verbose=config.translation_log_enabled,
        max_logged_items=4,
    )


def _make_box(paragraph: BenchmarkParagraph) -> OCRBox:
    return OCRBox(
        id=paragraph.name,
        source_text=paragraph.source_text,
        confidence=1.0,
        bbox=Rect(x=0, y=0, width=1200, height=220),
    )


def _run_paragraph(translator: GroqTranslator, paragraph: BenchmarkParagraph, repeat: int) -> ParagraphRun:
    box = _make_box(paragraph)
    latencies: list[float] = []
    translated_text = ""
    for _ in range(max(1, repeat)):
        started = time.perf_counter()
        results = translator.translate_screen_blocks([box], "en", "vi")
        latencies.append((time.perf_counter() - started) * 1000.0)
        if results:
            translated_text = results[0].translated_text
    return ParagraphRun(
        name=paragraph.name,
        source_text=paragraph.source_text,
        translated_text=translated_text,
        word_count=_word_count(paragraph.source_text),
        latency_ms=round(statistics.mean(latencies), 2),
    )


def _build_markdown(model: str, env_path: Path, runs: list[ParagraphRun]) -> str:
    latencies = [run.latency_ms for run in runs]
    lines = [
        "# Groq Deep Mode Benchmark",
        "",
        f"- Model: `{model}`",
        f"- Env file: `{env_path}`",
        f"- Paragraphs: `{len(runs)}`",
        f"- Avg latency: `{statistics.mean(latencies):.2f}ms`" if latencies else "- Avg latency: `0.00ms`",
        f"- Median latency: `{statistics.median(latencies):.2f}ms`" if latencies else "- Median latency: `0.00ms`",
        "",
        "## Results",
        "",
        "| Paragraph | Words | Latency (ms) |",
        "| --- | ---: | ---: |",
    ]
    for run in runs:
        lines.append(f"| {run.name} | {run.word_count} | {run.latency_ms:.2f} |")
    lines.extend(
        [
            "",
            "## Samples",
            "",
        ]
    )
    for run in runs:
        lines.append(f"### {run.name}")
        lines.append("")
        lines.append(f"- Source words: {run.word_count}")
        lines.append(f"- Latency: {run.latency_ms:.2f}ms")
        lines.append("")
        lines.append("> Source")
        lines.append(f"> {run.source_text}")
        lines.append("")
        lines.append("> Translation")
        for line in run.translated_text.splitlines() or [""]:
            lines.append(f"> {line}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Groq deep translation with English paragraphs.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help="Path to .env containing GROQ_API_KEY or AUTOTRANS_DEEP_TRANSLATION_API_KEY.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Groq model name to benchmark.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=90000,
        help="Request timeout for the Groq client, in milliseconds.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="How many times to translate each paragraph before averaging latency.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_JSON_OUTPUT,
        help="Where to write the JSON report.",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=DEFAULT_MARKDOWN_OUTPUT,
        help="Where to write the Markdown report.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose translator logs.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _ensure_env_loaded(args.env_file)
    api_key = _resolve_api_key()
    config = _make_config(args.model, api_key, args.timeout_ms, args.verbose)
    translator = _make_translator(config)

    runs = [_run_paragraph(translator, sample, args.repeat) for sample in SAMPLES]
    total_latency = sum(run.latency_ms for run in runs)
    summary = {
        "model": args.model,
        "env_file": str(args.env_file),
        "paragraph_count": len(runs),
        "repeat": max(1, args.repeat),
        "avg_latency_ms": round(statistics.mean(run.latency_ms for run in runs), 2) if runs else 0.0,
        "median_latency_ms": round(statistics.median(run.latency_ms for run in runs), 2) if runs else 0.0,
        "total_latency_ms": round(total_latency, 2),
        "word_count_avg": round(statistics.mean(run.word_count for run in runs), 2) if runs else 0.0,
    }

    payload = {
        "summary": summary,
        "runs": [asdict(run) for run in runs],
    }

    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_markdown.write_text(_build_markdown(args.model, args.env_file, runs), encoding="utf-8")

    print(
        f"[groq] model={args.model} avg={summary['avg_latency_ms']}ms "
        f"median={summary['median_latency_ms']}ms total={summary['total_latency_ms']}ms"
    )
    for run in runs:
        preview = " ".join(run.translated_text.split())
        print(f"[{run.name}] {run.latency_ms:.2f}ms | {preview[:240]}")
    print(f"Wrote JSON report to {args.output_json}")
    print(f"Wrote Markdown report to {args.output_markdown}")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
