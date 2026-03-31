# Changelog

## 2026-03-31

### Realtime OCR
- Added `PaddleOCR` as a selectable realtime OCR engine while keeping deep mode fixed on `RapidOCR`.
- Realtime OCR now supports `rapidocr` and `paddleocr` from the startup settings dialog.
- Deep translation continues to use the existing Gemini flow and `RapidOCR` paragraph OCR path.
- Removed runtime OCR fallback so `paddleocr` now runs as the selected engine instead of silently dropping to another provider.
- Tuned the realtime `PaddleOCR` path for subtitle crop workloads using `PP-OCRv5_mobile_det`, `en_PP-OCRv5_mobile_rec`, reduced detection side length, and higher recognition batch size.

### Startup And Logging
- Moved realtime OCR, deep OCR, and local `ctranslate2` translator initialization behind lazy wrappers so the app can show UI before heavy model startup finishes.
- Added per-step startup timing logs under `[AutoTrans][Startup]` and explicit one-time logs when OCR/translator instances are initialized.
- Runtime logs are now cleared on every new session instead of appending to old runs.
- Added richer subtitle-filter diagnostics, cache hit/miss logs, and live translation timing logs to make runtime analysis easier.

### UI
- Added descriptive hover tooltips to settings titles and controls so each startup/runtime option explains its effect.
- Clarified in UI behavior that `OCR Provider` applies to realtime translation only; deep mode remains on `RapidOCR`.

### OCR
- Kept the existing subtitle OCR flow and detection logic, but added support for overriding the RapidOCR recognition model via runtime config.
- The app now prefers `.runtime/models/ocr/latin_PP-OCRv5_rec_mobile_infer.onnx` for OCR recognition when that file is present.
- This keeps the current detector path unchanged while allowing a faster recognition model to be applied without changing the rest of the runtime pipeline.

### Benchmarking
- Added a subtitle OCR benchmark script at `tests/ocr_test/benchmark_subtitle_runtime.py`.
- The benchmark reproduces the runtime subtitle OCR path up to the pre-translation output stage.
- Added more subtitle sample images under `tests/ocr_test/` to evaluate OCR speed and stability on a broader set.
- Benchmarked multiple OCR presets, including crop/no-crop, angle classifier toggles, detection size changes, PP-OCRv4/v5 recognition models, and DirectML experiments.

### Findings
- On the expanded subtitle sample set, `no-crop` and `no-cls-no-crop` remain the fastest presets, but they introduce more OCR noise.
- Among the recognition-model-only swaps, `latin_PP-OCRv5_rec_mobile` was the strongest practical option tested.
- DirectML on RX 6600 XT did not show a meaningful speedup over CPU for the tested subtitle OCR workload, so runtime remains CPU-oriented for now.
- On the current subtitle runtime benchmark, optimized `PaddleOCR` is materially faster than `RapidOCR` when subtitle crop is enabled.
- Startup slowness on the `paddleocr` path is dominated by provider initialization time, which is now deferred until first realtime OCR use.
