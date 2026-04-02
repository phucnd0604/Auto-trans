param(
    [switch]$SyncEnv,
    [switch]$SyncModels,
    [switch]$RecreateVenv,
    [switch]$SkipRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$venvDir = Join-Path $repoRoot ".venv"
$python = Join-Path $venvDir "Scripts\python.exe"

function Get-BootstrapPython {
    $candidates = @(
        @{ Command = "py"; Args = @("-3.11", "-c", "print('ok')") },
        @{ Command = "python"; Args = @("-c", "print('ok')") }
    )

    foreach ($candidate in $candidates) {
        $commandInfo = Get-Command $candidate.Command -ErrorAction SilentlyContinue
        if ($null -eq $commandInfo) {
            continue
        }
        try {
            & $candidate.Command @($candidate.Args) *> $null
            if ($LASTEXITCODE -eq 0) {
                return $candidate.Command
            }
        } catch {
            continue
        }
    }

    throw "Python launcher not found. Install Python 3.11 or ensure 'py'/'python' is on PATH."
}

function Ensure-Venv {
    if ($RecreateVenv -and (Test-Path $venvDir)) {
        Write-Host "[AutoTrans] Removing existing .venv"
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }

    if (Test-Path $python) {
        return
    }

    $bootstrapPython = Get-BootstrapPython
    Write-Host "[AutoTrans] Creating virtualenv in .venv"
    if ($bootstrapPython -eq "py") {
        & py -3.11 -m venv $venvDir
    } else {
        & python -m venv $venvDir
    }
}

function Sync-Environment {
    Write-Host "[AutoTrans] Syncing environment"
    & $python -m pip install --upgrade pip setuptools wheel
    & $python -m pip install -e ".[dev,ocr,local_translate]"
}

function Sync-Models {
    Write-Host "[AutoTrans] Ensuring runtime models"
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONPATH = "src"
    @'
import os
from pathlib import Path

from autotrans.config import AppConfig
from autotrans.services.ocr import PaddleOCRProvider
from autotrans.services.translation import build_default_local_translator

config = AppConfig()

runtime_dirs = [
    config.runtime_root_dir,
    config.local_model_dir,
    config.cache_root_dir,
    config.xdg_data_home,
    config.xdg_cache_home,
    config.xdg_config_home,
    config.hf_home,
    config.paddle_cache_dir,
    config.log_dir,
]
for path in runtime_dirs:
    path.mkdir(parents=True, exist_ok=True)

os.environ["XDG_DATA_HOME"] = str(config.xdg_data_home.resolve())
os.environ["XDG_CACHE_HOME"] = str(config.xdg_cache_home.resolve())
os.environ["XDG_CONFIG_HOME"] = str(config.xdg_config_home.resolve())
os.environ["HF_HOME"] = str(config.hf_home.resolve())
os.environ["PADDLE_HOME"] = str(config.paddle_cache_dir.resolve())
os.environ["PADDLE_PDX_CACHE_HOME"] = str(config.paddle_cache_dir.resolve())

print(f"[AutoTrans] Runtime root: {config.runtime_root_dir}")
print(f"[AutoTrans] Local model dir: {config.local_model_dir}")
print(f"[AutoTrans] Paddle cache dir: {config.paddle_cache_dir}")

print("[AutoTrans] Ensuring local translator model...")
build_default_local_translator(config)
print("[AutoTrans] Local translator model ready")

print("[AutoTrans] Ensuring PaddleOCR models...")
provider = PaddleOCRProvider(config)
layout_engine = provider._get_layout_engine()
print(
    "[AutoTrans] PaddleOCR models ready "
    f"(layout={'enabled' if layout_engine is not None else 'unavailable'})"
)
'@ | & $python -
}

Ensure-Venv

if ($SyncEnv -or $RecreateVenv) {
    Sync-Environment
}

if ($SyncEnv -or $SyncModels -or $RecreateVenv) {
    Sync-Models
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = "src"

if (-not $SkipRun) {
    & $python -m autotrans.app
}
