# AutoTrans

## Chay Tu Source

1. Clone repo.
2. Tao va cai dat venv:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e .[dev,ocr,local_translate]
```

3. Chay app:

```powershell
.\run.ps1
```

## Build EXE

Neu can build exe tu source:

```powershell
.\build_exe.ps1
```

## OCR Runtime

- OCR runtime hien tai da duoc chuan hoa thanh `PaddleOCR` cho ca realtime va deep mode.
- Benchmark subtitle OCR va deep mode preview co the chay lai bang guide trong [GUIDE_OCR_BENCHMARK_AND_DEEPMODE.md](/Users/phucnd/Documents/Auto-trans/Auto-trans/GUIDE_OCR_BENCHMARK_AND_DEEPMODE.md).
- Bao cao chot trang thai Paddle-only OCR nam o [REPORT_2026-04-01_PADDLEOCR_ONLY.md](/Users/phucnd/Documents/Auto-trans/Auto-trans/REPORT_2026-04-01_PADDLEOCR_ONLY.md).
