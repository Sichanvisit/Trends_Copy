@echo off
chcp 65001 > nul
title X Content Workbench Dashboard Launcher
echo ============================================================
echo   Starting X Content Workbench Premium Dashboard...
echo ============================================================
echo.
echo   [*] Launching FastAPI server on http://127.0.0.1:8000...
echo   [*] Automatically opening your default web browser...
echo.
echo ============================================================
echo   To stop the server, press Ctrl+C in this window.
echo ============================================================
echo.
start http://127.0.0.1:8000
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe main.py --web
) else (
    python main.py --web
)
pause
