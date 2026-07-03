# -*- coding: utf-8 -*-
"""
Varredura GoPokeScan (o bot).

Para cada Pokemon (N vezes):
  1. Acha a bola laranja: 1o pelo template salvo (rapido); se nao achar, pela
     deteccao por cor; se ainda nao achar, ENCERRA dizendo o motivo.
  2. Clica nela (ponto humanizado).
  3. Bate o print e salva em capturas/<AAAA-MM-DD>/<n>.png.
  4. Verifica se o topo do card branco bate com a calibracao (tolerancia).
     Se nao bater, registra o numero da imagem em avisos.txt (entregue no fim).
  5. Clica no X para fechar.
  6. Desliza (swipe humanizado) para o proximo Pokemon.

Gestos humanizados (jitter, duracao/pausas variaveis) para nao parecer bot.
"""

import datetime
import math
import random
import time
from pathlib import Path

import cv2

import config_store
import detectar_icone
import gerar_swipe
import imgio
import swipe_injecao
import visao
from calibracao import carregar_perfil

DIR_BASE = Path(__file__).resolve().parent
DIR_CAPTURAS = DIR_BASE / "capturas"

# ---- swipe (fracao da tela) ----
SWIPE_Y, SWIPE_X_INI, SWIPE_X_FIM = 0.55, 0.80, 0.20
JITTER_FRAC = 0.03
DUR_SWIPE_MS = (220, 420)
PAUSA_ENTRE = (0.2, 2.0)       # intervalo entre ciclos
PAUSA_RENDER = (0.5, 1.5)      # espera a pagina do PokeGenie abrir
PAUSA_POS_X = (0.3, 0.8)       # espera fechar apos o X
PAUSA_MENU = (0.5, 0.8)        # apos clicar no botao de menu
PAUSA_AVALIAR = (0.2, 0.8)     # apos clicar em AVALIAR
PAUSA_AVALIAR_GENIE = (0.4, 0.8)  # apos o clique inferior, antes de clicar no icone Genie
# Os valores acima sao apenas fallback; os efetivos vem de config_store (secao "coleta")


def _jitter(frac, dim):
    f = frac + random.uniform(-JITTER_FRAC, JITTER_FRAC)
    return int(min(max(f, 0.02), 0.98) * dim)


def _roi_icone(w, h):
    return (int(0.5 * w), 0, w, int(0.5 * h))


def _roi_x(w, h):
    return (0, 0, int(0.40 * w), int(0.40 * h))


def _achar_icone(img, perfil, w, h, log):
    """Template salvo -> deteccao por cor. Retorna det {x,y,r} ou None."""
    ic = perfil.get("icone_pokegenie", {})
    roi = _roi_icone(w, h)
    if ic.get("template"):
        m = visao.localizar_template(
            img, DIR_CALIB / ic["template"],
            DIR_CALIB / ic.get("mask", ""), roi, limiar=0.6)
        if m:
            return {"x": m["x"], "y": m["y"], "r": ic.get("r", 17), "via": "template"}
    det = detectar_icone.detectar(img, roi_prioritaria=roi)
    if det:
        det["via"] = "cor"
        return det
    return None


def _roi_menu(w, h):
    return (0, int(0.5 * h), w, h)                   # metade inferior


def _grab_mem(conn):
    """Print da tela SO NA MEMORIA (nao grava arquivo). Retorna img BGR ou None."""
    raw = conn.screencap_bytes()
    return imgio.imdecode(raw) if raw else None


def _tap_inferior(conn, w, h):
    """Clique simples em um ponto aleatorio da metade inferior da tela."""
    x = random.randint(int(0.20 * w), int(0.80 * w))
    y = random.randint(int(0.55 * h), int(0.90 * h))
    conn.tap(x, y)


def _menu_avaliar(conn, img, perfil, w, h, log, pausas=None):
    """
    Se o botao de menu (3 barras) aparecer no print: clica no menu -> AVALIAR ->
    clique simples na metade inferior. SO executa se o menu for localizado.
    'pausas' e um dict opcional com os ranges efetivos (pausa_menu, pausa_avaliar,
    pausa_avaliar_genie); se omitido, usa os fallbacks do modulo.
    Retorna True se rodou a sequencia.
    """
    if pausas is None:
        pausas = {
            "pausa_menu": PAUSA_MENU,
            "pausa_avaliar": PAUSA_AVALIAR,
            "pausa_avaliar_genie": PAUSA_AVALIAR_GENIE,
        }
    menu = visao.detectar_botao_menu(img, _roi_menu(w, h))
    if not menu:
        return False
    mx, my = detectar_icone.ponto_clique((menu["x"], menu["y"], menu["r"] * 0.7))
    log(f"    menu detectado -> clicando em ({mx},{my})")
    conn.tap(mx, my)
    time.sleep(random.uniform(*pausas["pausa_menu"]))
    av = perfil.get("texto_avaliar")
    if av:
        conn.tap(av["cx"], av["cy"])                 # AVALIAR (posicao da calibracao)
        time.sleep(random.uniform(*pausas["pausa_avaliar"]))
        _tap_inferior(conn, w, h)                    # dispensa com clique inferior
        time.sleep(random.uniform(*pausas["pausa_avaliar_genie"]))
    else:
        log("    AVISO: 'texto_avaliar' nao esta no perfil; AVALIAR pulado.")
    return True


