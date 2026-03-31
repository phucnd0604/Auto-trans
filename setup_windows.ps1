param(
    [ValidateSet("full", "lite")]
    [string]$Profile = "full"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.13 -m venv .venv
}

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

& $python -m pip install --upgrade pip setuptools wheel
& $python -m pip install -e .[dev]

if ($Profile -eq "full") {
    & $python -m pip install -e .[ocr,local_translate]
} else {
    & $python -m pip install rapidocr_onnxruntime ctranslate2 sentencepiece huggingface_hub bettercam
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Run the app with:" -ForegroundColor Green
Write-Host "  .\run_windows.ps1" -ForegroundColor Yellow
