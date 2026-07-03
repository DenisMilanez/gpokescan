# -*- coding: utf-8 -*-
"""
Utilitarios de visualizacao dos swipes: render de um gesto (colorido por
velocidade), montagem de uma pasta e geracao dos 20 testes.
Usado pela calibracao de swipe (captura + testes) e reutilizavel.
"""

import glob
import math
import os

import cv2
import numpy as np

import gerar_swipe
import imgio


def render_swipe(pontos, w, h, destino, titulo=""):
    """Desenha o gesto em fundo preto, traco colorido pela velocidade."""
    img = np.zeros((h, w, 3), np.uint8)
    if len(pontos) >= 2:
        vs = [math.hypot(pontos[i][1]-pontos[i-1][1], pontos[i][2]-pontos[i-1][2]) /
              max(pontos[i][0]-pontos[i-1][0], 1e-4) for i in range(1, len(pontos))]
        vmn, vmx = min(vs), max(vs); rng = (vmx - vmn) or 1.0
        for i in range(1, len(pontos)):
            c = cv2.applyColorMap(np.uint8([[int((vs[i-1]-vmn)/rng*255)]]),
                                  cv2.COLORMAP_JET)[0][0]
            cv2.line(img, (int(pontos[i-1][1]), int(pontos[i-1][2])),
                     (int(pontos[i][1]), int(pontos[i][2])),
                     (int(c[0]), int(c[1]), int(c[2])), 6, cv2.LINE_AA)
        cv2.circle(img, (int(pontos[0][1]), int(pontos[0][2])), 12, (0, 255, 0), -1)
        cv2.circle(img, (int(pontos[-1][1]), int(pontos[-1][2])), 12, (0, 0, 255), -1)
        dur = pontos[-1][0] - pontos[0][0]
        cv2.putText(img, f"{titulo}  dur={dur*1000:.0f}ms  pts={len(pontos)}",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    imgio.imwrite(destino, img)


def _janela(img, ww=760, wh=230, rotulo=""):
    """Recorta janela fixa centrada no gesto (escala real, sem auto-ampliar)."""
    m = img.max(axis=2) > 30; m[:100, :] = False
    ys, xs = np.where(m); out = np.zeros((wh, ww, 3), np.uint8)
    if len(xs) >= 5:
        cx, cy = int(xs.mean()), int(ys.mean()); x0, y0 = cx-ww//2, cy-wh//2
        sx0, sy0 = max(0, x0), max(0, y0)
        sx1, sy1 = min(img.shape[1], x0+ww), min(img.shape[0], y0+wh)
        out[sy0-y0:sy0-y0+(sy1-sy0), sx0-x0:sx0-x0+(sx1-sx0)] = img[sy0:sy1, sx0:sx1]
    cv2.rectangle(out, (0, 0), (ww-1, wh-1), (70, 70, 70), 1)
    if rotulo:
        cv2.putText(out, rotulo, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (210, 210, 210), 1, cv2.LINE_AA)
    return out


def montar(dir_imgs, padrao, destino, cols=4):
    """Monta uma folha com todas as imagens que casam 'padrao' (ex.: swipe_*.png)."""
    def num(p):
        s = "".join(ch for ch in os.path.basename(p) if ch.isdigit())
        return int(s) if s else 0
    arqs = sorted(glob.glob(os.path.join(str(dir_imgs), padrao)), key=num)
    tiles = []
    for a in arqs:
        im = imgio.imread(a)
        if im is not None:
            tiles.append(_janela(im, rotulo=os.path.basename(a)[:-4]))
    if not tiles:
        return False
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    linhas = [np.hstack(tiles[r*cols:(r+1)*cols]) for r in range(len(tiles)//cols)]
    imgio.imwrite(destino, np.vstack(linhas))
    return True


def gerar_testes(perfil, w, h, saida, n=20):
    """Gera n swipes de teste do perfil e monta a folha na pasta 'saida'."""
    from pathlib import Path
    saida = Path(saida); saida.mkdir(parents=True, exist_ok=True)
    for f in saida.glob("gerado_*.png"):
        try: f.unlink()
        except Exception: pass
    for k in range(1, n + 1):
        pts = gerar_swipe.gerar(perfil, w, h)
        render_swipe(pts, w, h, saida / f"gerado_{k}.png", titulo=f"gerado {k}")
    montar(saida, "gerado_*.png", saida / "_montagem_GERADOS.png")
