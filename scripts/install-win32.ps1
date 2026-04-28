# CH8 Agent - Windows Installation Script
# For Windows 10/11 (64-bit recommended, WSL2 preferred)
# Usage: powershell -ExecutionPolicy Bypass -c "iwr -useb https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/master/scripts/install-win32.ps1 | iex"

$ErrorActionPreference = "Stop"

Write-Host @"

   _____ _   _ ___
  / ____| | | ( _ )
 | |    | |_| / _ \
 | |___ |  _  | (_) |
  \____|_| |_|\___/   Agent  -  Windows

"@ -ForegroundColor Cyan

# ── WSL2 recommendation ───────────────────────────────────────────────────
Write-Host "Note: For best experience, use WSL2 (Windows Subsystem for Linux):" -ForegroundColor Yellow
Write-Host "  wsl --install" -ForegroundColor Green
Write-Host "  Then run the Linux installer inside WSL." -ForegroundColor Yellow
Write-Host ""

# ── Check Python 3.10+ ───────────────────────────────────────────────────
Write-Host "[1/5] Checking Python..." -ForegroundColor Blue

$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $python = $cmd
                Write-Host "  [OK] $ver" -ForegroundColor Green
                break
            }
        }
    } catch {}
}

if (-not $python) {
    Write-Host "  [ERROR] Python 3.10+ not found." -ForegroundColor Red
    Write-Host "  Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  Check 'Add Python to PATH' during install." -ForegroundColor Yellow
    exit 1
}

# ── Check Git ─────────────────────────────────────────────────────────────
Write-Host "[2/5] Checking Git..." -ForegroundColor Blue

try {
    $gitVer = & git --version 2>&1
    Write-Host "  [OK] $gitVer" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Git not found." -ForegroundColor Red
    Write-Host "  Download from: https://git-scm.com/download/win" -ForegroundColor Yellow
    exit 1
}

# ── Clone or update ───────────────────────────────────────────────────────
Write-Host "[3/5] Downloading CH8 Agent..." -ForegroundColor Blue

$installDir = "$env:USERPROFILE\ch8-agent"

# Kill any running ch8 processes so files are not locked during update
Write-Host "  Stopping ch8 processes..." -ForegroundColor Yellow
$prev = $ErrorActionPreference; $ErrorActionPreference = "SilentlyContinue"
taskkill /F /IM python.exe /T 2>&1 | Out-Null
taskkill /F /IM python3.exe /T 2>&1 | Out-Null
Remove-Item "$env:USERPROFILE\.config\ch8\*.pid" -Force 2>&1 | Out-Null
Start-Sleep -Seconds 1
$ErrorActionPreference = $prev

if (Test-Path $installDir) {
    Write-Host "  Removing old installation..." -ForegroundColor Yellow
    $prev = $ErrorActionPreference; $ErrorActionPreference = "SilentlyContinue"
    Remove-Item -Recurse -Force $installDir 2>&1 | Out-Null
    $ErrorActionPreference = $prev
    if (Test-Path $installDir) {
        Write-Host "  [ERROR] Could not remove $installDir" -ForegroundColor Red
        Write-Host "  Close any open terminals/editors using ch8 files and retry." -ForegroundColor Yellow
        exit 1
    }
}

$prev = $ErrorActionPreference; $ErrorActionPreference = "SilentlyContinue"
git clone https://github.com/hudsonrj/ch8-cluster-agent.git $installDir 2>&1 | Out-Null
$ErrorActionPreference = $prev
if (-not (Test-Path "$installDir\ch8")) {
    Write-Host "  [ERROR] Clone failed. Check your internet connection." -ForegroundColor Red
    exit 1
}

Write-Host "  [OK] Installed at $installDir" -ForegroundColor Green

# ── Install Python dependencies ───────────────────────────────────────────
Write-Host "[4/5] Installing dependencies..." -ForegroundColor Blue

# Install dependencies — suppress stderr (pip PATH warnings, etc.)
$prev = $ErrorActionPreference; $ErrorActionPreference = "SilentlyContinue"
& $python -m pip install --quiet --upgrade pip --no-warn-script-location 2>&1 | Out-Null
& $python -m pip install --quiet --no-warn-script-location httpx psutil fastapi uvicorn pydantic 2>&1 | Out-Null
$ErrorActionPreference = $prev

Write-Host "  [OK] httpx, psutil, fastapi, uvicorn, pydantic" -ForegroundColor Green

# ── Create ch8.bat wrapper ────────────────────────────────────────────────
Write-Host "[5/5] Creating ch8 command..." -ForegroundColor Blue

$batContent = @"
@echo off
set PYTHONPATH=$installDir
$python "$installDir\ch8" %*
"@

$batPath = "$installDir\ch8.bat"
$batContent | Out-File -FilePath $batPath -Encoding ASCII

# Add to user PATH if not already there
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*ch8-agent*") {
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$installDir", "User")
    Write-Host "  [OK] Added $installDir to PATH" -ForegroundColor Green
} else {
    Write-Host "  [OK] Already in PATH" -ForegroundColor Green
}
# Also update PATH for the current session (no restart needed)
$env:PATH = "$env:PATH;$installDir"

# Config dir
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.config\ch8" | Out-Null

# ── Done ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔═══════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   CH8 Agent installed on Windows!    ║" -ForegroundColor Green
Write-Host "╚═══════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps (restart terminal first, then):" -ForegroundColor Yellow
Write-Host "  ch8 config ai              (configure AI provider)" -ForegroundColor Green
Write-Host "  ch8 up --token <TOKEN>     (join your network)" -ForegroundColor Green
Write-Host ""
Write-Host "Or run directly:" -ForegroundColor Yellow
Write-Host "  $python $installDir\ch8 up --token <TOKEN>" -ForegroundColor Cyan
Write-Host ""
Write-Host "Recommended AI providers:" -ForegroundColor Yellow
Write-Host "  Groq   (cloud, free) - groq.com" -ForegroundColor Cyan
Write-Host "  Ollama (local)       - ollama.com/download" -ForegroundColor Cyan
Write-Host ""
Write-Host "Docs: https://github.com/hudsonrj/ch8-cluster-agent" -ForegroundColor Blue
Write-Host ""
