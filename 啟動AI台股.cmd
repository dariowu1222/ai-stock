@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

set "PYTHON_EXE="
set "PYTHON_ARGS="

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
)

if not defined PYTHON_EXE (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
    )
)

if not defined PYTHON_EXE (
    for %%V in (312 311 310) do (
        if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
            set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        )
    )
)

if not defined PYTHON_EXE (
    echo Python 3 was not found. Please install Python first.
    pause
    exit /b 1
)

set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

echo Starting AI Taiwan Stock Strategy Advisor...
echo Project path: %CD%
echo.

call :run_python -c "import streamlit, pandas, numpy, requests, plotly, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo Required packages are missing. Installing from requirements.txt...
    call :run_python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Package installation failed. Please check Python and network settings.
        pause
        exit /b 1
    )
)

call :run_python -c "import json; c=json.load(open('config.json', encoding='utf-8')); raise SystemExit(0 if c.get('auto_update_prices_on_launch', True) is True else 1)" >nul 2>nul
if not errorlevel 1 (
    echo Updating price data from FinMind before opening app...
    call :run_python update_prices.py
    if errorlevel 1 (
        echo.
        echo Price update failed. Opening app with existing local CSV anyway.
        echo.
    ) else (
        echo Price update completed.
        echo.
    )
)

powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8501' -TimeoutSec 2; if ($r.StatusCode -ge 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 (
    echo App is already running. Opening browser...
    start "" "http://localhost:8501"
    exit /b 0
)

start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://localhost:8501'"

echo Browser will open at http://localhost:8501
echo Keep this window open while using the app.
echo Press Ctrl+C to stop the app.
echo.

call :run_python -m streamlit run "%CD%\app.py" --server.port 8501 --server.headless true --browser.gatherUsageStats false

echo.
echo App stopped.
pause

:run_python
if defined PYTHON_ARGS (
    "%PYTHON_EXE%" %PYTHON_ARGS% %*
) else (
    "%PYTHON_EXE%" %*
)
exit /b %errorlevel%