def _achar_x(img, perfil, w, h):
    """Template salvo -> geometria -> posicao fixa da calibracao."""
    bx = perfil.get("botao_x", {})
    roi = _roi_x(w, h)
    if bx.get("template"):
        m = visao.localizar_template(
            img, DIR_CALIB / bx["template"],
            DIR_CALIB / bx.get("mask", ""), roi, limiar=0.6)
        if m:
            return m["x"], m["y"], bx.get("r", 60)
    g = visao.detectar_botao_x(img, roi)
    if g:
        return g["x"], g["y"], g["r"]
    if "x" in bx:  # fallback: posicao fixa salva (o X nao se move)
        return bx["x"], bx["y"], bx.get("r", 60)
    return None


# DIR_CALIB e resolvido a partir do modulo calibracao para casar os caminhos
DIR_CALIB = DIR_BASE / "calibracao"
DIR_SWIPE = DIR_CALIB / "swipe_horizontal"


def _carregar_swipe(w, h, log):
    """Carrega o perfil de swipe humanizado (se existir). Retorna (perfil, touch)."""
    ps = DIR_SWIPE / "perfil_swipe.json"
    if not ps.exists():
        log("Sem perfil de swipe; usando swipe simples. Rode 'Calibrar Swipe Horizontal'.")
        return None, None
    try:
        perfil = gerar_swipe.carregar_perfil(ps)
    except Exception:
        return None, None
    if not perfil.get("largura"):
        perfil["largura"], perfil["altura"] = w, h
    log("Swipe humanizado ativo (perfil de gesto carregado).")
    return perfil, perfil.get("touch")


