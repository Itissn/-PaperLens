@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-AI.ps1"
if errorlevel 1 pause
