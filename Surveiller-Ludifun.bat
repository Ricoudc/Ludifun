@echo off
rem Surveiller Ludifun pendant un essai (journal, IA, carte graphique), a envoyer a Claude : double-cliquer (Windows).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\surveiller.ps1"
if errorlevel 1 pause
