@echo off
rem Choisir l IA (cle Anthropic ou IA factice) : double-cliquer sur ce fichier (Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\changer-ia.ps1"
if errorlevel 1 pause
