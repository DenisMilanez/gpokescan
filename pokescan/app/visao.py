# -*- coding: utf-8 -*-
"""
Utilitarios de visao para a calibracao e o bot:
  - detectar_botao_x   : acha o circulo branco com X (Hough + 2 diagonais).
  - salvar_template_*  : recorta e salva templates (com mascara) p/ matching rapido.
  - localizar_template : casa um template salvo na tela (rapido; usado no bot).
  - delimitar_bloco    : acha topo/base do painel branco (projecao de linhas).

Metodos por alvo:
  - icone laranja  -> cor (detectar_icone.py) + template (aqui) como atalho rapido.
  - botao X        -> geometria (circulo + diagonais) + template.
  - card branco    -> projecao de linhas (transicoes de branco/cor).
"""

import math
from pathlib import Path

import cv2
import numpy as np

import imgio


# ============================================================ #
# Botao X (circulo branco com X dentro)
# ============================================================ #
def detectar_botao_x(img_bgr, roi=None):
    """
    Acha o botao 'fechar' (circulo branco com X). Retorna {x,y,r} ou None.
    Desambigua da estrela / icone vermelho contando as DIAGONAIS internas.
    roi = (x0,y0,x1,y1); se None usa o quadrante superior-esquerdo.
    """
    H, W = img_bgr.shape[:2]
    if roi is None:
        roi = (0, 0, int(0.40 * W), int(0.40 * H))
    x0, y0, x1, y1 = roi
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    sub = cv2.medianBlur(gray[y0:y1, x0:x1], 5)
    circ = cv2.HoughCircles(sub, cv2.HOUGH_GRADIENT, dp=1, minDist=70,
                            param1=100, param2=30, minRadius=35, maxRadius=80)
    if circ is None:
        return None
    melhor = None
    for c in np.round(circ[0]).astype(int):
        cx, cy, r = c[0] + x0, c[1] + y0, c[2]
        diag = _conta_diagonais(gray, cx, cy, r, W, H)
        if diag >= 2 and (melhor is None or diag > melhor[0]):
            melhor = (diag, cx, cy, r)
    if melhor:
        return {"x": int(melhor[1]), "y": int(melhor[2]), "r": int(melhor[3]),
                "diagonais": int(melhor[0])}
    return None


