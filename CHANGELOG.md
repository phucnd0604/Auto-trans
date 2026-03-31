# Changelog

## 2026-03-31

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
