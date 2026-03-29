param(
    [ValidateSet("full", "lite")]
    [string]$Profile = "full"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$runtimeRoot = Join-Path $repoRoot ".portable-runtime"
$pythonRoot = Join-Path $runtimeRoot "python"
$pythonExe = Join-Path $pythonRoot "python.exe"
$pythonPth = Join-Path $pythonRoot "python313._pth"
$markerFile = Join-Path $runtimeRoot ("installed-" + $Profile + ".marker")
$pythonUrl = "https://www.python.org/ftp/python/3.13.12/python-3.13.12-embed-amd64.zip"
$getPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$requirementsFile = if ($Profile -eq "full") {
    Join-Path $repoRoot "requirements-portable-full.txt"
} else {
    Join-Path $repoRoot "requirements-portable-lite.txt"
}

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null

if (-not (Test-Path $pythonExe)) {
    $pythonZip = Join-Path $runtimeRoot "python-embed.zip"
    Write-Host "Downloading embedded Python..." -ForegroundColor Green
    Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZip

    if (Test-Path $pythonRoot) {
        Remove-Item -Recurse -Force $pythonRoot
    }

    Expand-Archive -Path $pythonZip -DestinationPath $pythonRoot -Force
    Remove-Item -Force $pythonZip

    $pthContent = @(
        "python313.zip",
        ".",
        "Lib\site-packages",
        "import site"
    )
    Set-Content -Path $pythonPth -Value $pthContent -Encoding ASCII
}

if (-not (Test-Path $markerFile)) {
    $getPipPath = Join-Path $runtimeRoot "get-pip.py"
    Write-Host "Downloading pip bootstrap..." -ForegroundColor Green
    Invoke-WebRequest -Uri $getPipUrl -OutFile $getPipPath

    Write-Host "Installing pip into embedded Python..." -ForegroundColor Green
    & $pythonExe $getPipPath
    Remove-Item -Force $getPipPath

    Write-Host "Installing runtime dependencies..." -ForegroundColor Green
    & $pythonExe -m pip install --upgrade pip
    & $pythonExe -m pip install -r $requirementsFile

    Set-Content -Path $markerFile -Value (Get-Date -Format s) -Encoding ASCII
}

Write-Host ""
Write-Host "Portable runtime ready." -ForegroundColor Green
Write-Host "Run with:" -ForegroundColor Green
Write-Host "  .\run_portable.cmd" -ForegroundColor Yellow
