# -*- coding: utf-8 -*-
"""
Captura a tela ATUAL do celular e salva como MODELO de calibracao.

Uso (com o celular ja conectado pela GUI, e a janela desejada aberta na tela):
    .venv\\Scripts\\python.exe capturar_modelo.py
    (opcional) ... capturar_modelo.py nome_do_modelo

Salva em calibração/modelo_<nome>_<w>x<h>.png. A dimensao no nome identifica o
aparelho. Reaproveita a config salva (adb_path, ip) do config.json.
"""

import sys
from pathlib import Path

import config_store
from adb_connect import ADBConnector, PORTA_FIXA

DIR_CALIB = Path(__file__).resolve().parent / "calibracao"


def main():
    nome = sys.argv[1] if len(sys.argv) > 1 else "captura"
    cfg = config_store.carregar()

    conn = ADBConnector(cfg.get("adb_path", ""), log=print)
    ok, info = conn.testar_adb()
    if not ok:
        print(f"[ERRO] adb indisponivel: {info}")
        return
    print(f"adb OK: {info}")

    # Garante conexao: tenta o que ja estiver ligado; senao, ip:5555 salvo
    ok, resumo = conn.verificar_conexao()
    if not ok and cfg.get("ip"):
        print("Sem device ativo; tentando reconectar na 5555 salva...")
        conn.conectar(cfg["ip"], PORTA_FIXA)
        ok, resumo = conn.verificar_conexao()
    if not ok:
        print(f"[ERRO] nao conectado. Abra a GUI e conecte primeiro. {resumo}")
        return
    print(f"[OK] {resumo}")

    w, h = conn.wm_size
    DIR_CALIB.mkdir(parents=True, exist_ok=True)
    destino = DIR_CALIB / f"{nome}_{w}x{h}.png"
    ok, msg = conn.screencap(destino)
    if ok:
        print(f"Modelo salvo: {destino}")
    else:
        print(f"[ERRO] falha na captura: {msg}")


if __name__ == "__main__":
    main()
