@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

echo Starting AI Taiwan Stock Strategy Advisor...
echo Project path: %CD%
echo.

"%PYTHON_EXE%" -c "import streamlit, pandas, numpy, requests" >nul 2>nul
if errorlevel 1 (
    echo Required packages are missing. Installing from requirements.txt...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Package installation failed. Please check Python and network settings.
        pause
        exit /b 1
    )
)

"%PYTHON_EXE%" -c "import json; c=json.load(open('config.json', encoding='utf-8')); raise SystemExit(0 if c.get('auto_update_prices_on_launch', True) is True else 1)" >nul 2>nul
if not errorlevel 1 (
    echo Updating price data from FinMind before opening app...
    "%PYTHON_EXE%" update_prices.py
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

"%PYTHON_EXE%" -m streamlit run "%CD%\app.py" --server.port 8501 --server.headless true --browser.gatherUsageStats false

echo.
echo App stopped.
pause
