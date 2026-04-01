# Bắt Đầu Nhanh

## Tổng quan

`AutoTrans` là ứng dụng OCR overlay dành cho game trên Windows.

Trạng thái hiện tại:
- OCR runtime đã được chuẩn hóa sang `PaddleOCR`
- Deep mode dùng OCR đoạn văn + phân tích layout bằng Paddle
- Dịch realtime dùng `ctranslate2`
- Deep mode ưu tiên `Gemini`, nếu không dùng được thì fallback sang `ctranslate2`

## Yêu cầu

- Python `3.11`
- Windows để chạy app thực tế
- `venv` cục bộ của project

## Chạy từ source

Thực hiện tại thư mục root của repo:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e .[dev,ocr,local_translate]
```

Chạy app:

```powershell
.\run.ps1
```

## Build EXE

```powershell
.\build_exe.ps1
```

## Biến môi trường quan trọng

- `PYTHONPATH=src`
- `PADDLE_PDX_CACHE_HOME=.runtime/paddlex-cache`
- `AUTOTRANS_DEEP_TRANSLATION_API_KEY`
- `AUTOTRANS_DEEP_TRANSLATION_MODEL`

Nếu local cache chưa có model Paddle và máy có mạng, Paddle có thể tự tải model cần thiết.

## Tài liệu liên quan

- [Hướng dẫn benchmark OCR và test deepmode](./ocr-benchmark-and-deepmode.md)
- [Changelog](./changelog.md)
- [Báo cáo PaddleOCR-only](./reports/2026-04-01-paddleocr-only.md)

