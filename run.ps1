$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtualenv not found. Create .venv and install dependencies first."
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = "src"

& $python -m autotrans.app
