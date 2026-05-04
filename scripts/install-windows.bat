@echo off
REM ═══════════════════════════════════════════════════════════════
REM  CH8 Agent - Windows Native Installer
REM  Run as Administrator for best results
REM ═══════════════════════════════════════════════════════════════

echo.
echo  ██████╗██╗  ██╗ █████╗     █████╗  ██████╗ ███████╗███╗   ██╗████████╗
echo ██╔════╝██║  ██║██╔══██╗   ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
echo ██║     ███████║╚█████╔╝   ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║
echo ██║     ██╔══██║██╔══██╗   ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║
echo ╚██████╗██║  ██║╚█████╔╝   ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║
echo  ╚═════╝╚═╝  ╚═╝ ╚════╝    ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
echo.
echo  Windows Native Installer
echo  ════════════════════════════════════════════════════════════
echo.

set INSTALL_DIR=%USERPROFILE%\ch8-agent
set CONFIG_DIR=%USERPROFILE%\.config\ch8
set REPO=https://github.com/hudsonrj/ch8-cluster-agent.git

REM ── Check Python ──
echo [1/6] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Python not found. Installing via winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo   ERROR: Failed to install Python. Install manually from python.org
        pause
        exit /b 1
    )
    echo   Python installed. You may need to restart this script.
    echo   Refreshing PATH...
    set PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%
)
python --version
echo.

REM ── Check Git ──
echo [2/6] Checking Git...
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Git not found. Installing via winget...
    winget install Git.Git --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo   ERROR: Failed to install Git. Install manually from git-scm.com
        pause
        exit /b 1
    )
    set PATH=C:\Program Files\Git\cmd;%PATH%
)
git --version
echo.

REM ── Clone/Update Repository ──
echo [3/6] Setting up CH8 Agent...
if exist "%INSTALL_DIR%\.git" (
    echo   Repository exists. Pulling latest...
    cd /d "%INSTALL_DIR%"
    git pull origin main
) else (
    echo   Cloning repository...
    git clone %REPO% "%INSTALL_DIR%"
    cd /d "%INSTALL_DIR%"
)
echo.

REM ── Install Dependencies ──
echo [4/6] Installing Python dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet httpx psutil fastapi "uvicorn[standard]" pydantic
echo   Done.
echo.

REM ── Configure Environment ──
echo [5/6] Configuring environment...
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

REM AI Config
echo {"provider":"bedrock","model":"us.anthropic.claude-sonnet-4-5-20250929-v1:0","aws_region":"us-east-1"}> "%CONFIG_DIR%\ai.json"

REM Environment variables - prompt for token
set /p BEDROCK_TOKEN="  Enter AWS_BEARER_TOKEN_BEDROCK: "
(
echo CLAUDE_CODE_USE_BEDROCK=1
echo AWS_REGION=us-east-1
echo AWS_BEARER_TOKEN_BEDROCK=%BEDROCK_TOKEN%
) > "%CONFIG_DIR%\env"

echo   AI: Bedrock / Claude Sonnet 4.5
echo   Region: us-east-1
echo   Config: %CONFIG_DIR%
echo.

REM ── Start Agent ──
echo [6/6] Starting CH8 Agent...
echo.
cd /d "%INSTALL_DIR%"
python ch8 up

echo.
echo  ════════════════════════════════════════════════════════════
echo   Installation complete!
echo   Agent directory: %INSTALL_DIR%
echo   Config directory: %CONFIG_DIR%
echo.
echo   Commands:
echo     python ch8 status   - Check status
echo     python ch8 up       - Start agent
echo     python ch8 down     - Stop agent
echo     python ch8 update   - Update to latest version
echo     python ch8 doctor   - Diagnose issues
echo  ════════════════════════════════════════════════════════════
echo.
pause
