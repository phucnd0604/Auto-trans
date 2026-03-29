param(
    [ValidateSet("full", "lite")]
    [string]$Profile = "full"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot ".portable-runtime\python\python.exe"
if (-not (Test-Path $pythonExe)) {
    & (Join-Path $repoRoot "bootstrap_portable.ps1") -Profile $Profile
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = (Join-Path $repoRoot "src")

& $pythonExe -m autotrans.app
