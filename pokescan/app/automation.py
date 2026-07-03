# -*- coding: utf-8 -*-
"""
Automacao PokeScan (STUB).

Aqui entrara a automacao real: capturar screenshots do PokeGenie no Pokemon GO,
processar as imagens (CP, IVs, moves...) e alimentar a analise da colecao.

Por enquanto e apenas um esqueleto chamado pelo botao PLAY da GUI, para validar
que a conexao ja funciona antes de seguirmos para a automacao.
"""


def iniciar(conn, log):
    """
    Ponto de entrada da automacao.

    Parametros:
      conn : ADBConnector ja configurado (adb_path + log).
      log  : funcao de log (escreve na GUI).
    """
    log("=== Automacao (stub) ===")
    ok, resumo = conn.verificar_conexao()
    if not ok:
        log(f"Automacao abortada: sem device. {resumo}")
        return
    log(f"Device pronto: {resumo}")
    if conn.wm_size:
        log(f"Resolucao da tela: {conn.wm_size[0]}x{conn.wm_size[1]} "
            f"(usada para normalizar toques).")
    log("Automacao ainda nao implementada — proximo passo do projeto.")
    # TODO: abrir PokeGenie, disparar capturas, salvar screenshots, processar imagens.
