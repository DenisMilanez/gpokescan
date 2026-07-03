@echo off
REM ============================================================
REM  PokeScan - Setup do ambiente virtual (.venv) no Windows
REM  Cria a venv, atualiza o pip e instala as dependencias.
REM ============================================================
cd /d "%~dp0"

echo [1/3] Criando ambiente virtual .venv ...
python -m venv .venv
if errorlevel 1 (
    echo ERRO: Python nao encontrado. Instale o Python 3.10+ e tente de novo.
    pause
    exit /b 1
)

echo [2/3] Atualizando pip ...
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip

echo [3/4] Instalando dependencias (requirements.txt) ...
pip install -r requirements.txt

echo [4/4] Verificando Tesseract OCR (necessario para localizar 'AVALIAR') ...
where tesseract >nul 2>nul
if errorlevel 1 (
    echo Tesseract nao encontrado. Tentando instalar via winget...
    winget install -e --id UB-Mannheim.TesseractOCR --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo.
        echo AVISO: nao consegui instalar o Tesseract automaticamente.
        echo O OCR do passo 'AVALIAR' pode nao funcionar. Instale manualmente:
        echo   https://github.com/UB-Mannheim/tesseract/wiki
    )
) else (
    echo Tesseract ja instalado.
)

echo.
echo Setup concluido. Rode run.bat para abrir a GUI.
pause
