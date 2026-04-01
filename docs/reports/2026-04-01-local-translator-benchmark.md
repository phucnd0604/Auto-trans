# Local Translator Benchmark 2026-04-01

## Scope

This report benchmarks local EN->VI translators for the realtime path, isolated from OCR, to decide whether any `ctranslate2` model should replace `quickmt/quickmt-en-vi` without hurting runtime performance.

## Test Data

Source:
- `tests/translation_test/local_translator_dataset.json`

Dataset groups:
- `subtitle_dialogue`
- `quest_narrative`
- `ui_menu`

## Benchmark Script

Source:
- `tests/translation_test/benchmark_local_translator.py`

Measured metrics:
- cold start model init
- warm single-item latency
- p50/p95 for single-item requests
- small-batch latency
- throughput over the full dataset
- consistency across repeated runs

## Results

Sources:
- `tests/translation_test/local_translator_benchmark.json`
- `tests/translation_test/local_translator_benchmark.md`

Measured on this machine:
- `quickmt-en-vi`
  - cold start: `2563.88ms`
  - warm single avg: `54.87ms`
  - warm single p95: `83.52ms`
  - throughput: `42.01 items/s`
- `opus-mt-en-vi-ctranslate2`
  - cold start: `17450.28ms`
  - warm single avg: `351.3ms`
  - warm single p95: `476.91ms`
  - throughput: `8.95 items/s`

## Quality Notes

- `quickmt-en-vi` is still literal and somewhat mechanical, especially for dramatic dialogue.
- Even so, it mostly preserves core meaning on dialogue and quest text, and it stays fast enough for realtime.
- `opus-mt-en-vi-ctranslate2` does not meet the realtime bar:
  - much slower cold and warm latency
  - repeated-token / degenerate output on multiple samples
  - much worse UI/menu translations

## Conclusion

- No benchmarked candidate currently beats `quickmt/quickmt-en-vi` while preserving realtime performance.
- Current decision: keep `quickmt/quickmt-en-vi` as the default local realtime model.
- If style quality needs to improve without sacrificing latency, prefer:
  - deep mode Gemini or another style-aware rewrite path
  - manual rewrite flow for selected text
  - better glossary/term handling instead of replacing the realtime model
