# AutoTrans

## OCR Runtime

- OCR runtime hien tai da duoc chuan hoa thanh `PaddleOCR` cho ca realtime va deep mode.
- Benchmark subtitle OCR va deep mode preview co the chay lai bang guide trong [GUIDE_OCR_BENCHMARK_AND_DEEPMODE.md](/Users/phucnd/Documents/Auto-trans/Auto-trans/GUIDE_OCR_BENCHMARK_AND_DEEPMODE.md).
- Bao cao chot trang thai Paddle-only OCR nam o [REPORT_2026-04-01_PADDLEOCR_ONLY.md](/Users/phucnd/Documents/Auto-trans/Auto-trans/REPORT_2026-04-01_PADDLEOCR_ONLY.md).

## Tao File Share

Chay:

```powershell
.\release_share.ps1
```

Neu muon bo qua test:

```powershell
.\release_share.ps1 -SkipTests
```

File ket qua:

```text
dist\AutoTrans-shareable.zip
```

## Chay App Tu File Share

1. Giai nen `AutoTrans-shareable.zip`
2. Chay:

```powershell
.\bootstrap_portable.ps1
```

Neu muon ban nhe hon:

```powershell
.\bootstrap_portable.ps1 -Profile lite
```

3. Mo app:

```text
run_portable.cmd
```
