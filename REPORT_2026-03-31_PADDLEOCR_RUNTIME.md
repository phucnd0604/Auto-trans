# PaddleOCR Realtime Runtime Report

## Scope

This report summarizes the current realtime OCR work for `PaddleOCR`, the startup investigation, runtime logging changes, and the verification status in the current workspace.

## Implemented Changes

- Added `PaddleOCRProvider` for realtime OCR in `src/autotrans/services/ocr.py`.
- Kept deep mode on `RapidOCR` by introducing a separate `deep_ocr_provider` path in `src/autotrans/services/orchestrator.py`.
- Updated `src/autotrans/app.py` so realtime OCR can be selected as `rapidocr` or `paddleocr`.
- Removed realtime OCR fallback behavior so `paddleocr` either runs as configured or fails loudly.
- Added startup timing logs and lazy initialization wrappers for:
  - realtime OCR provider
  - deep OCR provider
  - local `ctranslate2` translator
- Added runtime logging diagnostics for:
  - subtitle selection rejection reasons
  - cache hit/miss counts
  - live translation timings
  - per-session clean logs
- Updated `src/autotrans/ui/settings_dialog.py` so:
  - `OCR Provider` exposes both `rapidocr` and `paddleocr`
  - hovering setting titles shows detailed explanations
- Added dependency and packaging updates for `paddlepaddle`, `paddleocr`, and `paddlex`.

## Benchmark Summary

Source: `tests/ocr_test/subtitle_runtime_benchmark.json`

Test set:
- 11 subtitle images from `tests/ocr_test/sub*.png`
- subtitle mode enabled
- runtime crop benchmark included

Headline results:
- `rapidocr/runtime-default`: `avg_ocr=541.12ms`, `avg_total=542.31ms`
- `paddleocr/runtime-default`: `avg_ocr=150.46ms`, `avg_total=151.62ms`
- `paddleocr/runtime-no-cls-det-640`: `avg_ocr=144.47ms`, `avg_total=145.86ms`
- `paddleocr/runtime-no-crop`: `avg_ocr=360.58ms`, `avg_total=361.94ms`

Interpretation:
- With subtitle crop enabled, optimized `PaddleOCR` is significantly faster than current `RapidOCR`.
- Without subtitle crop, `PaddleOCR` slows down enough to miss the original `<300ms` target.
- The current runtime setting `ocr_crop_subtitle_only=true` is therefore important for realtime viability.

## Startup Investigation

Measured directly in the current environment using eager construction:
- `PaddleOCRProvider`: `8262.2ms`
- `RapidOCRProvider`: `299.9ms`
- `CTranslate2Translator`: `930.8ms`

Conclusion:
- The main startup delay is `PaddleOCRProvider` initialization.
- Local translator startup also contributes, but it is much smaller than `PaddleOCR`.
- App startup is now improved by lazy initialization, so these costs move to first OCR/translation use instead of blocking UI launch.

## Runtime Log Findings

Recent runtime log analysis showed:
- `PaddleOCR` was running as the realtime provider.
- OCR timing was generally in a usable realtime range after optimization.
- The main remaining live-quality issue was not OCR speed, but subtitle selection rejecting many boxes.
- The dominant rejection reason in the analyzed session was `uppercase_label`.

Logging added for follow-up tuning:
- `[AutoTrans][Startup] ...`
- `subtitle filter raw=... accepted=... rejected=... reasons: ...`
- `live cache hits=... misses=... request_items=...`
- `live translate_ms=... pending_items=... translator=...`

## Verification

Automated tests:
- `pytest tests/test_ocr_runtime_providers.py tests/test_runtime_logging.py tests/test_deep_mode.py -q`
- Result: `32 passed`

Additional checks:
- Verified lazy wrapper creation for realtime OCR and local translator is effectively immediate.
- Verified benchmark report is generated and includes both `rapidocr` and `paddleocr`.

## Current Assessment

- `PaddleOCR` is now usable for realtime evaluation.
- Deep mode remains isolated on `RapidOCR` and Gemini.
- Realtime subtitle OCR performance is now strong when subtitle crop is enabled.
- Startup responsiveness is improved because heavy OCR/translator initialization is deferred.
- The next meaningful quality task is subtitle-selection tuning for `PaddleOCR` output, especially around uppercase subtitle lines versus HUD/menu labels.
