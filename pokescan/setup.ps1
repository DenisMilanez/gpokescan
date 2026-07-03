# ============================================================
#  PokeScan - Setup do ambiente virtual (.venv) - PowerShell
#  Uso:  powershell -ExecutionPolicy Bypass -File setup.ps1
# ============================================================
Set-Location -Path $PSScriptRoot

Write-Host "[1/3] Criando ambiente virtual .venv ..." -ForegroundColor Cyan
python -m venv .venv
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: Python nao encontrado. Instale o Python 3.10+." -ForegroundColor Red
    exit 1
}

Write-Host "[2/3] Atualizando pip ..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip

Write-Host "[3/3] Instalando dependencias (requirements.txt) ..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host ""
Write-Host "Setup concluido. Rode run.bat (ou: .\.venv\Scripts\python.exe app\gui.py)" -ForegroundColor Green
