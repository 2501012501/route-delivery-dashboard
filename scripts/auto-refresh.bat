@echo off
REM Auto-refresh job for Route to Delivery dashboard.
REM Runs RouteToDelivery.py + git auto-publish so the public Streamlit Cloud
REM URL stays fresh without anyone clicking buttons. Requires Falcon VPN.
REM Hand off to Windows Task Scheduler — see scripts\install-scheduled-task.ps1.

setlocal
cd /d "%~dp0\.."

REM Logs live OUTSIDE OneDrive — OneDrive sync was locking the file mid-append
REM and silently dropping every >> redirect. %LOCALAPPDATA% is local-only.
set LOG_DIR=%LOCALAPPDATA%\RouteToDelivery\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set LOG_FILE=%LOG_DIR%\auto-refresh.log

echo. >> "%LOG_FILE%"
echo === %DATE% %TIME% === >> "%LOG_FILE%"

REM -u = unbuffered stdout/stderr so the log file shows progress live
python -u RouteToDelivery.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo RouteToDelivery.py FAILED >> "%LOG_FILE%"
    exit /b 1
)

git add "Route To Delivery Data" data >> "%LOG_FILE%" 2>&1
git diff --cached --quiet
if not errorlevel 1 (
    echo No data changes to publish. >> "%LOG_FILE%"
    exit /b 0
)

for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm'"') do set TS=%%i
git commit -m "Auto: scheduled data update %TS%" >> "%LOG_FILE%" 2>&1
git push origin main >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo git push FAILED >> "%LOG_FILE%"
    exit /b 1
)

echo OK >> "%LOG_FILE%"
endlocal
