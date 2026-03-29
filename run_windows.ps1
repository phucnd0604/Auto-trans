$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtualenv not found. Run .\setup_windows.ps1 first."
}

Set-ExecutionPolicy -Scope Process Bypass
$env:PYTHONIOENCODING = "utf-8"

& $python -m autotrans.app
