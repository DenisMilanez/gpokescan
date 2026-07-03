import numpy as np, cv2, math
from pathlib import Path
import gerar_swipe as G
import imgio

W,H=1080,2340
perfil=G.carregar_perfil("calibracao/swipe_horizontal/perfil_swipe.json")
print("perfil (stats):", {k:perfil[k] for k in ["n_gestos","duracao_s","inicio_x","fim_x"] if k in perfil})
saida=Path("calibracao/swipe_horizontal/gerados"); saida.mkdir(parents=True,exist_ok=True)

def cor_vel(f):
    return cv2.applyColorMap(np.uint8([[int(f*255)]]),cv2.COLORMAP_JET)[0][0]

def render_full(pts, destino, titulo):
    img=np.zeros((H,W,3),np.uint8)
    vs=[math.hypot(pts[i][1]-pts[i-1][1],pts[i][2]-pts[i-1][2])/max(pts[i][0]-pts[i-1][0],1e-4) for i in range(1,len(pts))]
    vmn,vmx=min(vs),max(vs); rng=(vmx-vmn) or 1
    for i in range(1,len(pts)):
        c=cor_vel((vs[i-1]-vmn)/rng)
        cv2.line(img,(int(pts[i-1][1]),int(pts[i-1][2])),(int(pts[i][1]),int(pts[i][2])),(int(c[0]),int(c[1]),int(c[2])),6,cv2.LINE_AA)
    cv2.circle(img,(int(pts[0][1]),int(pts[0][2])),12,(0,255,0),-1)
    cv2.circle(img,(int(pts[-1][1]),int(pts[-1][2])),12,(0,0,255),-1)
    dur=pts[-1][0]-pts[0][0]
    cv2.putText(img,f"{titulo}  dur={dur*1000:.0f}ms  vmax={vmx:.0f}px/s  pts={len(pts)}",(20,40),cv2.FONT_HERSHEY_SIMPLEX,0.7,(255,255,255),2,cv2.LINE_AA)
    imgio.imwrite(destino,img)

def tile(pts, tw=350, th=180, titulo=""):
    img=np.zeros((th,tw,3),np.uint8)
    xs=[p[1] for p in pts]; ys=[p[2] for p in pts]
    minx,maxx=min(xs),max(xs); miny,maxy=min(ys),max(ys)
    pad=26; sc=(tw-2*pad)/max(maxx-minx,1); cy=(miny+maxy)/2
    def mp(x,y): return int(pad+(x-minx)*sc), int(th/2+(y-cy)*sc)
    vs=[math.hypot(pts[i][1]-pts[i-1][1],pts[i][2]-pts[i-1][2])/max(pts[i][0]-pts[i-1][0],1e-4) for i in range(1,len(pts))]
    vmn,vmx=min(vs),max(vs); rng=(vmx-vmn) or 1
    for i in range(1,len(pts)):
        c=cor_vel((vs[i-1]-vmn)/rng)
        cv2.line(img,mp(pts[i-1][1],pts[i-1][2]),mp(pts[i][1],pts[i][2]),(int(c[0]),int(c[1]),int(c[2])),4,cv2.LINE_AA)
    cv2.circle(img,mp(pts[0][1],pts[0][2]),6,(0,255,0),-1)
    cv2.circle(img,mp(pts[-1][1],pts[-1][2]),6,(0,0,255),-1)
    dur=pts[-1][0]-pts[0][0]
    cv2.putText(img,f"{titulo} {dur*1000:.0f}ms",(8,20),cv2.FONT_HERSHEY_SIMPLEX,0.5,(200,200,200),1,cv2.LINE_AA)
    cv2.rectangle(img,(0,0),(tw-1,th-1),(60,60,60),1)
    return img

tiles=[]
for k in range(1,21):
    g=G.gerar(perfil,W,H)
    render_full(g, saida/f"gerado_{k}.png", f"gerado {k}")
    tiles.append(tile(g,titulo=f"#{k}"))
# montagem 5 linhas x 4 colunas
rows=[np.hstack(tiles[r*4:(r+1)*4]) for r in range(5)]
mont=np.vstack(rows)
imgio.imwrite(saida/"_montagem_20.png", mont)
print("OK: 20 individuais + _montagem_20.png em", saida)
