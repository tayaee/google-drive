@echo off
setlocal
chcp 65001 > nul

where google-drive >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    google-drive status %*
) else (
    uv run google-drive status %*
)
pause
