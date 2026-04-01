# OCR Benchmark And Deepmode Guide

## Purpose

This guide documents the repeatable commands used to validate OCR behavior after runtime changes.

## Environment

Run commands from the repo root:

```bash
cd /Users/phucnd/Documents/Auto-trans/Auto-trans
```

Use the project venv:

```bash
./.venv/bin/python --version
```

Recommended environment variables:

```bash
export PYTHONPATH=src
export PADDLE_PDX_CACHE_HOME=/Users/phucnd/Documents/Auto-trans/Auto-trans/.runtime/paddlex-cache
```

Notes:
- If local Paddle model cache is missing and network is available, Paddle can download required models automatically.
- If network is blocked, tests can only use models already present in `PADDLE_PDX_CACHE_HOME`.

## 1. Realtime OCR Benchmark

Command:

```bash
PYTHONPATH=src \
PADDLE_PDX_CACHE_HOME=/Users/phucnd/Documents/Auto-trans/Auto-trans/.runtime/paddlex-cache \
./.venv/bin/python tests/ocr_test/benchmark_subtitle_runtime.py
```

What it does:
- Runs OCR on 11 subtitle sample images in `tests/ocr_test/`.
- Benchmarks the current Paddle-only runtime path up to subtitle selection output.
- Writes a JSON report to `tests/ocr_test/subtitle_runtime_benchmark.json`.

Current scenarios:
- `runtime-default`
- `runtime-no-crop`
- `runtime-det-640`
- `runtime-latin-rec`

## 2. Deepmode OCR Preview

Command:

```bash
PYTHONPATH=src \
PADDLE_PDX_CACHE_HOME=/Users/phucnd/Documents/Auto-trans/Auto-trans/.runtime/paddlex-cache \
./.venv/bin/python tests/sample-screenshot/render_deepmode_ocr_preview.py
```

What it does:
- Runs deep mode OCR on `quest1.png` and `quest2.png`.
- Produces grouped OCR boxes using Paddle layout grouping.
- Writes preview PNG and JSON files next to the sample screenshots.

Expected output files:
- `tests/sample-screenshot/quest1.deepmode-paddleocr_auto-ocr-boxes.png`
- `tests/sample-screenshot/quest1.deepmode-paddleocr_auto-ocr-boxes.json`
- `tests/sample-screenshot/quest2.deepmode-paddleocr_auto-ocr-boxes.png`
- `tests/sample-screenshot/quest2.deepmode-paddleocr_auto-ocr-boxes.json`

## 3. Deepmode Runtime Preview

Command:

```bash
PYTHONPATH=src \
PADDLE_PDX_CACHE_HOME=/Users/phucnd/Documents/Auto-trans/Auto-trans/.runtime/paddlex-cache \
AUTOTRANS_TRANSLATOR_BACKEND=word \
./.venv/bin/python tests/sample-screenshot/render_deepmode_runtime_preview.py
```

What it does:
- Exercises the deep mode pipeline more closely to runtime.
- Builds pending/final overlay preview images for the sample quest screenshots.

## 4. Quick Compile Check

Command:

```bash
PYTHONPATH=src ./.venv/bin/python -m py_compile \
  src/autotrans/app.py \
  src/autotrans/config.py \
  src/autotrans/services/ocr.py \
  src/autotrans/ui/settings_dialog.py \
  tests/ocr_test/benchmark_subtitle_runtime.py \
  tests/sample-screenshot/render_deepmode_ocr_preview.py \
  tests/test_deep_mode.py \
  tests/test_ocr_runtime_providers.py
```

## 5. When To Rerun

Rerun the benchmark and deepmode preview after:
- changing OCR model names
- changing detection size or crop behavior
- changing deepmode layout grouping
- changing Paddle dependency versions
- cleaning or replacing the Paddle local cache
