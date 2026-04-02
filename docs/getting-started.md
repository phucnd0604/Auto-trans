# Bat Dau Nhanh

## Tong quan

`AutoTrans` la ung dung OCR overlay cho game tren Windows.

Trang thai hien tai:
- OCR runtime da duoc chuan hoa sang `PaddleOCR`
- Deep mode dung OCR doan van + layout bang Paddle
- Dich realtime dung `ctranslate2`
- Deep mode co the dung `Gemini` hoac `Groq`, neu khong dung duoc thi fallback sang `ctranslate2`

## Yeu cau

- Python `3.11`
- Windows de chay app thuc te
- `venv` cuc bo cua project

## Chay tu source

Thuc hien tai thu muc root cua repo:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e .[dev,ocr,local_translate]
```

Chay app:

```powershell
.\run.ps1
```

De script tu sync dependency truoc khi chay:

```powershell
.\run.ps1 -SyncEnv
```

De chi kiem tra va tai model runtime ve `.runtime`:

```powershell
.\run.ps1 -SyncModels -SkipRun
```

Neu can dung lai `.venv` tu dau:

```powershell
.\run.ps1 -RecreateVenv
```

## Build EXE

```powershell
.\build_exe.ps1
```

## Bien moi truong quan trong

- `PYTHONPATH=src`
- `PADDLE_HOME=.runtime/paddle`
- `PADDLE_PDX_CACHE_HOME=.runtime/paddle`
- `AUTOTRANS_DEEP_TRANSLATION_API_KEY`
- `AUTOTRANS_DEEP_TRANSLATION_MODEL`

Neu local cache chua co model va may co mang, `run.ps1 -SyncModels` se tai cac model can thiet ve `.runtime`.

## Tai lieu lien quan

- [Huong dan benchmark OCR va test deepmode](./ocr-benchmark-and-deepmode.md)
- [Changelog](./changelog.md)
- [Bao cao PaddleOCR-only](./reports/2026-04-01-paddleocr-only.md)
