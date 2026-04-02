# Hướng Dẫn Benchmark OCR Và Test Deepmode

## Mục tiêu

Tài liệu này mô tả các lệnh chuẩn để kiểm tra lại OCR runtime và deepmode sau khi thay đổi code hoặc model.

## Môi trường chạy

Chạy từ thư mục root của repo và dùng đúng `venv` của project.

macOS / Linux:

```bash
./.venv/bin/python --version
export PYTHONPATH=src
export PADDLE_PDX_CACHE_HOME="$(pwd)/.runtime/paddlex-cache"
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe --version
$env:PYTHONPATH = "src"
$env:PADDLE_PDX_CACHE_HOME = Join-Path (Get-Location) ".runtime\paddlex-cache"
```

Lưu ý:
- Nếu local cache chưa có model và máy có mạng, Paddle có thể tự tải model.
- Nếu môi trường không có mạng, chỉ các model đã có sẵn trong `PADDLE_PDX_CACHE_HOME` mới dùng được.

## 1. Benchmark OCR realtime

Lệnh:

macOS / Linux:

```bash
PYTHONPATH=src \
PADDLE_PDX_CACHE_HOME="$(pwd)/.runtime/paddlex-cache" \
./.venv/bin/python tests/ocr_test/benchmark_subtitle_runtime.py
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
$env:PADDLE_PDX_CACHE_HOME = Join-Path (Get-Location) ".runtime\paddlex-cache"
.\.venv\Scripts\python.exe tests\ocr_test\benchmark_subtitle_runtime.py
```

Ý nghĩa:
- Chạy OCR trên 11 ảnh subtitle mẫu trong `tests/ocr_test/`
- Benchmark luồng OCR realtime hiện tại
- Ghi report JSON vào `tests/ocr_test/subtitle_runtime_benchmark.json`

Preset hiện có:
- `runtime-default`
- `runtime-no-crop`
- `runtime-det-640`
- `runtime-en-rec`

Mặc định benchmark hiện dùng recognition model `en_PP-OCRv5_mobile_rec`. Nếu máy chỉ còn cache cũ, script và runtime vẫn có thể resolve alias tương thích.

## 2. Test deepmode OCR preview

Lệnh:

macOS / Linux:

```bash
PYTHONPATH=src \
PADDLE_PDX_CACHE_HOME="$(pwd)/.runtime/paddlex-cache" \
./.venv/bin/python tests/sample-screenshot/render_deepmode_ocr_preview.py
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
$env:PADDLE_PDX_CACHE_HOME = Join-Path (Get-Location) ".runtime\paddlex-cache"
.\.venv\Scripts\python.exe tests\sample-screenshot\render_deepmode_ocr_preview.py
```

Ý nghĩa:
- Chạy deepmode OCR trên `quest1.png` và `quest2.png`
- Render box OCR sau khi grouping theo layout
- Xuất PNG và JSON cạnh file sample

Output mong đợi:
- `tests/sample-screenshot/quest1.deepmode-paddleocr_auto-ocr-boxes.png`
- `tests/sample-screenshot/quest1.deepmode-paddleocr_auto-ocr-boxes.json`
- `tests/sample-screenshot/quest2.deepmode-paddleocr_auto-ocr-boxes.png`
- `tests/sample-screenshot/quest2.deepmode-paddleocr_auto-ocr-boxes.json`

## 3. Test deepmode runtime preview

Lệnh local translator:

```bash
PYTHONPATH=src \
PADDLE_PDX_CACHE_HOME="$(pwd)/.runtime/paddlex-cache" \
AUTOTRANS_TRANSLATOR_BACKEND=ctranslate2 \
./.venv/bin/python tests/sample-screenshot/render_deepmode_runtime_preview.py
```

Lệnh ưu tiên Gemini:

```bash
PYTHONPATH=src \
PADDLE_PDX_CACHE_HOME="$(pwd)/.runtime/paddlex-cache" \
AUTOTRANS_TRANSLATOR_BACKEND=gemini-rest \
AUTOTRANS_DEEP_TRANSLATION_MODEL=gemini-3.1-flash-lite-preview \
AUTOTRANS_DEEP_TRANSLATION_API_KEY=... \
./.venv/bin/python tests/sample-screenshot/render_deepmode_runtime_preview.py
```

Ý nghĩa:
- Mô phỏng luồng deepmode gần runtime thật
- Tạo overlay preview cho trạng thái pending và final
- Xác nhận fallback `Gemini -> ctranslate2` vẫn hoạt động khi cần

## 4. Test Groq deep mode riêng

Benchmark này đọc key từ `.env` hoặc biến môi trường:
- `AUTOTRANS_DEEP_TRANSLATION_API_KEY`
- `GROQ_API_KEY`

Model mặc định:
- `moonshotai/kimi-k2-instruct`

Lệnh chạy:

```bash
PYTHONPATH=src \
./.venv/bin/python tests/translation_test/benchmark_groq_deepmode_translator.py \
  --env-file .env \
  --model moonshotai/kimi-k2-instruct
```

Ý nghĩa:
- Dịch các đoạn tiếng Anh khoảng 100 từ
- Ghi report JSON và Markdown vào `tests/translation_test/`
- In ra latency từng đoạn để so sánh tốc độ và chất lượng

## 5. Compile check nhanh

```bash
PYTHONPATH=src ./.venv/bin/python -m py_compile \
  src/autotrans/app.py \
  src/autotrans/config.py \
  src/autotrans/services/ocr.py \
  src/autotrans/services/translation.py \
  src/autotrans/ui/main_window.py \
  src/autotrans/ui/settings_dialog.py \
  tests/ocr_test/benchmark_subtitle_runtime.py \
  tests/sample-screenshot/render_deepmode_ocr_preview.py \
  tests/sample-screenshot/render_deepmode_runtime_preview.py \
  tests/test_deep_mode.py \
  tests/test_ocr_runtime_providers.py
```

## 6. Khi nào nên chạy lại

Chạy lại benchmark và test deepmode khi:
- đổi model OCR
- đổi detection size
- đổi subtitle crop hoặc logic subtitle selection
- đổi layout grouping của deepmode
- thay đổi dependency phiên bản Paddle
- xóa hoặc thay local cache model
