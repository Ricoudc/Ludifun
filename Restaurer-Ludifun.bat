@echo off
rem Remettre une sauvegarde de Ludifun : double-cliquer sur ce fichier (Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\restaurer.ps1"
if errorlevel 1 pause
