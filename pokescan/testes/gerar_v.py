# -*- coding: utf-8 -*-
"""Copia identica de gerar_swipe.py (nome novo p/ contornar cache do mount)."""

import bisect
import json
import math
import random
from pathlib import Path

DIR_SWIPE = Path(__file__).resolve().parent / "calibracao" / "swipe_horizontal"


def carregar_perfil(caminho):
    txt = Path(caminho).read_text(encoding="utf-8")
    try:
        return json.loads(txt)
    except Exception:
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
    c, s = math.cos(ang), math.sin(ang)
    dx, dy = px - ox, py - oy
    return ox + dx*c - dy*s, oy + dx*s + dy*c


def _perfil_velocidade(n):
    us = [i/(n-1) for i in range(n)]
    base = [30*u*u - 60*u**3 + 30*u**4 for u in us]
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
    dm, ds = _ms(perfil, "duracao_s", 0.16, 0.04)
    base = 0.09 + dist * 0.00028
    return max(0.07, random.gauss(0.5*dm + 0.5*base, max(ds, 0.02) * 0.8))


def gerar(perfil, w=None, h=None, seed=None):
    if seed is not None:
        random.seed(seed)
    gestos = perfil.get("gestos")
    if gestos:
        ex = random.choice(gestos)
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

    curv_m, curv_s = _ms(perfil, "curvatura", 0.06, 0.03)
    amp = random.gauss(curv_m, curv_s) * corda * random.choice([-1, 1])
    k1, k2 = random.uniform(0.8, 1.1), random.uniform(0.8, 1.1)
    P0 = (x0, y0); P3 = (x1, y1)
    P1 = [x0 + dx/3 + pxn*amp*k1, y0 + dy/3 + pyn*amp*k1]
    P2 = [x0 + 2*dx/3 + pxn*amp*k2, y0 + 2*dy/3 + pyn*amp*k2]
    P1 = list(_rot(P1[0], P1[1], x0, y0, math.radians(random.gauss(0, 7))))
    P2 = list(_rot(P2[0], P2[1], x1, y1, math.radians(random.gauss(0, 7))))

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
