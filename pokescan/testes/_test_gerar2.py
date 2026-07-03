import numpy as np, cv2, math, glob, os
from pathlib import Path
import gerar_swipe as G
import imgio

W,H=1080,2340
D=Path("calibracao/swipe_horizontal"); ger=D/"gerados"; ger.mkdir(parents=True,exist_ok=True)
perfil=G.carregar_perfil(D/"perfil_swipe.json")

def cor(f): return cv2.applyColorMap(np.uint8([[int(f*255)]]),cv2.COLORMAP_JET)[0][0]

def render_full(pts, destino, titulo):
    img=np.zeros((H,W,3),np.uint8)
    vs=[math.hypot(pts[i][1]-pts[i-1][1],pts[i][2]-pts[i-1][2])/max(pts[i][0]-pts[i-1][0],1e-4) for i in range(1,len(pts))]
    vmn,vmx=min(vs),max(vs); rng=(vmx-vmn) or 1
    for i in range(1,len(pts)):
        c=cor((vs[i-1]-vmn)/rng)
        cv2.line(img,(int(pts[i-1][1]),int(pts[i-1][2])),(int(pts[i][1]),int(pts[i][2])),(int(c[0]),int(c[1]),int(c[2])),6,cv2.LINE_AA)
    cv2.circle(img,(int(pts[0][1]),int(pts[0][2])),12,(0,255,0),-1)
    cv2.circle(img,(int(pts[-1][1]),int(pts[-1][2])),12,(0,0,255),-1)
    if destino: imgio.imwrite(destino,img)
    return img

def janela(img, ww=760, wh=230, rotulo=""):
    mask=img.max(axis=2)>30; mask[:100,:]=False
    ys,xs=np.where(mask)
    out=np.zeros((wh,ww,3),np.uint8)
    if len(xs)>=5:
        cx,cy=int(xs.mean()),int(ys.mean()); x0=cx-ww//2; y0=cy-wh//2
        sx0,sy0=max(0,x0),max(0,y0); sx1,sy1=min(img.shape[1],x0+ww),min(img.shape[0],y0+wh)
        out[sy0-y0:sy0-y0+(sy1-sy0), sx0-x0:sx0-x0+(sx1-sx0)]=img[sy0:sy1,sx0:sx1]
    cv2.rectangle(out,(0,0),(ww-1,wh-1),(70,70,70),1)
    if rotulo: cv2.putText(out,rotulo,(10,26),cv2.FONT_HERSHEY_SIMPLEX,0.6,(210,210,210),1,cv2.LINE_AA)
    return out

def grade(tiles, cols):
    while len(tiles)%cols: tiles.append(np.zeros_like(tiles[0]))
    rows=[np.hstack(tiles[r*cols:(r+1)*cols]) for r in range(len(tiles)//cols)]
    return np.vstack(rows)

# ---- 1) montagem dos CAPTURADOS (a partir dos swipe_N.png ja renderizados) ----
caps=[]
arqs=sorted(glob.glob(str(D/"swipe_*.png")), key=lambda p:int(os.path.basename(p)[6:-4]))
for p in arqs:
    img=imgio.imread(p)
    if img is not None: caps.append(janela(img, rotulo=os.path.basename(p)[:-4]))
imgio.imwrite(D/"_montagem_CAPTURADOS.png", grade(caps,4))
print("capturados:", len(caps))

# ---- 2) montagem dos GERADOS (novo algoritmo suave) ----
gers=[]
for k in range(1,21):
    g=G.gerar(perfil,W,H)
    img=render_full(g, ger/f"gerado_{k}.png", f"gerado {k}")
    dur=g[-1][0]-g[0][0]
    gers.append(janela(img, rotulo=f"#{k} {dur*1000:.0f}ms"))
imgio.imwrite(ger/"_montagem_GERADOS.png", grade(gers,4))
print("gerados: 20")
