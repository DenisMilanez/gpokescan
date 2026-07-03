import numpy as np, cv2, math, glob, os
from pathlib import Path
import gerar_v as G
import imgio

W,H=1080,2340
D=Path("calibracao/swipe_horizontal"); ger=D/"gerados"; ger.mkdir(parents=True,exist_ok=True)
perfil=G.carregar_perfil(D/"perfil_swipe.json")

# extrai gestos reais (inicio=verde, fim=vermelho) dos PNGs capturados
gestos=[]
for p in sorted(glob.glob(str(D/"swipe_*.png")), key=lambda x:int(os.path.basename(x)[6:-4])):
    img=imgio.imread(p); B,Gc,R=img[:,:,0].astype(int),img[:,:,1].astype(int),img[:,:,2].astype(int)
    gm=(Gc>140)&(R<90)&(B<90); rm=(R>140)&(Gc<90)&(B<90)
    gy,gx=np.where(gm); ry,rx=np.where(rm)
    if len(gx)==0 or len(rx)==0: continue
    sx,sy=float(gx.mean()),float(gy.mean()); ex,ey=float(rx.mean()),float(ry.mean())
    gestos.append({"inicio":[sx,sy],"fim":[ex,ey],"dist":math.hypot(ex-sx,ey-sy)})
perfil["gestos"]=gestos
print("gestos reais injetados:", len(gestos))

def cor(f): return cv2.applyColorMap(np.uint8([[int(f*255)]]),cv2.COLORMAP_JET)[0][0]
def render_full(pts):
    img=np.zeros((H,W,3),np.uint8)
    vs=[math.hypot(pts[i][1]-pts[i-1][1],pts[i][2]-pts[i-1][2])/max(pts[i][0]-pts[i-1][0],1e-4) for i in range(1,len(pts))]
    vmn,vmx=min(vs),max(vs); rng=(vmx-vmn) or 1
    for i in range(1,len(pts)):
        c=cor((vs[i-1]-vmn)/rng)
        cv2.line(img,(int(pts[i-1][1]),int(pts[i-1][2])),(int(pts[i][1]),int(pts[i][2])),(int(c[0]),int(c[1]),int(c[2])),6,cv2.LINE_AA)
    cv2.circle(img,(int(pts[0][1]),int(pts[0][2])),12,(0,255,0),-1)
    cv2.circle(img,(int(pts[-1][1]),int(pts[-1][2])),12,(0,0,255),-1)
    return img
def janela(img,ww=760,wh=230,rot=""):
    m=img.max(axis=2)>30; m[:100,:]=False; ys,xs=np.where(m); out=np.zeros((wh,ww,3),np.uint8)
    if len(xs)>=5:
        cx,cy=int(xs.mean()),int(ys.mean()); x0,y0=cx-ww//2,cy-wh//2
        sx0,sy0=max(0,x0),max(0,y0); sx1,sy1=min(img.shape[1],x0+ww),min(img.shape[0],y0+wh)
        out[sy0-y0:sy0-y0+(sy1-sy0),sx0-x0:sx0-x0+(sx1-sx0)]=img[sy0:sy1,sx0:sx1]
    cv2.rectangle(out,(0,0),(ww-1,wh-1),(70,70,70),1)
    if rot: cv2.putText(out,rot,(10,26),cv2.FONT_HERSHEY_SIMPLEX,0.6,(210,210,210),1,cv2.LINE_AA)
    return out
def grade(tiles,cols):
    while len(tiles)%cols: tiles.append(np.zeros_like(tiles[0]))
    return np.vstack([np.hstack(tiles[r*cols:(r+1)*cols]) for r in range(len(tiles)//cols)])

tiles=[]; dists=[]
for k in range(1,21):
    g=G.gerar(perfil,W,H)
    d=math.hypot(g[-1][1]-g[0][1],g[-1][2]-g[0][2]); dists.append(round(d))
    img=render_full(g); imgio.imwrite(ger/f"gerado_{k}.png",img)
    tiles.append(janela(img,rot=f"#{k} {d:.0f}px"))
imgio.imwrite(ger/"_montagem_GERADOS.png", grade(tiles,4))
print("distancias geradas ordenadas:", sorted(dists))
