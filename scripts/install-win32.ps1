# CH8 Agent - Windows 32-bit Installation Script
# For old Windows PCs, Windows 7/8/10 32-bit

$ErrorActionPreference = "Stop"

Write-Host @"

   _____ _    _  ___
  / ____| |  | |/ _ \
 | |    | |__| | (_) |
 | |    |  __  |> _ <
 | |____| |  | | (_) |
  \_____|_|  |_|\___/

 Windows 32-bit Installation

"@ -ForegroundColor Green

# Check if 32-bit
function Check-Architecture {
    $arch = $env:PROCESSOR_ARCHITECTURE

    if ($arch -ne "x86") {
        Write-Host "Warning: Not detected as 32-bit (detected: $arch)" -ForegroundColor Yellow
        $response = Read-Host "Continue anyway? (y/n)"
        if ($response -ne "y") {
            exit 1
        }
    }

    Write-Host "Architecture: $arch" -ForegroundColor Green
}

# Check RAM
function Check-RAM {
    $computerInfo = Get-CimInstance Win32_ComputerSystem
    $ramMB = [math]::Round($computerInfo.TotalPhysicalMemory / 1MB)

    Write-Host "Available RAM: ${ramMB}MB" -ForegroundColor Yellow

    if ($ramMB -lt 1024) {
        Write-Host "Warning: Low memory. Minimum 1GB recommended." -ForegroundColor Yellow
        $script:tier = "nano"
    }
    elseif ($ramMB -lt 2048) {
        $script:tier = "tiny"
    }
    else {
        $script:tier = "small"
    }

    Write-Host "Tier: $script:tier" -ForegroundColor Green
    return $ramMB
}

# Install Python if not present
function Install-Python {
    $pythonPath = Get-Command python -ErrorAction SilentlyContinue

    if (-not $pythonPath) {
        Write-Host "Python not found. Please install Python 3.8+ (32-bit)" -ForegroundColor Red
        Write-Host "Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host "Make sure to select '32-bit' version!" -ForegroundColor Yellow
        exit 1
    }

    $pythonVersion = & python --version 2>&1
    Write-Host "Found: $pythonVersion" -ForegroundColor Green
}

# Install Git if not present
function Install-Git {
    $gitPath = Get-Command git -ErrorAction SilentlyContinue

    if (-not $gitPath) {
        Write-Host "Git not found. Please install Git" -ForegroundColor Red
        Write-Host "Download from: https://git-scm.com/download/win" -ForegroundColor Yellow
        exit 1
    }

    Write-Host "Git found" -ForegroundColor Green
}

# Download llama.cpp binary (pre-built for Windows)
function Install-LlamaCpp {
    Write-Host "Downloading llama.cpp..."

    $llamaCppDir = "$env:USERPROFILE\.ch8\llama.cpp"
    New-Item -ItemType Directory -Force -Path $llamaCppDir | Out-Null

    # Download pre-built binary
    $llamaCppUrl = "https://github.com/ggerganov/llama.cpp/releases/latest/download/llama-cpp-windows-x86.zip"
    $llamaCppZip = "$env:TEMP\llama-cpp.zip"

    try {
        Invoke-WebRequest -Uri $llamaCppUrl -OutFile $llamaCppZip -UseBasicParsing
        Expand-Archive -Path $llamaCppZip -DestinationPath $llamaCppDir -Force
        Remove-Item $llamaCppZip
        Write-Host "llama.cpp installed" -ForegroundColor Green
    }
    catch {
        Write-Host "Note: Could not download pre-built binary" -ForegroundColor Yellow
        Write-Host "You may need to build from source" -ForegroundColor Yellow
    }
}

