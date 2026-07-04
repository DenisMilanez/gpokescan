@echo off
REM ============================================================
REM  PokeScan - Atualiza o dashboard (do CSV mais recente em
REM  app\exports) e abre o HTML no navegador padrao.
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente .venv nao encontrado. Rode setup.bat primeiro.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" app\gerar_dashboard.py
if errorlevel 1 (
    echo Falha ao gerar o dashboard.
    pause
    exit /b 1
)

start "" "dashboard\dashboard.html"
