@echo off
setlocal
chcp 65001 > nul

echo ============================================================
echo   WebClient Configuration Fixer
echo   - BasicAuthLevel: 2 (Enables HTTP WebDAV drive mounting)
echo   - FileSizeLimitInBytes: 4GB (Max transfer limit)
echo ============================================================
echo.

:: 1. Check administrator privileges and self-elevate (UAC)
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [*] Administrator privileges required to modify registry and restart service.
    echo [*] Requesting UAC elevation...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

set "REG_KEY=HKLM\SYSTEM\CurrentControlSet\Services\WebClient\Parameters"

:: 2. Display current values
echo [1] Current registry values:
echo ------------------------------------------------------------
reg query "%REG_KEY%" /v BasicAuthLevel 2>nul
reg query "%REG_KEY%" /v FileSizeLimitInBytes 2>nul
echo ------------------------------------------------------------
echo.

:: 3. Update BasicAuthLevel to 2
echo [2] Setting BasicAuthLevel to 2 (enables HTTP WebDAV)...
reg add "%REG_KEY%" /v BasicAuthLevel /t REG_DWORD /d 2 /f
if %ERRORLEVEL% NEQ 0 (
    echo [!] Failed to update BasicAuthLevel!
    pause
    exit /b %ERRORLEVEL%
)

:: 4. Update FileSizeLimitInBytes to 4GB
echo [3] Setting FileSizeLimitInBytes to 4GB (4294967295)...
reg add "%REG_KEY%" /v FileSizeLimitInBytes /t REG_DWORD /d 4294967295 /f
if %ERRORLEVEL% NEQ 0 (
    echo [!] Failed to update FileSizeLimitInBytes!
    pause
    exit /b %ERRORLEVEL%
)
echo.

:: 5. Display updated values
echo [4] Updated registry values:
echo ------------------------------------------------------------
reg query "%REG_KEY%" /v BasicAuthLevel
reg query "%REG_KEY%" /v FileSizeLimitInBytes
echo ------------------------------------------------------------
echo.

:: 6. Restart WebClient service
echo [5] Restarting WebClient service...
echo [*] net stop WebClient
net stop WebClient
echo [*] net start WebClient
net start WebClient

echo.
echo ============================================================
echo [DONE] BasicAuthLevel=2 and FileSizeLimitInBytes=4GB applied!
echo ============================================================
echo.
pause
