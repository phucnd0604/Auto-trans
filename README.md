# AutoTrans

Windows desktop MVP for realtime OCR translation overlay aimed at windowed and borderless games.

## Implemented in this scaffold

- PySide6 desktop control window
- Transparent always-on-top overlay with click-through behavior on Windows
- Capture abstraction with a Windows window capture implementation
- OCR abstraction with a mock provider and an optional PaddleOCR provider
- Translation abstraction with cache, hybrid policy, local stub provider, and optional OpenAI cloud provider
- Tracking and debounce pipeline to stabilize OCR boxes before showing overlay text
- Tests for cache, policy, tracking, and orchestrator behavior

## Quick start

1. Create and activate a Python 3.11+ virtual environment.
2. Install base dependencies:

```powershell
pip install -e .[dev]
```

3. Run the app:

```powershell
autotrans
```

The MVP runs with mock OCR and local translation fallback by default. To wire real providers, set environment variables and install optional extras.

## Shareable Windows setup

If you want to share the project without packaging a standalone `.exe`, use the included scripts:

```powershell
.\setup_windows.ps1
```

For a lighter install:

```powershell
.\setup_windows.ps1 -Profile lite
```

Then run:

```powershell
.\run_windows.ps1
```

Or double-click:

```text
run_windows.cmd
```

## Portable zip without Python installed

If the target machine does not have Python installed, you can share a small zip that contains only:

- source code
- `.runtime` data if you want to prebundle caches/models
- bootstrap scripts

On the target machine:

```powershell
.\bootstrap_portable.ps1
```

For a lighter setup:

```powershell
.\bootstrap_portable.ps1 -Profile lite
```

Then run:

```text
run_portable.cmd
```

The bootstrap script downloads the official Windows embedded Python package from Python.org and installs only the runtime dependencies needed by the selected profile.

To create a small zip for sharing:

```powershell
.\create_share_zip.ps1
```

## Real OCR setup

Install OCR extras:

```powershell
pip install -e .[ocr]
```

Enable PaddleOCR:

```powershell
$env:AUTOTRANS_OCR_PROVIDER="paddle"
$env:AUTOTRANS_OCR_LANGUAGES="en,jp"
$env:AUTOTRANS_OCR_MIN_CONFIDENCE="0.45"
python -m autotrans.app
```

Useful OCR tuning:

```powershell
$env:AUTOTRANS_OCR_PREPROCESS="1"
$env:AUTOTRANS_OCR_MAX_SIDE="1600"
```

If PaddleOCR cannot load, the app will print the reason and fall back to mock OCR.

## Optional providers

### OpenAI cloud translator

```powershell
pip install -e .[openai]
$env:OPENAI_API_KEY="..."
$env:AUTOTRANS_CLOUD_PROVIDER="openai"
```

### OpenAI-compatible local server

You can point AutoTrans at a local server such as LM Studio that exposes an OpenAI-compatible API.

```powershell
pip install -e .[openai]
$env:AUTOTRANS_CLOUD_PROVIDER="openai"
$env:AUTOTRANS_OPENAI_BASE_URL="http://127.0.0.1:1234/v1"
$env:AUTOTRANS_OPENAI_API_KEY="lm-studio"
$env:AUTOTRANS_OPENAI_MODEL="your-local-model-name"
```

Recommended practical path on this machine:

- Run a local OpenAI-compatible server on `localhost`
- Use a small quantized instruct model first
- Keep OCR and overlay local, and only use the local model for translation

The app treats `localhost` as an available local endpoint and will not block on remote network checks.

### Local translator backend

The local translator interface is implemented, but the default provider is a lightweight stub until a CTranslate2 model is configured.

```powershell
pip install -e .[local_translate]
$env:AUTOTRANS_LOCAL_MODEL_DIR="C:\models\my-translator"
```

## Known gaps

- No exclusive fullscreen support
- No anti-cheat compatibility guarantees
- PaddleOCR on Python 3.13 may fail depending on transitive wheels; Python 3.11 or 3.12 is safer if OCR install breaks
- Default local translator is a stub; real model integration is designed in but not bundled
