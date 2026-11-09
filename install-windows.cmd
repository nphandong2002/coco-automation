@echo off
rem Double-click to install Coco Automation on Windows (no admin rights needed).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\install.ps1" %*
echo.
pause
