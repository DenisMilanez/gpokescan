# -*- coding: utf-8 -*-
"""
Gerador de swipes humanizados a partir do perfil capturado (perfil_swipe.json).

Amostra um gesto NOVO a cada chamada (nunca repete o gravado): duracao, pontos de
inicio/fim, curvatura e tremor sao sorteados das distribuicoes do seu perfil real;
a velocidade segue um perfil "minimum-jerk" (acelera-desacelera, como humano).
O resultado e uma lista de pontos (t, x, y) pronta pra render ou pra injecao.

Uso (gera 20 exemplos e renderiza em calibracao/swipe_horizontal/gerados/):
    .venv\\Scripts\\python.exe gerar_swipe.py
"""

import bisect
import json
import math
import random
from pathlib import Path

DIR_SWIPE = Path(__file__).resolve().parent / "calibracao" / "swipe_horizontal"


# ------------------------------------------------------------ #
# Carregamento robusto do perfil (tolera JSON truncado no fim)
# ------------------------------------------------------------ #
def carregar_perfil(caminho):
    """Le o perfil. Se o JSON estiver corrompido (ex.: templates truncados),
    recupera ao menos as estatisticas do topo, que e o que o gerador usa."""
    txt = Path(caminho).read_text(encoding="utf-8")
    try:
        return json.loads(txt)
    except Exception:
        # corta a partir de 'templates_velocidade' e fecha o objeto
        i = txt.find('"templates_velocidade"')
        if i > 0:
            j = txt.rfind(",", 0, i)
            try:
                return json.loads(txt[:j] + "\n}")
            except Exception:
                pass
        raise


def _ms(perfil, chave, media_pad, std_pad=0.0):
    d = perfil.get(chave) or {}
    return d.get("media", media_pad), d.get("std", std_pad)


def _rot(px, py, ox, oy, ang):
    """Rotaciona (px,py) em torno de (ox,oy) por 'ang' rad."""
    c, s = math.cos(ang), math.sin(ang)
    dx, dy = px - ox, py - oy
    return ox + dx*c - dy*s, oy + dx*s + dy*c


def _perfil_velocidade(n):
    """
    Fracao de ARCO acumulada (0..1) por passo de tempo uniforme.
    Base = velocidade min-jerk (0 nas pontas) MODULADA por oscilacao suave de
    baixa frequencia -> a aceleracao oscila (como humano) e varia a cada gesto,
    sem virar serrilhado (nada de ruido por ponto).
    """
    us = [i/(n-1) for i in range(n)]
    base = [30*u*u - 60*u**3 + 30*u**4 for u in us]      # perfil de velocidade min-jerk
    comps = [(random.uniform(0.12, 0.32), random.uniform(1.3, 3.2),
              random.uniform(0, 2*math.pi)) for _ in range(random.randint(2, 3))]
    spd = []
    for u, b in zip(us, base):
        mod = 1 + sum(a*math.sin(2*math.pi*f*u + ph) for a, f, ph in comps)
        spd.append(max(b * max(mod, 0.25), 1e-4))
    cum = [0.0]
    for s in spd[1:]:
        cum.append(cum[-1] + s)
    tot = cum[-1] or 1.0
    return [c/tot for c in cum]


def _bezier_por_arco(P0, P1, P2, P3, cumfrac):
    """Amostra a Bezier cubica nas fracoes de ARCO dadas (velocidade correta)."""
    M = 120
    xs, ys = [], []
    for j in range(M + 1):
        t = j/M; mt = 1 - t
        xs.append(mt**3*P0[0] + 3*mt*mt*t*P1[0] + 3*mt*t*t*P2[0] + t**3*P3[0])
        ys.append(mt**3*P0[1] + 3*mt*mt*t*P1[1] + 3*mt*t*t*P2[1] + t**3*P3[1])
    fr = [0.0]
    for j in range(1, M + 1):
        fr.append(fr[-1] + math.hypot(xs[j]-xs[j-1], ys[j]-ys[j-1]))
    tot = fr[-1] or 1.0
    fr = [f/tot for f in fr]
    pts = []
    for cf in cumfrac:
        k = min(max(bisect.bisect_left(fr, cf), 1), M)
        f0, f1 = fr[k-1], fr[k]
        a = 0.0 if f1 == f0 else (cf - f0)/(f1 - f0)
        pts.append((xs[k-1] + a*(xs[k]-xs[k-1]), ys[k-1] + a*(ys[k]-ys[k-1])))
    return pts


def _dur_para(dist, perfil):
    """Duracao correlacionada com a distancia (swipe mais longo, um pouco mais lento)."""
    dm, ds = _ms(perfil, "duracao_s", 0.16, 0.04)
    base = 0.09 + dist * 0.00028
    return max(0.07, random.gauss(0.5*dm + 0.5*base, max(ds, 0.02) * 0.8))


