param(
    [string]$OutputName = "AutoTrans-shareable",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtualenv not found. Expected at .venv\\Scripts\\python.exe"
}

if (-not $SkipTests) {
    Write-Host "Running tests..." -ForegroundColor Green
    & $python -m pytest
}

$distRoot = Join-Path $repoRoot "dist"
if (Test-Path (Join-Path $distRoot $OutputName)) {
    Remove-Item -Recurse -Force (Join-Path $distRoot $OutputName)
}
if (Test-Path (Join-Path $distRoot ($OutputName + ".zip"))) {
    Remove-Item -Force (Join-Path $distRoot ($OutputName + ".zip"))
}

Write-Host "Creating shareable zip..." -ForegroundColor Green
& (Join-Path $repoRoot "create_share_zip.ps1") -OutputName $OutputName

Write-Host ""
Write-Host "Done. Share this file:" -ForegroundColor Green
Write-Host "  dist\\$OutputName.zip" -ForegroundColor Yellow
