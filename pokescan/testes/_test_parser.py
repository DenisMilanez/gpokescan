import re, math
# copia EXATA do parser corrigido (mesmo regex do modulo)
_RE = re.compile(r"\[\s*([\d.]+)\]\s+(\S+)\s+(\S+)\s+(\S+)")
def parsear_swipes(linhas, x_max, y_max, w, h):
    gestos, atual = [], []
    x=y=None; tocando=False
    sx=w/(x_max+1) if x_max else 1.0; sy=h/(y_max+1) if y_max else 1.0
    for ln in linhas:
        m=_RE.search(ln)
        if not m: continue
        t,tipo,code,val=m.group(1),m.group(2),m.group(3),m.group(4); t=float(t)
        if code=="BTN_TOUCH":
            if val.upper().startswith("DOWN") or val=="00000001": tocando,atual=True,[]
            elif val.upper().startswith("UP") or val=="00000000":
                if len(atual)>=3: gestos.append(atual)
                tocando,atual=False,[]
        elif code=="ABS_MT_TRACKING_ID":
            if val.lower() in ("ffffffff","-1"):
                if len(atual)>=3: gestos.append(atual)
                tocando,atual=False,[]
            else: tocando=True
        elif code=="ABS_MT_POSITION_X": x=int(val,16)
        elif code=="ABS_MT_POSITION_Y": y=int(val,16)
        elif code=="SYN_REPORT":
            if tocando and x is not None and y is not None: atual.append((t,x*sx,y*sy))
    if len(atual)>=3: gestos.append(atual)
    return gestos

def gera(t0,x0,y0,x1,y1,dur,curv,n=25):
    L=[f'[{t0:14.6f}] EV_KEY       BTN_TOUCH            DOWN']
    for i in range(n):
        u=i/(n-1); e=0.5-0.5*math.cos(math.pi*u)
        x=x0+(x1-x0)*e; y=y0+(y1-y0)*e+curv*math.sin(math.pi*u); t=t0+dur*u
        L+=[f'[{t:14.6f}] EV_ABS       ABS_MT_POSITION_X    {int(x)&0xffffffff:08x}',
            f'[{t:14.6f}] EV_ABS       ABS_MT_POSITION_Y    {int(y)&0xffffffff:08x}',
            f'[{t:14.6f}] EV_SYN       SYN_REPORT           00000000']
    L.append(f'[{t0+dur:14.6f}] EV_KEY       BTN_TOUCH            UP')
    return L

# tambem testa o estilo TRACKING_ID (sem BTN_TOUCH), como alguns cels usam
def gera_tid(t0,x0,y0,x1,y1,dur,n=20):
    L=[f'[{t0:14.6f}] EV_ABS       ABS_MT_TRACKING_ID   000004d2']
    for i in range(n):
        u=i/(n-1); x=x0+(x1-x0)*u; y=y0+(y1-y0)*u; t=t0+dur*u
        L+=[f'[{t:14.6f}] EV_ABS       ABS_MT_POSITION_X    {int(x)&0xffffffff:08x}',
            f'[{t:14.6f}] EV_ABS       ABS_MT_POSITION_Y    {int(y)&0xffffffff:08x}',
            f'[{t:14.6f}] EV_SYN       SYN_REPORT           00000000']
    L.append(f'[{t0+dur:14.6f}] EV_ABS       ABS_MT_TRACKING_ID   ffffffff')
    return L

lin=gera(1000,860,1300,210,1290,0.32,40)+gera(1002,870,1320,200,1350,0.28,-60)
g=parsear_swipes(lin,1080,2340,1080,2340)
print("BTN_TOUCH: gestos=",len(g),"pts=",[len(x) for x in g])
g2=parsear_swipes(gera_tid(2000,850,1300,220,1310,0.3),1080,2340,1080,2340)
print("TRACKING_ID: gestos=",len(g2),"pts=",[len(x) for x in g2])
print("amostra ponto (t,x,y):", tuple(round(v,2) for v in g[0][5]))
