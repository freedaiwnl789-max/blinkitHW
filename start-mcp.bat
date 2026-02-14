@echo off
setlocal enabledelayedexpansion

REM Get the directory where this script is located
cd /d "%~dp0"

REM Find uv in the system PATH
for /f "delims=" %%i in ('where uv 2^>nul') do set "UV_PATH=%%i"

if not defined UV_PATH (
    echo [ERROR] uv not found in PATH. Installing...
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    REM Refresh PATH
    for /f "delims=" %%i in ('where uv 2^>nul') do set "UV_PATH=%%i"
)

if not defined UV_PATH (
    echo [ERROR] Failed to install uv. Please install manually.
    pause
    exit /b 1
)

echo [OK] uv found at: %UV_PATH%

REM Sync dependencies
echo [OK] Syncing dependencies...
"%UV_PATH%" sync --frozen
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to sync dependencies
    pause
    exit /b 1
)

REM Install Playwright if needed
set PLAYWRIGHT_DIR=%APPDATA%\ms-playwright
if not exist "%PLAYWRIGHT_DIR%" (
    echo [OK] Installing Playwright browsers...
    "%UV_PATH%" run playwright install chromium
    if %ERRORLEVEL% neq 0 (
        echo [WARN] Playwright install had issues, but continuing...
    )
)

REM Run the MCP server
echo [OK] Starting Blinkit MCP Server...
"%UV_PATH%" run main.py