@echo off
REM ═══════════════════════════════════════════════════════════
REM  CH8 Agent - Install global 'ch8' command on Windows
REM  After this, you can run: ch8 up, ch8 status, ch8 doctor
REM  from any directory
REM ═══════════════════════════════════════════════════════════

set INSTALL_DIR=%USERPROFILE%\ch8-agent
set CMD_DIR=%USERPROFILE%\AppData\Local\Microsoft\WindowsApps

echo.
echo Installing 'ch8' command globally...
echo.

REM Create ch8.cmd wrapper in PATH
(
echo @echo off
echo python "%INSTALL_DIR%\ch8" %%*
) > "%CMD_DIR%\ch8.cmd"

if %errorlevel% equ 0 (
    echo  Done! 'ch8' command installed.
    echo.
    echo  You can now run from anywhere:
    echo    ch8 up        - Start the agent
    echo    ch8 down      - Stop the agent
    echo    ch8 status    - Check cluster status
    echo    ch8 nodes     - List nodes
    echo    ch8 update    - Update to latest
    echo    ch8 doctor    - Diagnose issues
    echo    ch8 config ai - Configure AI provider
    echo.
) else (
    echo  Failed. Trying alternative location...
    if not exist "C:\ch8" mkdir "C:\ch8"
    (
    echo @echo off
    echo python "%INSTALL_DIR%\ch8" %%*
    ) > "C:\ch8\ch8.cmd"
    setx PATH "%PATH%;C:\ch8"
    echo  Installed to C:\ch8\ch8.cmd - restart terminal to use.
)

pause
