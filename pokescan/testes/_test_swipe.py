import numpy as np, math, random, json
from pathlib import Path
import swipe_calibra as sw

W,H=1080,2340
D=Path("calibração/swipe_horizontal"); D.mkdir(parents=True, exist_ok=True)

# ---------- 1) TESTA O PARSER com getevent -lt sintetico ----------
def gera_getevent(t0, x0,y0,x1,y1, dur, curv, n=25):
    linhas=[f"[{t0:14.6f}] EV_KEY       BTN_TOUCH            DOWN"]
    for i in range(n):
        u=i/(n-1)
        e=0.5-0.5*math.cos(math.pi*u)            # easing ease-in-out
        x=x0+(x1-x0)*e
        y=y0+(y1-y0)*e + curv*math.sin(math.pi*u) + random.uniform(-3,3)
        t=t0+dur*u
        linhas+=[f"[{t:14.6f}] EV_ABS       ABS_MT_POSITION_X    {int(x)&0xffffffff:08x}",
                 f"[{t:14.6f}] EV_ABS       ABS_MT_POSITION_Y    {int(y)&0xffffffff:08x}",
                 f"[{t:14.6f}] EV_SYN       SYN_REPORT           00000000"]
    linhas.append(f"[{t0+dur:14.6f}] EV_KEY       BTN_TOUCH            UP")
    return linhas

linhas=[]
linhas+=gera_getevent(1000.0, 860,1300, 210,1290, 0.32, 40)
linhas+=gera_getevent(1002.0, 870,1320, 200,1350, 0.28, -60)
gestos=sw.parsear_swipes(linhas, 1080, 2340, W, H)
print("PARSER: gestos recuperados =", len(gestos), "| pts:", [len(g) for g in gestos])

# ---------- 2) RENDER de 3 swipes humanos variados ----------
def swipe_humano(seed):
    random.seed(seed)
    x0,y0=random.uniform(820,900),random.uniform(1280,1360)
    x1,y1=random.uniform(180,240),random.uniform(1280,1380)
    dur=random.uniform(0.24,0.40); curv=random.uniform(-70,70)
    n=random.randint(22,30); pts=[]
    for i in range(n):
        u=i/(n-1); e=0.5-0.5*math.cos(math.pi*u)
        x=x0+(x1-x0)*e + random.uniform(-2,2)
        y=y0+(y1-y0)*e + curv*math.sin(math.pi*u) + random.uniform(-3,3)
        t=dur*u
        pts.append((t,x,y))
    return pts

for k in range(1,4):
    pts=swipe_humano(k*7)
    sw.render_swipe(pts, W, H, D/f"swipe_{k}.png", titulo=f"swipe {k}")
print("RENDER: 3 imagens salvas em", D)

# ---------- 3) PERFIL ----------
perfil=sw.extrair_perfil([swipe_humano(s) for s in range(20)])
perfil_show={k:v for k,v in perfil.items() if k!="templates_velocidade"}
print("PERFIL (20 gestos):"); print(json.dumps(perfil_show, indent=2, ensure_ascii=False))
(D/"perfil_swipe.json").write_text(json.dumps(perfil, ensure_ascii=False), encoding="utf-8")
