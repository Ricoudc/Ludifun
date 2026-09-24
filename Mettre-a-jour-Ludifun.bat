@echo off
rem Mettre a jour Ludifun : double-cliquer sur ce fichier (Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\mettre-a-jour.ps1"
if errorlevel 1 pause
