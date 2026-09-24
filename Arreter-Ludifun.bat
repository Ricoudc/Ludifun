@echo off
rem Arreter Ludifun : double-cliquer sur ce fichier (Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\arreter.ps1"
if errorlevel 1 pause
