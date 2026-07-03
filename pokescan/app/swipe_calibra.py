# -*- coding: utf-8 -*-
"""
Calibracao de swipe horizontal (perfil de gesto do usuario).

Ideia: gravar varios deslizes REAIS seus (via getevent), extrair um perfil
estatistico (duracao, curvatura, velocidade, tremor, dispersao de inicio/fim) e,
depois, GERAR gestos novos amostrados desse perfil (nunca repetir o mesmo) para
o bot injetar via sendevent. Isso mantem os movimentos dentro de uma distribuicao
humana real -> muito mais dificil de um detector identificar como bot.

Este modulo tem:
  - descobrir_touch(): auto-descobre o /dev/input/eventX do touchscreen + ranges.
  - gravar(): roda getevent por N segundos e devolve as linhas.
  - parsear_swipes(): quebra o stream em gestos [(t, x_px, y_px), ...].
  - render_swipe(): desenha o gesto em fundo preto, colorido pela VELOCIDADE.
  - extrair_perfil(): estatisticas simples -> perfil salvo em JSON.

Obs. honesta: pressao real quase nunca existe em telas capacitivas; por isso a
humanizacao usa trajetoria + tempo (velocidade/curvatura/tremor), nao pressao.
"""

import json
import re
import statistics as st
import subprocess
import time
from pathlib import Path

import numpy as np

try:
    import cv2
    import imgio
except ImportError:
    cv2 = None
    imgio = None

DIR_BASE = Path(__file__).resolve().parent
DIR_SWIPE = DIR_BASE / "calibracao" / "swipe_horizontal"


