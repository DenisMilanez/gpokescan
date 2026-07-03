# -*- coding: utf-8 -*-
"""
Regioes da tela (fatiamento) - base da calibracao.

Ideia: como a resolucao muda entre celulares, definimos as regioes em FRACAO
da tela (0..1), nunca em pixels fixos. Assim "canto inferior esquerdo" e a mesma
area em qualquer aparelho. Com isso podemos recortar so a ROI de interesse de
qualquer print e rodar template matching / OCR ali (mais rapido que varrer tudo).

Esquema (grade 3x3 como base + metades + quadrantes derivados):
  colunas: esq (0-1/3) | centro (1/3-2/3) | dir (2/3-1)
  linhas : sup (0-1/3) | meio (1/3-2/3) | inf (2/3-1)

Cada regiao e uma caixa relativa (x0, y0, x1, y1) com valores entre 0 e 1.
"""

import json
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # so quebra se realmente for fatiar imagens
    Image = ImageDraw = ImageFont = None

DIR_BASE = Path(__file__).resolve().parent
DIR_CALIB = DIR_BASE / "calibracao"     # ASCII (sem acento) p/ evitar bug de path no Windows

_T = 1 / 3
_M = 2 / 3

# ------------------------------------------------------------------ #
# Definicao das regioes (fracoes 0..1): x0, y0, x1, y1
# ------------------------------------------------------------------ #
REGIOES = {
    # --- Grade 3x3 (celulas atomicas) ---
    "grade_sup_esq":    (0.0, 0.0, _T,  _T),
    "grade_sup_centro": (_T,  0.0, _M,  _T),
    "grade_sup_dir":    (_M,  0.0, 1.0, _T),
    "grade_meio_esq":   (0.0, _T,  _T,  _M),
    "grade_meio_centro":(_T,  _T,  _M,  _M),
    "grade_meio_dir":   (_M,  _T,  1.0, _M),
    "grade_inf_esq":    (0.0, _M,  _T,  1.0),
    "grade_inf_centro": (_T,  _M,  _M,  1.0),
    "grade_inf_dir":    (_M,  _M,  1.0, 1.0),

    # --- Metades ---
    "metade_esquerda":  (0.0, 0.0, 0.5, 1.0),
    "metade_direita":   (0.5, 0.0, 1.0, 1.0),
    "metade_superior":  (0.0, 0.0, 1.0, 0.5),
    "metade_inferior":  (0.0, 0.5, 1.0, 1.0),

    # --- Quadrantes ---
    "quad_sup_esq":     (0.0, 0.0, 0.5, 0.5),
    "quad_sup_dir":     (0.5, 0.0, 1.0, 0.5),
    "quad_inf_esq":     (0.0, 0.5, 0.5, 1.0),
    "quad_inf_dir":     (0.5, 0.5, 1.0, 1.0),
}


def caixa_px(frac, largura, altura):
    """Converte uma caixa relativa (x0,y0,x1,y1) em pixels inteiros."""
    x0, y0, x1, y1 = frac
    return (
        int(round(x0 * largura)), int(round(y0 * altura)),
        int(round(x1 * largura)), int(round(y1 * altura)),
    )


