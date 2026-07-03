# -*- coding: utf-8 -*-
"""
Deteccao do icone do PokeGenie (disco azul + miolo laranja + anel branco).

Problema: o icone e MOVEL (o usuario arrasta pra onde quiser) e o disco azul e
semitransparente (o fundo "vaza" por ele). Entao NAO casamos o blob inteiro.

Estrategia (validada na pratica): o miolo laranja e uma cor VIVIDA (saturacao
alta) que nao aparece no resto da tela do jogo (o bokeh quente e o medalhao sao
alaranjados porem dessaturados). Segmentamos esse laranja vivido, filtramos por
formato circular e raio, e confirmamos o ANEL BRANCO em volta. Isso torna o
match praticamente unico e independente do fundo. O centroide e o ponto de clique.

Busca primeiro numa regiao prioritaria (onde o icone costuma ficar) e, se nao
achar, varre a tela inteira.
"""

import cv2
import numpy as np

import imgio

# Faixa do laranja VIVIDO em HSV (OpenCV: H 0-179). S alto = descarta bokeh/medalha.
LARANJA_LO = np.array([10, 140, 150])
LARANJA_HI = np.array([25, 255, 255])

# Branco do anel: baixa saturacao, alto brilho.
BRANCO_S_MAX = 60
BRANCO_V_MIN = 180


def _brancura_anel(hsv, cx, cy, r):
    """Fracao de pixels brancos num anel logo em volta do miolo laranja."""
    h, w = hsv.shape[:2]
    y0, y1 = max(0, int(cy - r * 2.2)), min(h, int(cy + r * 2.2))
    x0, x1 = max(0, int(cx - r * 2.2)), min(w, int(cx + r * 2.2))
    sub = hsv[y0:y1, x0:x1]
    if sub.size == 0:
        return 0.0
    yy, xx = np.ogrid[y0:y1, x0:x1]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    anel = (dist >= r * 1.05) & (dist <= r * 1.9)
    if anel.sum() == 0:
        return 0.0
    branco = (sub[:, :, 1] < BRANCO_S_MAX) & (sub[:, :, 2] > BRANCO_V_MIN)
    return float(branco[anel].mean())


def _candidatos(img_bgr, roi=None):
    """
    Retorna candidatos [(score, cx, cy, r)] ordenados do melhor pro pior,
    dentro do roi (x0,y0,x1,y1) ou na imagem toda.
    """
    h, w = img_bgr.shape[:2]
    x0, y0, x1, y1 = roi if roi else (0, 0, w, w and h)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    recorte = img_bgr[y0:y1, x0:x1]
    if recorte.size == 0:
        return []

    hsv = cv2.cvtColor(recorte, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, LARANJA_LO, LARANJA_HI)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Raio esperado do miolo: fracao da largura, com folga (icone escala por device)
    r_min = max(5, int(0.006 * w))
    r_max = int(0.045 * w)

    cands = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 40:
            continue
        (px, py), r = cv2.minEnclosingCircle(c)
        if not (r_min <= r <= r_max):
            continue
        circ = area / (np.pi * r * r + 1e-6)   # 1.0 = circulo perfeito
        if circ < 0.55:
            continue
        # coordenadas absolutas (na imagem inteira)
        cx, cy = px + x0, py + y0
        branco = _brancura_anel(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV), cx, cy, r)
        # score combina circularidade e presenca do anel branco
        score = circ * 0.6 + branco * 0.4
        cands.append((score, int(cx), int(cy), int(round(r))))
    cands.sort(reverse=True)
    return cands


def detectar(img_bgr, roi_prioritaria=None, score_min=0.45):
    """
    Localiza o icone. Tenta a roi prioritaria primeiro; se nada bom, tela inteira.
    Retorna dict {x, y, r, score} do melhor match, ou None.
    """
    tentativas = []
    if roi_prioritaria:
        tentativas.append(roi_prioritaria)
    tentativas.append(None)  # tela inteira (fallback)

    melhor = None
    for roi in tentativas:
        cands = _candidatos(img_bgr, roi)
        if cands and cands[0][0] >= score_min:
            melhor = cands[0]
            break
        if cands and (melhor is None or cands[0][0] > melhor[0]):
            melhor = cands[0]

    if not melhor:
        return None
    score, x, y, r = melhor
    return {"x": x, "y": y, "r": r, "score": round(score, 3)}


