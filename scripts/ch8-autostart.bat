@echo off
REM ═══════════════════════════════════════════════════════════
REM  CH8 Agent - Auto-start on Windows boot
REM  Creates a Scheduled Task that runs ch8 up at login
REM ═══════════════════════════════════════════════════════════

set INSTALL_DIR=%USERPROFILE%\ch8-agent

echo Creating scheduled task for CH8 Agent auto-start...

schtasks /create /tn "CH8 Agent" /tr "python \"%INSTALL_DIR%\ch8\" up" /sc onlogon /rl highest /f

if %errorlevel% equ 0 (
    echo.
    echo  OK: CH8 Agent will start automatically on login.
    echo  Task name: "CH8 Agent"
    echo.
    echo  To remove: schtasks /delete /tn "CH8 Agent" /f
) else (
    echo.
    echo  ERROR: Failed to create task. Run as Administrator.
)

pause
