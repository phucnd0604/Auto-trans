# Huong Dan Benchmark OCR Va Test Deepmode

## Muc tieu

Tai lieu nay mo ta cac lenh chuan de kiem tra lai OCR runtime va deep mode sau khi thay doi code, dependency, cache model, hoac subtitle filter.

## Moi truong chay

Chay tu thu muc root cua repo va dung dung `venv` cua project.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe --version
$env:PYTHONPATH = "src"
$env:PADDLE_HOME = Join-Path (Get-Location) ".runtime\paddle"
$env:PADDLE_PDX_CACHE_HOME = Join-Path (Get-Location) ".runtime\paddle"
```

Khuyen nghi:
- Dung `.\run.ps1 -SyncModels -SkipRun` truoc khi benchmark de dam bao local model va Paddle model da nam trong `.runtime`
- Neu may khong co mang, chi cac model da co san trong `.runtime` moi dung duoc
- Neu can dieu tra spike/crash, bat `Diagnostics Capture` trong settings va doc file moi nhat trong `.runtime\logs\sessions`

## 1. Dong bo model runtime

```powershell
.\run.ps1 -SyncModels -SkipRun
```

Lenh nay se:
- kiem tra local translator model trong `.runtime\models\quickmt-en-vi`
- kiem tra Paddle/PaddleX model trong `.runtime\paddle`
- tai model thieu ve dung thu muc runtime

## 2. Benchmark OCR realtime

```powershell
$env:PYTHONPATH = "src"
$env:PADDLE_HOME = Join-Path (Get-Location) ".runtime\paddle"
$env:PADDLE_PDX_CACHE_HOME = Join-Path (Get-Location) ".runtime\paddle"
.\.venv\Scripts\python.exe tests\ocr_test\benchmark_subtitle_runtime.py
```

Y nghia:
- chay OCR tren bo anh subtitle mau trong `tests/ocr_test/`
- benchmark luong OCR realtime hien tai
- ghi report JSON vao `tests/ocr_test/subtitle_runtime_benchmark.json`

## 3. Test deepmode OCR preview

```powershell
$env:PYTHONPATH = "src"
$env:PADDLE_HOME = Join-Path (Get-Location) ".runtime\paddle"
$env:PADDLE_PDX_CACHE_HOME = Join-Path (Get-Location) ".runtime\paddle"
.\.venv\Scripts\python.exe tests\sample-screenshot\render_deepmode_ocr_preview.py
```

Y nghia:
- chay deepmode OCR tren screenshot mau
- render box OCR sau khi grouping theo layout
- xuat PNG va JSON canh file sample

## 4. Test deepmode runtime preview

Local translator:

```powershell
$env:PYTHONPATH = "src"
$env:PADDLE_HOME = Join-Path (Get-Location) ".runtime\paddle"
$env:PADDLE_PDX_CACHE_HOME = Join-Path (Get-Location) ".runtime\paddle"
.\.venv\Scripts\python.exe tests\sample-screenshot\render_deepmode_runtime_preview.py
```

Groq:

```powershell
$env:PYTHONPATH = "src"
$env:PADDLE_HOME = Join-Path (Get-Location) ".runtime\paddle"
$env:PADDLE_PDX_CACHE_HOME = Join-Path (Get-Location) ".runtime\paddle"
$env:AUTOTRANS_DEEP_TRANSLATION_API_KEY = "..."
$env:AUTOTRANS_DEEP_TRANSLATION_PROVIDER = "groq"
$env:AUTOTRANS_DEEP_TRANSLATION_MODEL = "qwen/qwen3-32b"
.\.venv\Scripts\python.exe tests\sample-screenshot\render_deepmode_runtime_preview.py
```

Gemini:

```powershell
$env:PYTHONPATH = "src"
$env:PADDLE_HOME = Join-Path (Get-Location) ".runtime\paddle"
$env:PADDLE_PDX_CACHE_HOME = Join-Path (Get-Location) ".runtime\paddle"
$env:AUTOTRANS_DEEP_TRANSLATION_API_KEY = "..."
$env:AUTOTRANS_DEEP_TRANSLATION_PROVIDER = "gemini"
$env:AUTOTRANS_DEEP_TRANSLATION_MODEL = "gemini-3.1-flash-lite-preview"
.\.venv\Scripts\python.exe tests\sample-screenshot\render_deepmode_runtime_preview.py
```

## 5. Test Groq deep mode rieng

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe tests\translation_test\benchmark_groq_deepmode_translator.py --env-file .env --model qwen/qwen3-32b
```

## 6. Compile check nhanh

```powershell
.\.venv\Scripts\python.exe -m py_compile `
  src\autotrans\app.py `
  src\autotrans\config.py `
  src\autotrans\services\ocr.py `
  src\autotrans\services\orchestrator.py `
  src\autotrans\services\translation.py `
  src\autotrans\services\subtitle_filter.py `
  src\autotrans\ui\main_window.py `
  src\autotrans\ui\settings_dialog.py `
  src\autotrans\utils\runtime_diagnostics.py
```

## 7. Dieu tra runtime theo phien

Sau khi app gap spike, fallback hoac timeout:
- Mo `.runtime\logs\autotrans.log` de xem tom tat text
- Mo file moi nhat trong `.runtime\logs\sessions`

Trong session JSON can uu tien:
- `events`: spike, deep fallback, timeout, error
- `samples`: snapshot nhe theo chu ky
- `last_state`: trang thai cuoi cung duoc ghi truoc khi app thoat

## 8. Khi nao nen chay lai

Chay lai benchmark va test deepmode khi:
- doi model OCR
- doi detection size
- doi subtitle crop hoac logic subtitle selection
- doi layout grouping cua deep mode
- doi cloud provider/model
- doi dependency Paddle hoac Groq
- xoa hoac thay local cache model
