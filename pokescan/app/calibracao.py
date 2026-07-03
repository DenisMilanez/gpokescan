# -*- coding: utf-8 -*-
"""
Calibracao da tela de jogo (roda 1x por aparelho).

Fluxo (11 passos):
  1. Confere conexao e le a resolucao (wm size).
  2. Print da tela atual (pagina do card).
  3. Acha a bola laranja (icone PokeGenie) por cor; salva template + posicao.
     Se nao achar -> informa e ABORTA.
  4. Acha a bola azul com 3 listras (botao de menu); salva template + posicao.
  5. Clica na bola laranja (ponto humanizado) e espera 1.0-1.6s.
  6. Print da tela de resultado do PokeGenie.
  7. Acha o botao X (circulo + 2 diagonais); salva template + posicao.
  8. Delimita o card branco de resultado (topo/base).
  9. Salva o perfil e clica no X para fechar.
 10. Clica no botao de menu, espera 0.5-1.0s e tira print.
 11. Localiza o texto 'AVALIAR' (OCR) nesse print; salva template + posicao.
"""

import json
import random
import time
from pathlib import Path

import cv2

import detectar_icone
import imgio
import visao

DIR_CALIB = Path(__file__).resolve().parent / "calibracao"


def _roi_icone(w, h):
    return (int(0.5 * w), 0, w, int(0.5 * h))       # quad_sup_dir


def _roi_x(w, h):
    return (0, 0, int(0.40 * w), int(0.40 * h))     # sup-esquerdo


def _roi_menu(w, h):
    return (0, int(0.5 * h), w, h)                   # metade inferior


def _pausa(a, b):
    time.sleep(random.uniform(a, b))


