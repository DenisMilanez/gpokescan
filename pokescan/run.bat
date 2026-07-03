@echo off
REM ============================================================
REM  PokeScan - Abre a GUI usando a venv (.venv)
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente .venv nao encontrado. Rode setup.bat primeiro.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" app\gui.py
