@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Start.ps1"
if errorlevel 1 pause
