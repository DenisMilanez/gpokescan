# -*- coding: utf-8 -*-
"""
Persistencia de configuracoes do GoPokeScan (config.json).

Guarda o que precisa sobreviver entre execucoes:
  - adb_path        : caminho do adb.exe
  - ip / porta      : ultimo IP e porta de conexao usados (para auto-conexao)
  - limite_colecao  : quantos Pokemon a varredura deve processar (nº de ciclos)

NAO guardamos o codigo de pareamento: ele expira e nao faz sentido persistir.
Os perfis por rede (SSID -> ip:5555) continuam no redes.json, gerido pela
camada de conexao.
"""

import json
from pathlib import Path

DIR_BASE = Path(__file__).resolve().parent
CONFIG_JSON = DIR_BASE / "config.json"

# Valores padrao caso ainda nao exista config salva
PADRAO = {
    "adb_path": r"D:\platform-tools\adb.exe",
    "ip": "",
    "porta": "",
    "limite_colecao": 50,
    "coleta": {
        "pausa_menu": [0.5, 0.8],        # apos clicar no menu (Pokemon GO)
        "pausa_avaliar": [0.2, 0.8],     # apos clicar em AVALIAR, antes do clique inferior
        "pausa_avaliar_genie": [0.4, 0.8],  # apos o clique inferior, antes de clicar no icone Genie
        "pausa_render": [0.5, 1.5],      # espera pagina de resultado do Genie abrir
        "pausa_pos_x": [0.3, 0.8],       # apos fechar no X
        "pausa_entre": [0.2, 2.0],       # entre ciclos (apos o swipe)
        "descanso_ciclos": [5, 30],      # a cada N ciclos (sorteado neste range) faz pausa longa; [0,0] = desativado
        "descanso_segundos": [2.0, 30.0],
    },
}


def carregar() -> dict:
    """Le config.json; devolve PADRAO mesclado com o que estiver salvo."""
    dados = dict(PADRAO)
    if CONFIG_JSON.exists():
        try:
            salvos = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
            if isinstance(salvos, dict):
                coleta_salva = salvos.pop("coleta", None)
                dados.update({k: v for k, v in salvos.items() if v is not None})
                # deep-merge de "coleta": mantem defaults para chaves ausentes
                coleta = dict(PADRAO["coleta"])
                if isinstance(coleta_salva, dict):
                    coleta_salva.pop("multiplicador", None)  # chave legada removida
                    v_ciclos = coleta_salva.get("descanso_ciclos")
                    if isinstance(v_ciclos, (int, float)) and not isinstance(v_ciclos, bool):
                        coleta_salva["descanso_ciclos"] = [v_ciclos, v_ciclos]
                    coleta.update(
                        {k: v for k, v in coleta_salva.items() if v is not None})
                dados["coleta"] = coleta
        except Exception:
            pass  # arquivo corrompido -> usa padrao
    return dados


def salvar(**campos) -> dict:
    """
    Atualiza apenas os campos informados e grava o config.json.
    Ex.: salvar(ip="192.168.0.5", porta="41069")
    Retorna o dicionario completo ja gravado.
    """
    dados = carregar()
    dados.update(campos)
    CONFIG_JSON.write_text(
        json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    return dados
