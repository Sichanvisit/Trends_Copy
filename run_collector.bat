@echo off
chcp 65001 > nul
title X Content Workbench Auto Collector
echo ============================================================
echo   Running X Content Workbench Auto Collector...
echo ============================================================
echo.
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe collect_all.py
) else (
    python collect_all.py
)
echo.
echo ============================================================
echo   Collection Complete! Press any key to exit.
echo ============================================================
pause > nul
