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

Hoặc để script tự đồng bộ môi trường trước khi chạy:

```powershell
.\run.ps1 -SyncEnv
```

Để chỉ kiểm tra và tải các model runtime cần thiết về `.runtime`:

```powershell
.\run.ps1 -SyncModels -SkipRun
```

Nếu cần dựng lại `.venv` từ đầu:

```powershell
.\run.ps1 -RecreateVenv
```

## Build EXE

```powershell
.\build_exe.ps1
```
