@echo off
rem Rapport de diagnostic a coller dans la conversation avec Claude : double-cliquer (Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\rapport.ps1"
if errorlevel 1 pause
