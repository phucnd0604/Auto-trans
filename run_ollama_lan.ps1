param(
    [string]$Server = "127.0.0.1",
    [string]$Model = "qwen2.5:3b",
    [string]$Port = "11434"
)

$env:AUTOTRANS_OCR_PROVIDER = "rapidocr"
$env:AUTOTRANS_SOURCE_LANG = "en"
$env:AUTOTRANS_TARGET_LANG = "vi"
$env:AUTOTRANS_SUBTITLE_MODE = "1"
$env:AUTOTRANS_LOCAL_MODEL_ENABLED = "0"
$env:AUTOTRANS_CLOUD_PROVIDER = "openai"
$env:AUTOTRANS_OPENAI_BASE_URL = "http://$Server`:$Port/v1"
$env:AUTOTRANS_OPENAI_API_KEY = "ollama"
$env:AUTOTRANS_OPENAI_MODEL = $Model
$env:PYTHONIOENCODING = "utf-8"

& ".\.venv\Scripts\python.exe" -m autotrans.app
