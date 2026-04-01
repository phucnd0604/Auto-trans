# PaddleOCR Only OCR Report

## Scope

This report summarizes the current `PaddleOCR`-only OCR state after removing `RapidOCR` from the app and test workspace.

## Implemented Changes

- Removed `RapidOCRProvider` and all runtime selection logic for `rapidocr`.
- Standardized both realtime OCR and deep mode OCR on `PaddleOCR`.
- Kept deep mode layout analysis on Paddle layout detection using `PP-DocLayout-S`.
- Simplified startup settings so `OCR Provider` is fixed to `paddleocr`.
- Removed `rapidocr_onnxruntime` from packaged OCR dependencies.
- Removed old RapidOCR-specific debug and preview scripts from `tests/sample-screenshot/`.
- Reworked the subtitle runtime benchmark so it exercises `PaddleOCR` presets only.

## Model Behavior

- Realtime and deep mode both initialize through `PaddleOCRProvider` in [`src/autotrans/services/ocr.py`](/Users/phucnd/Documents/Auto-trans/Auto-trans/src/autotrans/services/ocr.py).
- The preferred recognition model name is `latin_PP-OCRv5_rec_mobile`.
- For compatibility with an existing local cache, the provider can still resolve older cached folders such as `en_PP-OCRv5_mobile_rec`.
- If the local cache does not contain the needed model and network access is available, Paddle can fetch the model automatically through its normal model hosting flow.

## Realtime Benchmark

Source: [`tests/ocr_test/subtitle_runtime_benchmark.json`](/Users/phucnd/Documents/Auto-trans/Auto-trans/tests/ocr_test/subtitle_runtime_benchmark.json)

Test set:
- 11 subtitle images from `tests/ocr_test/sub*.png`

Results from the latest rerun in the project venv:
- `paddleocr/runtime-default`: `avg_ocr=226.85ms`, `avg_total=228.53ms`
- `paddleocr/runtime-no-crop`: `avg_ocr=1000.25ms`, `avg_total=1000.50ms`
- `paddleocr/runtime-det-640`: `avg_ocr=1765.92ms`, `avg_total=1766.18ms`
- `paddleocr/runtime-latin-rec`: `avg_ocr=204.32ms`, `avg_total=204.52ms`

Interpretation:
- Subtitle crop remains the main performance win for realtime OCR.
- Raising detection size to `640` is materially slower in the current runtime path.
- The current Paddle-only default remains suitable for realtime subtitle OCR.

## Deep Mode OCR Preview

Source script: [`tests/sample-screenshot/render_deepmode_ocr_preview.py`](/Users/phucnd/Documents/Auto-trans/Auto-trans/tests/sample-screenshot/render_deepmode_ocr_preview.py)

Latest rerun summary:
- `quest1.png`: `47` line boxes, `42` grouped deep boxes
- `quest2.png`: `45` line boxes, `39` grouped deep boxes

Observed behavior:
- Deep mode still groups quest description paragraphs correctly.
- HUD and menu text are also detected, which is expected for a full-screen OCR preview.
- The grouped quest text remains suitable for sending to the deep translation path.

## Verification

- `py_compile` passed for the updated runtime, tests, and preview scripts.
- Realtime benchmark was rerun in the project `./.venv`.
- Deep mode OCR preview was rerun in the project `./.venv`.

## Current Assessment

- The repo is now materially simpler because OCR is Paddle-only.
- Realtime OCR remains fast enough when subtitle crop stays enabled.
- Deep mode OCR remains functional with Paddle layout grouping.
- The next cleanup opportunity is deleting stale local cache folders once the desired Paddle recognition model is present locally.