# ============================================================ #
# 1) Auto-descoberta do touchscreen
# ============================================================ #
def descobrir_touch(adb_path, serial):
    """
    Roda 'getevent -pl' e acha o device multitoque (o que reporta
    ABS_MT_POSITION_X). Retorna {device, x_max, y_max} ou None.
    """
    try:
        p = subprocess.run(
            [adb_path, "-s", serial, "shell", "getevent", "-pl"],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        return None
    dev, xmax, ymax = None, None, None
    achou = {}
    for linha in p.stdout.splitlines():
        m = re.search(r"add device \d+:\s*(\S+)", linha)
        if m:
            dev = m.group(1)
            continue
        if "ABS_MT_POSITION_X" in linha:
            mm = re.search(r"max (\d+)", linha)
            if mm and dev:
                achou[dev] = achou.get(dev, {}); achou[dev]["x_max"] = int(mm.group(1))
                achou[dev]["dev"] = dev
        if "ABS_MT_POSITION_Y" in linha:
            mm = re.search(r"max (\d+)", linha)
            if mm and dev:
                achou[dev] = achou.get(dev, {}); achou[dev]["y_max"] = int(mm.group(1))
    # escolhe o device que tem X e Y
    for d, info in achou.items():
        if "x_max" in info and "y_max" in info:
            return {"device": d, "x_max": info["x_max"], "y_max": info["y_max"]}
    return None


# ============================================================ #
# 2) Gravacao do getevent por N segundos
# ============================================================ #
def gravar(adb_path, serial, device, segundos=15):
    """Roda 'getevent -lt <device>' por 'segundos' e retorna as linhas lidas."""
    cmd = [adb_path, "-s", serial, "shell", "getevent", "-lt", device]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    linhas = []
    t0 = time.time()
    try:
        while time.time() - t0 < segundos:
            linha = proc.stdout.readline()
            if linha:
                linhas.append(linha.rstrip("\n"))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
    return linhas


# ============================================================ #
# 3) Parser: stream -> lista de gestos [(t, x_px, y_px), ...]
# ============================================================ #
_RE = re.compile(r"\[\s*([\d.]+)\]\s+(\S+)\s+(\S+)\s+(\S+)")


def parsear_swipes(linhas, x_max, y_max, w, h):
    """
    Converte as linhas do getevent -lt em uma lista de gestos.
    Cada gesto e uma lista de (t_seg, x_px, y_px). Segmenta por BTN_TOUCH
    DOWN/UP (ou tracking id -1). Mapeia coord de toque -> pixel.
    """
    gestos, atual = [], []
    x = y = None
    tocando = False
    sx = w / (x_max + 1) if x_max else 1.0
    sy = h / (y_max + 1) if y_max else 1.0

    for ln in linhas:
        m = _RE.search(ln)
        if not m:
            continue
        t, tipo, code, val = m.group(1), m.group(2), m.group(3), m.group(4)
        t = float(t)
        if code == "BTN_TOUCH":
            if val.upper().startswith("DOWN") or val == "00000001":
                tocando, atual = True, []
            elif val.upper().startswith("UP") or val == "00000000":
                if len(atual) >= 3:
                    gestos.append(atual)
                tocando, atual = False, []
        elif code == "ABS_MT_TRACKING_ID":
            if val.lower() in ("ffffffff", "-1"):
                if len(atual) >= 3:
                    gestos.append(atual)
                tocando, atual = False, []
            else:
                tocando = True
        elif code == "ABS_MT_POSITION_X":
            x = int(val, 16)
        elif code == "ABS_MT_POSITION_Y":
            y = int(val, 16)
        elif code == "SYN_REPORT":
            if tocando and x is not None and y is not None:
                atual.append((t, x * sx, y * sy))
    if len(atual) >= 3:
        gestos.append(atual)
    return gestos


# ============================================================ #
# 4) Render: desenha o gesto colorido pela VELOCIDADE (fundo preto)
# ============================================================ #
def render_swipe(pontos, w, h, destino, titulo=""):
    """
    Desenha o gesto em fundo preto. Cor do traco = velocidade (azul=lento,
    verde=medio, vermelho=rapido). Marca inicio (verde) e fim (vermelho).
    """
    if cv2 is None:
        raise RuntimeError("Pillow/OpenCV necessario")
    img = np.zeros((h, w, 3), np.uint8)
    if len(pontos) < 2:
        imgio.imwrite(destino, img); return
    # velocidade por segmento (px/s)
    vs = []
    for i in range(1, len(pontos)):
        t0, x0, y0 = pontos[i - 1]; t1, x1, y1 = pontos[i]
        dt = max(t1 - t0, 1e-4)
        vs.append(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / dt)
    vmin, vmax = min(vs), max(vs)
    rng = (vmax - vmin) or 1.0
    for i in range(1, len(pontos)):
        _, x0, y0 = pontos[i - 1]; _, x1, y1 = pontos[i]
        f = (vs[i - 1] - vmin) / rng                 # 0=lento ... 1=rapido
        # colormap azul->verde->vermelho (BGR)
        cor = cv2.applyColorMap(np.uint8([[int(f * 255)]]), cv2.COLORMAP_JET)[0][0]
        cv2.line(img, (int(x0), int(y0)), (int(x1), int(y1)),
                 (int(cor[0]), int(cor[1]), int(cor[2])), 6, cv2.LINE_AA)
    # inicio/fim
    cv2.circle(img, (int(pontos[0][1]), int(pontos[0][2])), 12, (0, 255, 0), -1)
    cv2.circle(img, (int(pontos[-1][1]), int(pontos[-1][2])), 12, (0, 0, 255), -1)
    # legenda
    dur = pontos[-1][0] - pontos[0][0]
    txt = f"{titulo}  dur={dur*1000:.0f}ms  vmax={vmax:.0f}px/s  pts={len(pontos)}"
    cv2.putText(img, txt, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (255, 255, 255), 2, cv2.LINE_AA)
    imgio.imwrite(destino, img)


# ============================================================ #
# 5) Perfil estatistico do gesto
# ============================================================ #
def extrair_perfil(gestos):
    """
    Extrai estatisticas simples dos gestos capturados:
      duracao, comprimento, curvatura (desvio lateral / corda),
      velocidade (pico e media), tremor, e a dispersao de inicio/fim.
    Guarda tambem os perfis de velocidade normalizados (templates).
    """
    duracoes, comprimentos, curvaturas = [], [], []
    v_pico, v_med, tremores = [], [], []
    inicios, fins, templates = [], [], []

    for g in gestos:
        ts = [p[0] for p in g]; xs = [p[1] for p in g]; ys = [p[2] for p in g]
        dur = ts[-1] - ts[0]
        if dur <= 0:
            continue
        seg = [((xs[i] - xs[i-1])**2 + (ys[i] - ys[i-1])**2) ** 0.5
               for i in range(1, len(g))]
        comp = sum(seg)
        corda = ((xs[-1]-xs[0])**2 + (ys[-1]-ys[0])**2) ** 0.5 or 1.0
        # curvatura: maior desvio perpendicular da reta inicio-fim / corda
        desvio = _max_desvio_perp(xs, ys)
        # velocidades
        vsegs = [seg[i] / max(ts[i+1]-ts[i], 1e-4) for i in range(len(seg))]
        # perfil normalizado (distancia acumulada 0..1 x tempo 0..1)
        acum = np.cumsum([0] + seg) / comp
        tnorm = (np.array(ts) - ts[0]) / dur
        templates.append(list(zip(tnorm.round(4).tolist(), acum.round(4).tolist())))

        duracoes.append(dur); comprimentos.append(comp)
        curvaturas.append(desvio / corda)
        v_pico.append(max(vsegs)); v_med.append(comp / dur)
        tremores.append(desvio)
        inicios.append((xs[0], ys[0])); fins.append((xs[-1], ys[-1]))

    def ms(v): return {"media": round(st.mean(v), 3),
                       "std": round(st.pstdev(v), 3) if len(v) > 1 else 0.0} if v else None
    # features POR GESTO (permitem reamostrar swipes reais + perturbar na geracao)
    gestos_list = [
        {"dur": round(d, 4), "dist": round(c, 1),
         "inicio": [round(a[0], 1), round(a[1], 1)],
         "fim": [round(b[0], 1), round(b[1], 1)]}
        for d, c, a, b in zip(duracoes, comprimentos, inicios, fins)]
    perfil = {
        "n_gestos": len(duracoes),
        "gestos": gestos_list,
        "duracao_s": ms(duracoes),
        "comprimento_px": ms(comprimentos),
        "curvatura": ms(curvaturas),
        "v_pico_pxs": ms(v_pico),
        "v_media_pxs": ms(v_med),
        "tremor_px": ms(tremores),
        "inicio_x": ms([p[0] for p in inicios]),
        "inicio_y": ms([p[1] for p in inicios]),
        "fim_x": ms([p[0] for p in fins]),
        "fim_y": ms([p[1] for p in fins]),
        "templates_velocidade": templates,   # usados p/ warp na geracao
    }
    return perfil


def _max_desvio_perp(xs, ys):
    """Maior distancia perpendicular dos pontos a reta (inicio->fim)."""
    x0, y0, x1, y1 = xs[0], ys[0], xs[-1], ys[-1]
    dx, dy = x1 - x0, y1 - y0
    n = (dx*dx + dy*dy) ** 0.5 or 1.0
    md = 0.0
    for x, y in zip(xs, ys):
        d = abs(dy * (x - x0) - dx * (y - y0)) / n
        md = max(md, d)
    return md