# ------------------------------------------------------------ #
# Geracao de um gesto
# ------------------------------------------------------------ #
def gerar(perfil, w=None, h=None, seed=None):
    """
    Gera um swipe humanizado. Estrategia:
      - BOOTSTRAP: reamostra um gesto REAL (perfil['gestos']) -> preserva os
        dois perfis (curto/longo) e as posicoes reais; se nao houver, cai nas
        distribuicoes agregadas.
      - PERTURBACAO controlada: desloca inicio, escala (+-8%) e rotaciona (+-3 graus)
        o vetor -> cada reproducao e diferente, mantendo a personalidade.
      - GANCHO de angulo nas pontas: rotaciona as tangentes inicial/final (+-7 graus).
      - VELOCIDADE oscilante (min-jerk + oscilacao suave) amostrada por arco.
    Retorna [(t, x, y), ...].
    """
    if seed is not None:
        random.seed(seed)

    gestos = perfil.get("gestos")
    if gestos:
        ex = random.choice(gestos)                 # reamostra um swipe real
        bx0, by0 = ex["inicio"]; bx1, by1 = ex["fim"]
        dur = ex.get("dur") or _dur_para(math.hypot(bx1-bx0, by1-by0), perfil)
    else:
        ix_m, ix_s = _ms(perfil, "inicio_x", 800, 40)
        iy_m, iy_s = _ms(perfil, "inicio_y", 1200, 30)
        fx_m, _ = _ms(perfil, "fim_x", 250, 40)
        fy_m, _ = _ms(perfil, "fim_y", 1200, 30)
        bx0, by0 = random.gauss(ix_m, ix_s), random.gauss(iy_m, iy_s)
        bx1, by1 = bx0 + (fx_m - ix_m), by0 + (fy_m - iy_m)
        dur = _dur_para(math.hypot(bx1-bx0, by1-by0), perfil)

    # perturbacao: posicao de inicio, escala e rotacao do deslocamento
    x0 = bx0 + random.gauss(0, 20)
    y0 = by0 + random.gauss(0, 24)
    esc = random.gauss(1.0, 0.08)
    rot = math.radians(random.gauss(0, 3.0))
    c, s = math.cos(rot), math.sin(rot)
    dispx, dispy = bx1 - bx0, by1 - by0
    dx = (dispx*c - dispy*s) * esc
    dy = (dispx*s + dispy*c) * esc
    x1, y1 = x0 + dx, y0 + dy
    corda = math.hypot(dx, dy) or 1.0
    pxn, pyn = -dy/corda, dx/corda

    # curvatura suave (um arco), amplitude do perfil
    curv_m, curv_s = _ms(perfil, "curvatura", 0.06, 0.03)
    amp = random.gauss(curv_m, curv_s) * corda * random.choice([-1, 1])
    k1, k2 = random.uniform(0.8, 1.1), random.uniform(0.8, 1.1)
    P0 = (x0, y0); P3 = (x1, y1)
    P1 = [x0 + dx/3 + pxn*amp*k1, y0 + dy/3 + pyn*amp*k1]
    P2 = [x0 + 2*dx/3 + pxn*amp*k2, y0 + 2*dy/3 + pyn*amp*k2]
    # gancho de angulo: rotaciona a tangente inicial (em P0) e a final (em P3)
    P1 = list(_rot(P1[0], P1[1], x0, y0, math.radians(random.gauss(0, 7))))
    P2 = list(_rot(P2[0], P2[1], x1, y1, math.radians(random.gauss(0, 7))))

    # velocidade oscilante -> amostra por arco
    n = random.randint(34, 46)
    cumfrac = _perfil_velocidade(n)
    xy = _bezier_por_arco(P0, P1, P2, P3, cumfrac)
    pontos = []
    for i, (x, y) in enumerate(xy):
        u = i / (len(xy) - 1)
        if w:
            x = min(max(x, 1), w - 1)
        if h:
            y = min(max(y, 1), h - 1)
        pontos.append((dur * u, x, y))
    return pontos


def main():
    import swipe_calibra as sw           # importado so aqui (usa cv2)
    perfil_path = DIR_SWIPE / "perfil_swipe.json"
    perfil = carregar_perfil(perfil_path)
    w, h = perfil.get("largura", 1080), perfil.get("altura", 2340)
    saida = DIR_SWIPE / "gerados"
    saida.mkdir(parents=True, exist_ok=True)
    for k in range(1, 21):
        g = gerar(perfil, w, h)
        sw.render_swipe(g, w, h, saida / f"gerado_{k}.png", titulo=f"gerado {k}")
    print(f"20 swipes gerados em: {saida}")


if __name__ == "__main__":
    main()
