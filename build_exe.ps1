$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtualenv not found. Create .venv and install dependencies first."
}

$deploy = Join-Path $repoRoot ".venv\Scripts\pyside6-deploy.exe"
if (-not (Test-Path $deploy)) {
    throw "pyside6-deploy not found in .venv. Install the project dependencies in the venv first."
}

$env:PYTHONIOENCODING = "utf-8"

& $deploy pysidedeploy.spec