def _conta_diagonais(gray, cx, cy, r, W, H):
    """Conta segmentos ~45/135 graus dentro do circulo (assinatura do X)."""
    x0, y0 = max(0, cx - r), max(0, cy - r)
    x1, y1 = min(W, cx + r), min(H, cy + r)
    sub = gray[y0:y1, x0:x1]
    if sub.size == 0:
        return 0
    dark = cv2.threshold(sub, 110, 255, cv2.THRESH_BINARY_INV)[1]
    m = np.zeros_like(dark)
    cv2.circle(m, (sub.shape[1] // 2, sub.shape[0] // 2), int(r * 0.8), 255, -1)
    dark = cv2.bitwise_and(dark, m)
    linhas = cv2.HoughLinesP(dark, 1, np.pi / 180, threshold=18,
                             minLineLength=int(r * 0.7), maxLineGap=6)
    if linhas is None:
        return 0
    diag = 0
    for l in linhas:
        a, b, c, d = l[0]
        ang = abs(math.degrees(math.atan2(d - b, c - a)))
        if 30 <= ang <= 60 or 120 <= ang <= 150:
            diag += 1
    return diag


# ============================================================ #
# Botao de menu (circulo verde-agua com 3 barras HORIZONTAIS)
# ============================================================ #
def detectar_botao_menu(img_bgr, roi=None):
    """
    Acha o botao de menu (circulo com 3 barras horizontais). Retorna {x,y,r} ou None.
    Desambigua do X e de outros circulos exigindo que as linhas internas sejam
    quase todas HORIZONTAIS (pureza alta). roi=(x0,y0,x1,y1); default = metade inferior.
    """
    H, W = img_bgr.shape[:2]
    if roi is None:
        roi = (0, int(0.5 * H), W, H)
    x0, y0, x1, y1 = roi
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    sub = cv2.medianBlur(gray[y0:y1, x0:x1], 5)
    circ = cv2.HoughCircles(sub, cv2.HOUGH_GRADIENT, dp=1, minDist=80,
                            param1=100, param2=32, minRadius=40, maxRadius=95)
    if circ is None:
        return None
    melhor = None
    for c in np.round(circ[0]).astype(int):
        cx, cy, r = c[0] + x0, c[1] + y0, c[2]
        hz, tot = _conta_horizontais(gray, cx, cy, r, W, H)
        # exige linhas suficientes e quase todas horizontais (barras do menu)
        if hz >= 3 and tot > 0 and hz / tot >= 0.85:
            if melhor is None or hz > melhor[0]:
                melhor = (hz, cx, cy, r)
    if melhor:
        return {"x": int(melhor[1]), "y": int(melhor[2]), "r": int(melhor[3]),
                "horizontais": int(melhor[0])}
    return None


def _conta_horizontais(gray, cx, cy, r, W, H):
    """Conta segmentos ~horizontais (barras) e o total, dentro do circulo."""
    x0, y0 = max(0, cx - r), max(0, cy - r)
    x1, y1 = min(W, cx + r), min(H, cy + r)
    sub = gray[y0:y1, x0:x1]
    if sub.size == 0:
        return 0, 0
    # as barras sao mais CLARAS que o fundo do botao
    claro = cv2.threshold(sub, 150, 255, cv2.THRESH_BINARY)[1]
    m = np.zeros_like(claro)
    cv2.circle(m, (sub.shape[1] // 2, sub.shape[0] // 2), int(r * 0.75), 255, -1)
    claro = cv2.bitwise_and(claro, m)
    linhas = cv2.HoughLinesP(claro, 1, np.pi / 180, threshold=15,
                             minLineLength=int(r * 0.7), maxLineGap=8)
    if linhas is None:
        return 0, 0
    hz = 0
    for l in linhas:
        a, b, c, d = l[0]
        ang = abs(math.degrees(math.atan2(d - b, c - a)))
        if ang <= 20 or ang >= 160:
            hz += 1
    return hz, len(linhas)


# ============================================================ #
# Texto via OCR (ex.: 'AVALIAR' no menu)
# ============================================================ #
def localizar_texto(img_bgr, alvo, roi=None, padx=48, pady=12):
    """
    Acha um texto (ex.: 'AVALIAR') via OCR (tesseract). Retorna
    {x0,y0,x1,y1,cx,cy} com folga horizontal, ou None (tambem se o tesseract
    nao estiver instalado). roi=(x0,y0,x1,y1); default = metade inferior.
    """
    try:
        import pytesseract
        from pytesseract import Output
    except Exception:
        return None
    # acha o tesseract.exe mesmo fora do PATH (winget instala em Program Files)
    import os
    import shutil
    if not shutil.which("tesseract"):
        for cand in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                     r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
            if os.path.exists(cand):
                pytesseract.pytesseract.tesseract_cmd = cand
                break
    H, W = img_bgr.shape[:2]
    if roi is None:
        roi = (0, int(0.5 * H), W, H)
    rx0, ry0, rx1, ry1 = roi
    sub = img_bgr[ry0:ry1, rx0:rx1]
    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    th = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]
    try:
        d = pytesseract.image_to_data(th, output_type=Output.DICT)
    except Exception:
        return None
    alvo = alvo.strip().upper()
    for i, t in enumerate(d["text"]):
        tt = t.strip().upper()
        if tt and (tt == alvo or tt.startswith(alvo)):
            bx = d["left"][i] + rx0; by = d["top"][i] + ry0
            bw = d["width"][i]; bh = d["height"][i]
            x0 = max(0, bx - padx); y0 = max(0, by - pady)
            x1 = min(W, bx + bw + padx); y1 = min(H, by + bh + pady)
            return {"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                    "cx": (x0 + x1) // 2, "cy": (y0 + y1) // 2}
    return None


# ============================================================ #
# Templates (recorte com mascara) + matching
# ============================================================ #
def salvar_template_circular(img_bgr, cx, cy, r, path_template, path_mask):
    """Recorta um circulo (X, etc.) e salva template + mascara circular."""
    crop = img_bgr[cy - r:cy + r, cx - r:cx + r].copy()
    mask = np.zeros((2 * r, 2 * r), np.uint8)
    cv2.circle(mask, (r, r), int(r * 0.92), 255, -1)
    imgio.imwrite(path_template, crop)
    imgio.imwrite(path_mask, mask)
    return crop.shape[:2]


def salvar_template_icone(img_bgr, cx, cy, r, path_template, path_mask):
    """
    Recorta o icone PokeGenie (miolo laranja + anel branco) com folga e mascara
    que IGNORA o azul (so laranja/branco contam) -> matching independe do fundo.
    """
    rr = int(r * 2.4)  # folga p/ pegar o anel branco
    x0, y0 = max(0, cx - rr), max(0, cy - rr)
    x1, y1 = cx + rr, cy + rr
    crop = img_bgr[y0:y1, x0:x1].copy()
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    laranja = cv2.inRange(hsv, np.array([10, 140, 150]), np.array([25, 255, 255]))
    branco = cv2.inRange(hsv, np.array([0, 0, 180]), np.array([179, 60, 255]))
    mask = cv2.bitwise_or(laranja, branco)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    imgio.imwrite(path_template, crop)
    imgio.imwrite(path_mask, mask)
    return crop.shape[:2]


def localizar_template(img_bgr, template_path, mask_path=None, roi=None,
                       limiar=0.65):
    """
    Casa um template salvo na imagem. Retorna {x,y,score} do CENTRO do match,
    ou None se o score for abaixo do limiar. Busca no roi (mais rapido) se dado.
    """
    tpl = imgio.imread(template_path)
    if tpl is None:
        return None
    mask = imgio.imread(mask_path, cv2.IMREAD_GRAYSCALE) if mask_path else None
    H, W = img_bgr.shape[:2]
    if roi:
        x0, y0, x1, y1 = roi
        area = img_bgr[y0:y1, x0:x1]
    else:
        x0, y0 = 0, 0
        area = img_bgr
    th, tw = tpl.shape[:2]
    if area.shape[0] < th or area.shape[1] < tw:
        return None
    try:
        if mask is not None:
            res = cv2.matchTemplate(area, tpl, cv2.TM_CCORR_NORMED, mask=mask)
        else:
            res = cv2.matchTemplate(area, tpl, cv2.TM_CCOEFF_NORMED)
    except cv2.error:
        res = cv2.matchTemplate(area, tpl, cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxloc = cv2.minMaxLoc(res)
    if not np.isfinite(maxv) or maxv < limiar:
        return None
    cx = x0 + maxloc[0] + tw // 2
    cy = y0 + maxloc[1] + th // 2
    return {"x": int(cx), "y": int(cy), "score": round(float(maxv), 3)}


# ============================================================ #
# Card branco do PokeGenie (topo/base por projecao de linhas)
# ============================================================ #
def delimitar_bloco(img_bgr, margem_base=8):
    """
    Acha topo e base do painel branco de resultado.
      topo = 1a linha de largura cheia que 'entra no branco';
      base = logo acima do anuncio (1o bloco nao-branco sustentado >=48px).
    Retorna {topo, base} ou None.
    """
    H, W = img_bgr.shape[:2]
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    S, V = hsv[:, :, 1], hsv[:, :, 2]
    band = slice(int(0.05 * W), int(0.95 * W))
    branco = (S < 25) & (V > 235)
    fb = branco[:, band].mean(axis=1)
    nb = (~branco)[:, band].mean(axis=1)

    topo = None
    for y in range(int(0.45 * H), int(0.70 * H)):
        if fb[y] > 0.9 and fb[y:y + 60].mean() > 0.9:
            topo = y
            break
    if topo is None:
        return None

    ad_top = None
    for y in range(topo + 300, H - 50):
        if nb[y:y + 48].mean() > 0.15 and (nb[y:y + 48] > 0.05).mean() > 0.9:
            ad_top = y
            break
    base = (ad_top - margem_base) if ad_top else int(0.95 * H)
    return {"topo": int(topo), "base": int(base)}


def topo_bloco(img_bgr):
    """So o topo do painel branco (usado na verificacao rapida do bot)."""
    d = delimitar_bloco(img_bgr)
    return d["topo"] if d else None
