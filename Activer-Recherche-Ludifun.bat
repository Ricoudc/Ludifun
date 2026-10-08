@echo off
rem Activer la recherche sur les sites educatifs de confiance : double-cliquer sur ce fichier (Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\activer-recherche.ps1"
if errorlevel 1 pause