# Download model
function Download-Model {
    param($tier)

    Write-Host "Downloading model..."

    $modelsDir = "$env:USERPROFILE\.ch8\models"
    New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null

    switch ($tier) {
        "nano" {
            $modelUrl = "https://huggingface.co/QuantFactory/SmolLM-135M-Instruct-GGUF/resolve/main/SmolLM-135M-Instruct.Q4_K_M.gguf"
            $modelName = "smollm-135m-q4.gguf"
        }
        default {
            $modelUrl = "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q2_K.gguf"
            $modelName = "tinyllama-1.1b-q2.gguf"
        }
    }

    $modelPath = "$modelsDir\$modelName"

    if (-not (Test-Path $modelPath)) {
        Write-Host "Downloading $modelName..."
        Invoke-WebRequest -Uri $modelUrl -OutFile $modelPath -UseBasicParsing
        Write-Host "Model downloaded" -ForegroundColor Green
    }
    else {
        Write-Host "Model already downloaded" -ForegroundColor Yellow
    }

    return $modelPath
}

# Install CH8 Agent
function Install-CH8Agent {
    Write-Host "Installing CH8 Agent..."

    $ch8Dir = "$env:USERPROFILE\.ch8\ch8-agent"

    if (-not (Test-Path $ch8Dir)) {
        git clone https://github.com/hudsonrj/ch8-cluster-agent.git $ch8Dir
    }
    else {
        Write-Host "Updating CH8 Agent..."
        Push-Location $ch8Dir
        git pull
        Pop-Location
    }

    # Create virtual environment
    Push-Location $ch8Dir
    python -m venv venv
    & .\venv\Scripts\Activate.ps1
    pip install --upgrade pip
    pip install aiohttp structlog psutil pyyaml
    deactivate
    Pop-Location

    Write-Host "CH8 Agent installed" -ForegroundColor Green
}

# Create configuration
function Create-Config {
    param($tier, $ramMB, $modelPath)

    $configDir = "$env:USERPROFILE\.ch8\config"
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null

    $configContent = @"
node:
  id: win32-$env:COMPUTERNAME
  tier: $tier

hardware:
  platform: windows-x86
  ram_mb: $ramMB

llm:
  backend: llama.cpp
  model_path: $modelPath
  context_length: 512
  threads: $env:NUMBER_OF_PROCESSORS

performance:
  max_concurrent_tasks: 1
  batch_processing: true
"@

    $configContent | Out-File -FilePath "$configDir\node.yaml" -Encoding UTF8

    Write-Host "Configuration created" -ForegroundColor Green
}

# Create start script
function Create-StartScript {
    $ch8Dir = "$env:USERPROFILE\.ch8\ch8-agent"
    $startScript = "$env:USERPROFILE\.ch8\start-ch8.bat"

    $scriptContent = @"
@echo off
cd /d "$ch8Dir"
call venv\Scripts\activate.bat
python -m cluster.node
pause
"@

    $scriptContent | Out-File -FilePath $startScript -Encoding ASCII

    Write-Host "Start script created at: $startScript" -ForegroundColor Green
}

# Print summary
function Print-Summary {
    param($tier, $ramMB)

    Write-Host @"

╔════════════════════════════════════════════════╗
║   CH8 Agent Installation Complete (Win32)!    ║
╚════════════════════════════════════════════════╝

Architecture: Windows 32-bit
Tier: $tier
RAM: ${ramMB}MB

To start CH8 Agent:
  Double-click: $env:USERPROFILE\.ch8\start-ch8.bat

Or manually:
  cd $env:USERPROFILE\.ch8\ch8-agent
  venv\Scripts\activate
  python -m cluster.node

Configuration: $env:USERPROFILE\.ch8\config\node.yaml

"@ -ForegroundColor Green
}

# Main installation
function Main {
    Check-Architecture
    $ramMB = Check-RAM
    Install-Python
    Install-Git
    Install-LlamaCpp
    $modelPath = Download-Model -tier $script:tier
    Install-CH8Agent
    Create-Config -tier $script:tier -ramMB $ramMB -modelPath $modelPath
    Create-StartScript
    Print-Summary -tier $script:tier -ramMB $ramMB
}

Main