def executar(conn, n_ciclos, log=print, parar=None):
    ok, resumo = conn.verificar_conexao()
    if not ok:
        log(f"[ERRO] sem device. {resumo}"); return
    if not conn.wm_size:
        log("[ERRO] resolucao desconhecida."); return
    w, h = conn.wm_size

    # config de coleta (pausas humanizadas)
    cfg = config_store.carregar()["coleta"]
    pausa_menu = tuple(cfg.get("pausa_menu", PAUSA_MENU))
    pausa_avaliar = tuple(cfg.get("pausa_avaliar", PAUSA_AVALIAR))
    pausa_avaliar_genie = tuple(cfg.get("pausa_avaliar_genie", PAUSA_AVALIAR_GENIE))
    pausa_render = tuple(cfg.get("pausa_render", PAUSA_RENDER))
    pausa_pos_x = tuple(cfg.get("pausa_pos_x", PAUSA_POS_X))
    pausa_entre = tuple(cfg.get("pausa_entre", PAUSA_ENTRE))
    descanso_ciclos_min, descanso_ciclos_max = tuple(cfg.get("descanso_ciclos", (5, 30)))
    descanso_ciclos_min = int(descanso_ciclos_min)
    descanso_ciclos_max = int(descanso_ciclos_max)
    descanso_segundos = tuple(cfg.get("descanso_segundos", (2.0, 30.0)))
    descanso_ativo = descanso_ciclos_max >= 1
    proximo_descanso = (
        random.randint(descanso_ciclos_min, descanso_ciclos_max) if descanso_ativo else None)
    pausas_menu_avaliar = {
        "pausa_menu": pausa_menu,
        "pausa_avaliar": pausa_avaliar,
        "pausa_avaliar_genie": pausa_avaliar_genie,
    }

    perfil = carregar_perfil(w, h)
    if not perfil:
        log(f"[ERRO] sem calibracao para {w}x{h}. Rode 'Calibrar Tela de Jogo' antes.")
        return
    topo_calib = perfil.get("bloco_resultado", {}).get("topo")
    tol = max(12, int(0.006 * h))

    # perfil de swipe humanizado (gerado na hora a cada ciclo)
    perfil_swipe, touch_swipe = _carregar_swipe(w, h, log)

    # pasta do dia + relatorio de avisos
    dia = datetime.date.today().isoformat()          # AAAA-MM-DD
    pasta = DIR_CAPTURAS / dia
    pasta.mkdir(parents=True, exist_ok=True)
    avisos = pasta / "avisos.txt"
    lista_avisos = []

    log(f"Varredura: {n_ciclos} Pokemon | tela {w}x{h} | pasta {dia}")

    for n in range(1, int(n_ciclos) + 1):
        if parar is not None and parar.is_set():
            log("Interrompido pelo usuario."); break

        # 2) print da tela SO NA MEMORIA (para decisao/cliques; nao salva)
        img = _grab_mem(conn)
        if img is None:
            log(f"[{n}] falha ao capturar tela; encerrando."); break

        # 3) acha a bola laranja no print em memoria
        det = _achar_icone(img, perfil, w, h, log)
        if not det:
            log(f"[{n}] ENCERRANDO: bola laranja nao encontrada "
                "(PokeGenie nao esta aberto).")
            break

        # 4-5) se o botao de menu aparecer -> menu -> AVALIAR -> clique inferior
        _menu_avaliar(conn, img, perfil, w, h, log, pausas=pausas_menu_avaliar)

        # 6) clica na bola laranja (abre as infos do PokeGenie)
        zona = detectar_icone.zona_clique(det, img)
        px, py = detectar_icone.ponto_clique(zona)
        conn.tap(px, py)
        # 7) espera a pagina de resultado abrir
        time.sleep(random.uniform(*pausa_render))

        # 8) print do resultado -> SALVA numerado na pasta do dia
        destino = pasta / f"{n}.png"
        ok_cap, _ = conn.screencap(destino)
        res = imgio.imread(destino) if ok_cap else None
        if res is None:
            log(f"[{n}] falha ao capturar resultado; encerrando."); break

        # 4) verificacao: topo do card branco == calibracao?
        topo = visao.topo_bloco(res)
        if topo_calib is None:
            pass
        elif topo is None or abs(topo - topo_calib) > tol:
            msg = (f"imagem {n}.png: topo {topo} != calibracao {topo_calib} "
                   f"(tol {tol}px)")
            lista_avisos.append(msg)
            log(f"[{n}] AVISO: {msg}")
        else:
            log(f"[{n}] ok (via {det.get('via')}, topo {topo})")

        # 5) fecha no X (clique humanizado dentro do circulo)
        x = _achar_x(res, perfil, w, h)
        if x:
            cx, cy, r = x
            zx = (cx, cy, r * 0.7)
            tx, ty = detectar_icone.ponto_clique(zx)
            conn.tap(tx, ty)
        else:
            log(f"[{n}] AVISO: X nao encontrado para fechar.")
        time.sleep(random.uniform(*pausa_pos_x))

        # 6) swipe HUMANIZADO para o proximo Pokemon (gerado na hora)
        if n < int(n_ciclos):
            if perfil_swipe:
                pts = gerar_swipe.gerar(perfil_swipe, w, h)   # ~0.2ms, sempre diferente
                swipe_injecao.injetar(conn, touch_swipe, pts, w, h)
            else:
                conn.swipe(_jitter(SWIPE_X_INI, w), _jitter(SWIPE_Y, h),
                           _jitter(SWIPE_X_FIM, w), _jitter(SWIPE_Y, h),
                           random.randint(*DUR_SWIPE_MS))
            time.sleep(random.uniform(*pausa_entre))

        # descanso: a cada N ciclos (N sorteado no range configurado), pausa longa
        if descanso_ativo and n >= proximo_descanso and n < int(n_ciclos):
            t = random.uniform(*descanso_segundos)
            log(f"[{n}] descanso de {t:.0f}s...")
            fim = time.time() + t
            while time.time() < fim:
                if parar is not None and parar.is_set():
                    break
                time.sleep(min(0.5, fim - time.time()))
            if parar is not None and parar.is_set():
                log("Interrompido pelo usuario (durante descanso)."); break
            proximo_descanso = n + random.randint(descanso_ciclos_min, descanso_ciclos_max)

    # relatorio final
    if lista_avisos:
        avisos.write_text(
            "Imagens para conferir (topo do card fora da calibracao):\n"
            + "\n".join(lista_avisos) + "\n", encoding="utf-8")
        log(f"{len(lista_avisos)} aviso(s) salvos em {avisos}")
    else:
        log("Sem discrepancias de card.")
    log(f"Varredura concluida. Prints em: {pasta}")


def _grab(conn):
    """Captura a tela para um arquivo temporario e retorna a imagem (BGR)."""
    tmp = DIR_BASE / "_tmp_grab.png"
    ok, _ = conn.screencap(tmp)
    if not ok:
        return None
    return imgio.imread(tmp)