def fatiar(img_path, largura=None, altura=None, saida=DIR_CALIB,
           gerar_overlay=True, log=print):
    """
    Fatia a imagem em todas as REGIOES e salva cada recorte em 'saida' com o
    sufixo da dimensao da TELA, ex.: grade_sup_esq_1080x2340.png.

    Tambem salva:
      - regioes_<w>x<h>.json : manifesto (coords relativas + em pixels);
      - _grade_overlay_<w>x<h>.png : imagem com as divisoes desenhadas (visual).

    Retorna o dicionario do manifesto.
    """
    if Image is None:
        raise RuntimeError("Pillow nao instalado. pip install pillow")

    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    # Se a resolucao nao foi informada, usa a da propria imagem
    largura = largura or w
    altura = altura or h
    sufixo = f"{largura}x{altura}"

    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)

    manifesto = {"largura": largura, "altura": altura, "regioes": {}}

    for nome, frac in REGIOES.items():
        cx = caixa_px(frac, w, h)
        recorte = img.crop(cx)
        destino = saida / f"{nome}_{sufixo}.png"
        recorte.save(destino)
        manifesto["regioes"][nome] = {
            "relativo": [round(v, 6) for v in frac],
            "pixels": list(caixa_px(frac, largura, altura)),
            "arquivo": destino.name,
        }
        log(f"  {nome:18s} -> {destino.name}  {cx}")

    # Manifesto JSON (a leitura em producao usa isso, nao os recortes)
    manif_path = saida / f"regioes_{sufixo}.json"
    manif_path.write_text(
        json.dumps(manifesto, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Manifesto salvo: {manif_path.name} ({len(REGIOES)} regioes)")

    if gerar_overlay:
        _desenhar_overlay(img.copy(), saida / f"_grade_overlay_{sufixo}.png", log)

    return manifesto


def _linha_contraste(d, p0, p1, cor, largura):
    """Desenha uma linha com contorno preto por baixo (visivel em qualquer fundo)."""
    d.line([p0, p1], fill=(0, 0, 0), width=largura + 4)   # contorno
    d.line([p0, p1], fill=cor, width=largura)             # cor por cima


def _rotulo(d, cx, cy, texto, fonte, cor_caixa):
    """Escreve 'texto' centralizado em (cx,cy) dentro de uma caixinha legivel."""
    try:
        x0, y0, x1, y1 = d.textbbox((0, 0), texto, font=fonte)
        tw, th = x1 - x0, y1 - y0
    except Exception:
        tw, th = len(texto) * 12, 16
    pad = 8
    caixa = [cx - tw // 2 - pad, cy - th // 2 - pad,
             cx + tw // 2 + pad, cy + th // 2 + pad]
    d.rectangle(caixa, fill=cor_caixa, outline=(0, 0, 0), width=2)
    d.text((cx - tw // 2, cy - th // 2), texto, fill=(255, 255, 255),
           font=fonte, stroke_width=2, stroke_fill=(0, 0, 0))


def _desenhar_overlay(img, destino, log=print):
    """Desenha as divisoes e escreve o nome de cada celula (igual aos recortes)."""
    d = ImageDraw.Draw(img)
    w, h = img.size

    # Linhas das metades (0.5) em laranja, bem grossas
    _linha_contraste(d, (w // 2, 0), (w // 2, h), (255, 140, 0), 8)
    _linha_contraste(d, (0, h // 2), (w, h // 2), (255, 140, 0), 8)
    # Linhas dos tercos (grade 3x3) em ciano, grossas
    for f in (_T, _M):
        _linha_contraste(d, (int(f * w), 0), (int(f * w), h), (0, 220, 255), 6)
        _linha_contraste(d, (0, int(f * h)), (w, int(f * h)), (0, 220, 255), 6)

    # Fonte
    try:
        fonte = ImageFont.truetype("arial.ttf", 40)
    except Exception:
        fonte = ImageFont.load_default()

    # Rotulo de cada celula da grade 3x3 com o mesmo nome do recorte
    # (sem o prefixo 'grade_' para caber melhor). Caixa ciano.
    for nome, frac in REGIOES.items():
        if not nome.startswith("grade_"):
            continue
        x0, y0, x1, y1 = frac
        cx = int((x0 + x1) / 2 * w)
        cy = int((y0 + y1) / 2 * h)
        _rotulo(d, cx, cy, nome.replace("grade_", ""), fonte, (0, 130, 160))

    img.save(destino)
    log(f"Overlay salvo: {destino.name}")


if __name__ == "__main__":
    # Demo: fatia a primeira captura (mesma resolucao do celular do usuario)
    demo = DIR_BASE / "capturas" / "1.png"
    if demo.exists():
        print(f"Fatiando demo: {demo.name}")
        fatiar(demo)
    else:
        print("Sem captura de demo em capturas/1.png")
