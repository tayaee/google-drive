@echo off
setlocal
chcp 65001 > nul

echo ============================================================
echo   Google Drive CLI Tool Installer (uv tool)
echo ============================================================

where uv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Error: 'uv' is not installed or not in your PATH.
    echo Please install uv first: https://astral.sh/uv
    echo Powershell: iwr https://astral.sh/uv/install.ps1 -useb ^| iex
    pause
    exit /b 1
)

echo [*] Installing google-drive as uv tool...
uv tool install --force --reinstall .

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo [SUCCESS] google-drive has been installed!
    echo ============================================================
    echo You can now run the following commands anywhere in terminal:
    echo   google-drive --help
    echo   google-drive mount
    echo   google-drive mount "RemoteFolderName"
    echo   google-drive list
    echo ============================================================
) else (
    echo.
    echo [ERROR] Installation failed. Please check error messages above.
)

pause
