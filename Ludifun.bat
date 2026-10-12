@echo off
rem Ludifun : double-cliquer sur ce fichier (Windows). Un menu propose toutes les actions :
rem demarrer, arreter, mettre a jour, choisir l IA, sauvegarder, restaurer...
cd /d "%~dp0"
:menu
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\menu.ps1"
if errorlevel 3 goto menu
if errorlevel 1 pause
exit /b 0
