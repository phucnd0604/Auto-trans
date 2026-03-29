param(
    [string]$OutputName = "AutoTrans-shareable"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$distRoot = Join-Path $repoRoot "dist"
$stageRoot = Join-Path $distRoot $OutputName
$zipPath = Join-Path $distRoot ($OutputName + ".zip")

if (Test-Path $stageRoot) {
    Remove-Item -Recurse -Force $stageRoot
}
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}

New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null

$includeItems = @(
    "src",
    "main.py",
    "pyproject.toml",
    "README.md",
    "bootstrap_portable.ps1",
    "run_portable.ps1",
    "run_portable.cmd",
    "setup_windows.ps1",
    "run_windows.ps1",
    "run_windows.cmd",
    "requirements-portable-full.txt",
    "requirements-portable-lite.txt"
)

foreach ($item in $includeItems) {
    Copy-Item -Recurse -Force (Join-Path $repoRoot $item) $stageRoot
}

Compress-Archive -Path (Join-Path $stageRoot "*") -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "Shareable zip created:" -ForegroundColor Green
Write-Host "  $zipPath" -ForegroundColor Yellow
