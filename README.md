# AutoTrans

Tài liệu dự án đã được gom về thư mục [`docs`](./docs).

## Lối vào nhanh

- [Mục lục tài liệu](./docs/README.md)
- [Bắt đầu nhanh](./docs/getting-started.md)
- [Hướng dẫn benchmark OCR và test deepmode](./docs/ocr-benchmark-and-deepmode.md)
- [Changelog](./docs/changelog.md)
- [Báo cáo PaddleOCR-only](./docs/reports/2026-04-01-paddleocr-only.md)

## Chạy nhanh từ source

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e .[dev,ocr,local_translate]
.\run.ps1
```

## Build EXE

```powershell
.\build_exe.ps1
```
