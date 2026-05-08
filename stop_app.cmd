@echo off
setlocal
chcp 65001 >nul

echo Stopping AI Taiwan Stock Strategy Advisor...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$project = (Get-Location).Path; $app = Join-Path $project 'app.py'; $pidPath = Join-Path $project 'output\app.pid'; $ids = @(); if (Test-Path $pidPath) { $stored = Get-Content $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1; $parsed = 0; if ([int]::TryParse($stored, [ref]$parsed)) { $ids += $parsed } }; $matches = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*streamlit*run*' -and $_.CommandLine -like ('*' + $app + '*') }; $ids += @($matches | ForEach-Object { $_.ProcessId }); $ids = $ids | Where-Object { $_ } | Select-Object -Unique; if (-not $ids) { Write-Host 'No matching Streamlit process found.'; if (Test-Path $pidPath) { Remove-Item $pidPath -Force }; exit 0 }; foreach ($id in $ids) { if (Get-Process -Id $id -ErrorAction SilentlyContinue) { Write-Host ('Stopping PID ' + $id); Stop-Process -Id $id -Force } }; if (Test-Path $pidPath) { Remove-Item $pidPath -Force }"

echo Done.
pause