def detectar_arquivo(caminho, roi_prioritaria=None):
    """Conveniencia: carrega um PNG e detecta."""
    img = imgio.imread(caminho)
    if img is None:
        return None
    return detectar(img, roi_prioritaria)


# ================================================================== #
# Zona de clique (nao clicar sempre no pixel central = cara de bot)
# ================================================================== #
# Geometria medida no icone real (disco azul em relacao ao miolo laranja):
#   offset do centro do disco ~ (+1.6, +0.8) * raio_laranja  (direita e baixo)
#   raio do disco ~ 3.2 * raio_laranja
OFFSET_DISCO = (1.6, 0.8)     # (dx, dy) em unidades de raio do laranja
ZONA_FRAC_DISCO = 0.7          # usa 70% do raio do disco (margem da borda)
ZONA_FRAC_FALLBACK = 2.0       # zona = 2x o raio do laranja quando nao ha disco
GAUSS_SIGMA = 0.38             # dispersao do sorteio (fracao do raio da zona)
GAUSS_MAX = 0.85               # nunca perto da borda da zona

# Faixa do azul claro do disco (semitransparente -> S baixo/medio, V alto)
AZUL_LO = np.array([90, 25, 150])
AZUL_HI = np.array([125, 140, 255])


def detectar_disco(img_bgr, ox, oy, ro):
    """
    Tenta achar o disco azul que CONTEM o miolo laranja em (ox,oy).
    Retorna (cx, cy, R) ou None (o fundo transparente pode inviabilizar).
    """
    import math
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, AZUL_LO, AZUL_HI)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    melhor = None
    for c in cnts:
        a = cv2.contourArea(c)
        if a < 500:
            continue
        (x, y), r = cv2.minEnclosingCircle(c)
        # o disco tem que envolver o laranja e ser coerente em tamanho
        if math.hypot(x - ox, y - oy) < r and 2.0 * ro <= r <= 6.0 * ro:
            if melhor is None or a > melhor[0]:
                melhor = (a, x, y, r)
    if melhor:
        return (melhor[1], melhor[2], melhor[3])
    return None


def zona_clique(det, img_bgr=None):
    """
    Define a zona de clique (cx, cy, R) a partir do resultado de detectar().
    Se img_bgr vier e o disco azul for detectavel, usa o disco (mais preciso);
    senao, estima geometricamente a partir do laranja (direita + baixo).
    """
    ox, oy, ro = det["x"], det["y"], det["r"]
    disco = detectar_disco(img_bgr, ox, oy, ro) if img_bgr is not None else None
    if disco:
        cx, cy, R = disco
        return (cx, cy, R * ZONA_FRAC_DISCO)
    # fallback: so com o laranja como referencia
    dx, dy = OFFSET_DISCO
    return (ox + dx * ro, oy + dy * ro, ZONA_FRAC_FALLBACK * ro)


def ponto_clique(zona):
    """
    Sorteia um ponto de clique dentro da zona (cx, cy, R) com distribuicao
    gaussiana em torno do centro (concentra no meio, espalha para as bordas,
    nunca repete o mesmo pixel). Retorna (x, y) inteiros.
    """
    import math
    import random
    cx, cy, R = zona
    for _ in range(20):
        ang = random.uniform(0, 2 * math.pi)
        rad = abs(random.gauss(0, R * GAUSS_SIGMA))
        if rad <= R * GAUSS_MAX:
            return int(round(cx + rad * math.cos(ang))), int(round(cy + rad * math.sin(ang)))
    return int(round(cx)), int(round(cy))
