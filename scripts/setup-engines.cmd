@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-engines.ps1"
if errorlevel 1 exit /b %errorlevel%
