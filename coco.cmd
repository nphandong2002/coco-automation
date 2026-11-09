@echo off
rem Coco Automation launcher for Windows:  coco start | stop | restart | status | logs | open | backup | restore | autostart | firewall
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\coco.ps1" %*
