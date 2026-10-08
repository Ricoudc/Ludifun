@echo off
rem Sauvegarder les donnees de Ludifun : double-cliquer sur ce fichier (Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\sauvegarder.ps1"
if errorlevel 1 pause
