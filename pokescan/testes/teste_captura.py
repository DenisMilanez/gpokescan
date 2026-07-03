# -*- coding: utf-8 -*-
"""
PokeScan - Teste de captura (5 ciclos)

Objetivo do teste: com o Pokemon GO aberto e o PokeGenie sobreposto, para cada
ciclo:
    1) tira o print (numerado 1, 2, 3, ... n+1) -> pasta capturas/
    2) desliza o dedo pro lado (direita -> esquerda) pra ir ao proximo alvo

Repete 5 vezes. E so um smoke test — deixa a janela ja preparada no celular.

--- Sobre "nao parecer bot" ---
O 'input swipe' puro e uma reta perfeita com duracao fixa (facil de detectar).
Aqui humanizamos o gesto:
  - ponto de inicio/fim com jitter aleatorio (nunca no mesmo pixel);
  - duracao do deslize variavel (nao e sempre igual);
  - pausas irregulares entre ciclos (nao e um ritmo de metronomo).
Observacao honesta: isso ja disfarça bastante. O nivel mais alto de realismo
(curva do dedo com varios pontos e velocidade nao-linear) exige 'sendevent',
que e mais fragil; se precisar, dá pra evoluir depois.
"""

import random
import time
from pathlib import Path

from adb_connect import ADBConnector

# ------------------------------------------------------------------ #
# CONFIG (edite aqui)
# ------------------------------------------------------------------ #
ADB_PATH = r"D:\platform-tools\adb.exe"   # ajuste se seu adb estiver em outro lugar
N_CICLOS = 5                               # quantas vezes repetir (teste)
PASTA_SAIDA = Path(__file__).resolve().parent / "capturas"

# Geometria do swipe em FRACAO da tela (0..1), independente da resolucao.
# Direita -> esquerda: comeca perto da borda direita e termina perto da esquerda.
SWIPE_Y = 0.55            # altura do deslize (meio da tela, levemente abaixo)
SWIPE_X_INI = 0.80        # inicio (direita)
SWIPE_X_FIM = 0.20        # fim (esquerda)

# Faixas de aleatoriedade (humanizacao)
JITTER_FRAC = 0.03        # +-3% da tela em cada ponto
DUR_SWIPE_MS = (220, 420)   # duracao do deslize, ms (min, max)
PAUSA_ENTRE = (0.7, 1.6)    # pausa entre ciclos, s (min, max)
PAUSA_POS_PRINT = (0.2, 0.5)  # pausinha depois do print, antes de deslizar


def jitter(valor_frac, largura_ou_altura):
    """Aplica jitter aleatorio (+-JITTER_FRAC) e converte fracao -> pixels."""
    f = valor_frac + random.uniform(-JITTER_FRAC, JITTER_FRAC)
    f = min(max(f, 0.02), 0.98)          # nunca encostar exatamente na borda
    return int(f * largura_ou_altura)


def main():
    conn = ADBConnector(ADB_PATH, log=print)

    # Garante que o adb responde e que ha um device conectado
    ok, info = conn.testar_adb()
    if not ok:
        print(f"[ERRO] adb indisponivel: {info}")
        return
    ok, resumo = conn.verificar_conexao()
    if not ok:
        print(f"[ERRO] sem device conectado. Rode a GUI e conecte primeiro. {resumo}")
        return
    print(f"[OK] {resumo}")

    if not conn.wm_size:
        print("[ERRO] nao obtive a resolucao da tela (wm size).")
        return
    largura, altura = conn.wm_size
    print(f"Resolucao: {largura}x{altura}")

    PASTA_SAIDA.mkdir(exist_ok=True)
    print(f"Salvando prints em: {PASTA_SAIDA}")

    for n in range(1, N_CICLOS + 1):
        # 1) PRINT (numerado n)
        destino = PASTA_SAIDA / f"{n}.png"
        ok, msg = conn.screencap(destino)
        if ok:
            print(f"[{n}/{N_CICLOS}] print salvo: {msg}")
        else:
            print(f"[{n}/{N_CICLOS}] FALHA no print: {msg}")

        # pausinha humana depois do print
        time.sleep(random.uniform(*PAUSA_POS_PRINT))

        # 2) SWIPE direita -> esquerda (com jitter e duracao variavel)
        x1 = jitter(SWIPE_X_INI, largura)
        x2 = jitter(SWIPE_X_FIM, largura)
        y1 = jitter(SWIPE_Y, altura)
        y2 = jitter(SWIPE_Y, altura)     # y do fim tambem varia (leve inclinacao)
        dur = random.randint(*DUR_SWIPE_MS)
        ok, msg = conn.swipe(x1, y1, x2, y2, dur)
        print(f"     swipe ({x1},{y1})->({x2},{y2}) {dur}ms "
              f"{'ok' if ok else 'FALHA: ' + msg}")

        # pausa irregular antes do proximo ciclo (nao no ultimo)
        if n < N_CICLOS:
            time.sleep(random.uniform(*PAUSA_ENTRE))

    print("Teste concluido.")


if __name__ == "__main__":
    main()
