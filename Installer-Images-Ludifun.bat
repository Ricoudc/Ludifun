@echo off
rem Installer le moteur d'images de Ludifun (facultatif) : double-cliquer sur ce fichier (Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\installer-images.ps1"
if errorlevel 1 pause
