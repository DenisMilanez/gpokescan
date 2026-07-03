# -*- coding: utf-8 -*-
"""
Injecao de um gesto no celular via sendevent (alta fidelidade: curva + timing).

Recebe os pontos gerados [(t, x, y)] (x,y em pixels da tela) e injeta o gesto no
touchscreen usando eventos crus (multitoque tipo B). Mapeia pixel -> coordenada
de toque pelos ranges descobertos na calibracao. Se o device/ranges nao forem
conhecidos ou o sendevent falhar, cai no fallback 'input swipe' (reta).

OBS: sendevent e dependente do aparelho (alguns exigem PRESSURE/TOUCH_MAJOR, ou
usam toque simples). Testar no device real; o fallback garante que sempre desliza.
"""

# Codigos de evento (linux input)
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT = 0
BTN_TOUCH = 330
ABS_MT_TRACKING_ID = 57
ABS_MT_POSITION_X = 53
ABS_MT_POSITION_Y = 54
ABS_MT_PRESSURE = 58
ABS_MT_TOUCH_MAJOR = 48
TID_UP = 4294967295            # -1 em uint32 (dedo levantado)


def _map(x, y, w, h, xmax, ymax):
    """pixel -> coordenada do touchscreen (ranges podem diferir da resolucao)."""
    tx = int(round(x * xmax / max(w, 1)))
    ty = int(round(y * ymax / max(h, 1)))
    return max(0, min(tx, xmax)), max(0, min(ty, ymax))


def montar_comando(dev, pontos, w, h, xmax, ymax, tid=0):
    """Monta a sequencia de sendevent (uma unica linha de shell) do gesto."""
    cmds = []
    def se(tp, cd, vl): cmds.append(f"sendevent {dev} {tp} {cd} {vl}")

    x0, y0 = _map(pontos[0][1], pontos[0][2], w, h, xmax, ymax)
    # toque inicia
    se(EV_ABS, ABS_MT_TRACKING_ID, tid)
    se(EV_ABS, ABS_MT_POSITION_X, x0)
    se(EV_ABS, ABS_MT_POSITION_Y, y0)
    se(EV_ABS, ABS_MT_PRESSURE, 50)
    se(EV_ABS, ABS_MT_TOUCH_MAJOR, 6)
    se(EV_KEY, BTN_TOUCH, 1)
    se(EV_SYN, SYN_REPORT, 0)

    prev_t = pontos[0][0]
    for (t, x, y) in pontos[1:]:
        tx, ty = _map(x, y, w, h, xmax, ymax)
        dt = t - prev_t
        prev_t = t
        if dt > 0.001:
            cmds.append(f"sleep {dt:.3f}")
        se(EV_ABS, ABS_MT_POSITION_X, tx)
        se(EV_ABS, ABS_MT_POSITION_Y, ty)
        se(EV_SYN, SYN_REPORT, 0)

    # levanta o dedo
    se(EV_ABS, ABS_MT_TRACKING_ID, TID_UP)
    se(EV_KEY, BTN_TOUCH, 0)
    se(EV_SYN, SYN_REPORT, 0)
    return "; ".join(cmds)


def injetar(conn, touch, pontos, w, h):
    """
    Injeta o gesto. touch = {device, x_max, y_max} (da calibracao de swipe).
    Retorna True/False. Cai no fallback se algo falhar.
    """
    if not pontos or len(pontos) < 2:
        return False
    dev = (touch or {}).get("device")
    xmax = (touch or {}).get("x_max") or w
    ymax = (touch or {}).get("y_max") or h
    if not dev:
        return injetar_fallback(conn, pontos)
    cmd = montar_comando(dev, pontos, w, h, xmax, ymax)
    serial = conn.serial()
    if not serial:
        return False
    out, err, rc = conn.adb("-s", serial, "shell", cmd, timeout=15)
    if rc != 0:
        return injetar_fallback(conn, pontos)
    return True


def injetar_fallback(conn, pontos):
    """Reta via 'input swipe' (mantem endpoints e duracao do gesto gerado)."""
    x0, y0 = pontos[0][1], pontos[0][2]
    x1, y1 = pontos[-1][1], pontos[-1][2]
    dur_ms = int((pontos[-1][0] - pontos[0][0]) * 1000) or 250
    ok, _ = conn.swipe(x0, y0, x1, y1, dur_ms)
    return ok
