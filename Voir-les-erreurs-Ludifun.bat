@echo off
rem Voir l etat et les erreurs du serveur : double-cliquer sur ce fichier (Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\erreurs.ps1"
if errorlevel 1 pause