def _salvar_perfil(perfil, w, h, log):
    (DIR_CALIB / f"perfil_{w}x{h}.json").write_text(
        json.dumps(perfil, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Perfil salvo: perfil_{w}x{h}.json")


def iniciar(conn, log=print):
    log("=== Calibracao da tela ===")
    # 1) conexao + resolucao
    ok, resumo = conn.verificar_conexao()
    if not ok:
        log(f"Abortada: sem device. {resumo}")
        return False
    if not conn.wm_size:
        log("Abortada: resolucao desconhecida (wm size).")
        return False
    w, h = conn.wm_size
    DIR_CALIB.mkdir(parents=True, exist_ok=True)
    perfil = {"largura": w, "altura": h}

    # 2) print da pagina do card
    tela1 = DIR_CALIB / f"_ref_card_{w}x{h}.png"
    ok, msg = conn.screencap(tela1)
    if not ok:
        log(f"Falha na captura: {msg}"); return False
    img1 = imgio.imread(tela1)

    # 3) bola laranja (icone PokeGenie) -> ABORTA se nao achar
    det = detectar_icone.detectar(img1, roi_prioritaria=_roi_icone(w, h))
    if not det:
        log("ERRO: icone do PokeGenie (bola laranja) nao encontrado. "
            "Deixe o icone visivel na tela do card e refaca. Abortando.")
        return False
    log(f"Bola laranja em ({det['x']},{det['y']}) r={det['r']} score={det['score']}")
    tpl_i, msk_i = f"tpl_icone_{w}x{h}.png", f"tpl_icone_mask_{w}x{h}.png"
    visao.salvar_template_icone(img1, det["x"], det["y"], det["r"],
                                DIR_CALIB / tpl_i, DIR_CALIB / msk_i)
    perfil["icone_pokegenie"] = {
        "x": det["x"], "y": det["y"], "r": det["r"],
        "rel_x": round(det["x"] / w, 5), "rel_y": round(det["y"] / h, 5),
        "template": tpl_i, "mask": msk_i, "metodo": "cor_hsv + template"}

    # 4) bola azul com 3 listras (botao de menu) na propria pagina do card
    menu = visao.detectar_botao_menu(img1, _roi_menu(w, h))
    if menu:
        log(f"Botao menu em ({menu['x']},{menu['y']}) r={menu['r']} "
            f"horizontais={menu['horizontais']}")
        tpl_m, msk_m = f"tpl_menu_{w}x{h}.png", f"tpl_menu_mask_{w}x{h}.png"
        visao.salvar_template_circular(img1, menu["x"], menu["y"], menu["r"],
                                       DIR_CALIB / tpl_m, DIR_CALIB / msk_m)
        perfil["botao_menu"] = {
            "x": menu["x"], "y": menu["y"], "r": menu["r"],
            "rel_x": round(menu["x"] / w, 5), "rel_y": round(menu["y"] / h, 5),
            "template": tpl_m, "mask": msk_m,
            "metodo": "hough_circulo + 3 linhas horizontais"}
    else:
        log("AVISO: botao de menu (3 listras) nao encontrado no card. "
            "Passos 10-11 (AVALIAR) serao pulados.")

    # 5) clica na bola laranja e espera abrir
    zona = detectar_icone.zona_clique(det, img1)
    px, py = detectar_icone.ponto_clique(zona)
    log(f"Clicando na bola laranja em ({px},{py})...")
    conn.tap(px, py)
    _pausa(1.0, 1.6)

    # 6) print da tela de resultado
    tela2 = DIR_CALIB / f"_ref_resultado_{w}x{h}.png"
    ok, msg = conn.screencap(tela2)
    if not ok:
        log(f"Falha na captura do resultado: {msg}"); return False
    img2 = imgio.imread(tela2)

    # 7) botao X -> ABORTA se nao achar
    x = visao.detectar_botao_x(img2, _roi_x(w, h))
    if not x:
        log("ERRO: botao X nao encontrado na tela de resultado. Abortando.")
        return False
    log(f"Botao X em ({x['x']},{x['y']}) r={x['r']} diagonais={x['diagonais']}")
    tpl_x, msk_x = f"tpl_x_{w}x{h}.png", f"tpl_x_mask_{w}x{h}.png"
    visao.salvar_template_circular(img2, x["x"], x["y"], x["r"],
                                   DIR_CALIB / tpl_x, DIR_CALIB / msk_x)
    perfil["botao_x"] = {
        "x": x["x"], "y": x["y"], "r": x["r"],
        "rel_x": round(x["x"] / w, 5), "rel_y": round(x["y"] / h, 5),
        "template": tpl_x, "mask": msk_x, "metodo": "hough_circulo + 2 diagonais"}

    # 8) delimita o card branco (topo/base)
    bloco = visao.delimitar_bloco(img2)
    if bloco:
        perfil["bloco_resultado"] = {
            "topo": bloco["topo"], "base": bloco["base"],
            "rel_topo": round(bloco["topo"] / h, 4),
            "rel_base": round(bloco["base"] / h, 4),
            "metodo": "projecao de linhas (branco/cor)"}
        log(f"Card branco: topo={bloco['topo']} base={bloco['base']}")
    else:
        log("AVISO: nao delimitei o card branco.")

    # 9) salva o perfil e fecha no X
    _salvar_perfil(perfil, w, h, log)
    zx = (x["x"], x["y"], x["r"] * 0.7)
    cxp, cyp = detectar_icone.ponto_clique(zx)
    log(f"Fechando no X em ({cxp},{cyp})...")
    conn.tap(cxp, cyp)
    _pausa(0.5, 0.9)                       # espera voltar pra pagina do card

    # 10-11) menu -> AVALIAR (so se o menu foi encontrado no passo 4)
    if "botao_menu" in perfil:
        mx, my, mr = perfil["botao_menu"]["x"], perfil["botao_menu"]["y"], perfil["botao_menu"]["r"]
        tmx, tmy = detectar_icone.ponto_clique((mx, my, mr * 0.7))
        log(f"Clicando no menu em ({tmx},{tmy})...")
        conn.tap(tmx, tmy)
        _pausa(0.5, 1.0)
        tela3 = DIR_CALIB / f"_ref_menu_{w}x{h}.png"
        ok, msg = conn.screencap(tela3)
        if ok:
            img3 = imgio.imread(tela3)
            av = visao.localizar_texto(img3, "AVALIAR", _roi_menu(w, h))
            if av:
                crop = img3[av["y0"]:av["y1"], av["x0"]:av["x1"]]
                tpl_av = f"tpl_avaliar_{w}x{h}.png"
                imgio.imwrite(DIR_CALIB / tpl_av, crop)
                perfil["texto_avaliar"] = {
                    "x0": av["x0"], "y0": av["y0"], "x1": av["x1"], "y1": av["y1"],
                    "cx": av["cx"], "cy": av["cy"],
                    "rel_cx": round(av["cx"] / w, 5), "rel_cy": round(av["cy"] / h, 5),
                    "template": tpl_av, "metodo": "OCR (tesseract) + folga horizontal"}
                _salvar_perfil(perfil, w, h, log)      # re-salva com AVALIAR
                log(f"AVALIAR em ({av['cx']},{av['cy']}) -> template salvo.")
            else:
                log("AVISO: 'AVALIAR' nao localizado (tesseract instalado? "
                    "instale tesseract-ocr). Passo 11 pulado.")
        else:
            log(f"AVISO: falha ao capturar a tela do menu: {msg}")

    log("Calibracao concluida.")
    return True


def carregar_perfil(w, h):
    """Le o perfil de um aparelho (resolucao), ou None se nao existir."""
    p = DIR_CALIB / f"perfil_{w}x{h}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None
