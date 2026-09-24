@echo off
rem Demarrer Ludifun : double-cliquer sur ce fichier (Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\demarrer.ps1"
if errorlevel 1 pause
