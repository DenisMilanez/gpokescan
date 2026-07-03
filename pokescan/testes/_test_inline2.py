import shutil, json, datetime, random, math
from pathlib import Path
import cv2, numpy as np
import detectar_icone as di
import visao

C=Path("calibração")
CARD="capturas/1.png"; RES=str(C/"modelo_captura_1080x2340.png")
w,h=1080,2340
roi_i=(int(0.5*w),0,w,int(0.5*h)); roi_x=(0,0,int(0.4*w),int(0.4*h))

# --- zona/ponto de clique (codigo validado em _test_zona.py) ---
def detectar_disco(img,O,ro):
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
    m=cv2.inRange(hsv,np.array([90,25,150]),np.array([125,140,255]))
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
    m=cv2.morphologyEx(m,cv2.MORPH_OPEN,np.ones((5,5),np.uint8))
    cnts,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    best=None
    for c in cnts:
        a=cv2.contourArea(c)
        if a<500: continue
        (x,y),r=cv2.minEnclosingCircle(c)
        if math.hypot(x-O[0],y-O[1])<r and (best is None or a>best[0]): best=(a,x,y,r)
    return (best[1],best[2],best[3]) if best else None
def zona_clique(det,img):
    O=(det["x"],det["y"]); ro=det["r"]; d=detectar_disco(img,O,ro)
    return (d[0],d[1],d[2]*0.7) if d else (O[0]+1.6*ro,O[1]+0.8*ro,2.0*ro)
def ponto(z):
    cx,cy,R=z
    for _ in range(20):
        a=random.uniform(0,2*math.pi); r=abs(random.gauss(0,R*0.38))
        if r<=R*0.85: return int(cx+r*math.cos(a)),int(cy+r*math.sin(a))
    return int(cx),int(cy)

class FakeConn:
    wm_size=(w,h)
    def __init__(self): self.n=0
    def screencap(self,d): self.n+=1; shutil.copy(CARD if self.n%2 else RES,d); return True,""
    def tap(self,x,y): return True,""
    def swipe(self,*a): return True,""

print("== CALIBRACAO ==")
conn=FakeConn()
conn.screencap(C/"_a.png"); img1=cv2.imread(str(C/"_a.png"))
det=di.detectar(img1,roi_prioritaria=roi_i); print(" icone:",det)
visao.salvar_template_icone(img1,det["x"],det["y"],det["r"],C/"tpl_icone_1080x2340.png",C/"tpl_icone_mask_1080x2340.png")
z=zona_clique(det,img1); conn.tap(*ponto(z))
conn.screencap(C/"_b.png"); img2=cv2.imread(str(C/"_b.png"))
x=visao.detectar_botao_x(img2,roi_x); print(" X:",x)
visao.salvar_template_circular(img2,x["x"],x["y"],x["r"],C/"tpl_x_1080x2340.png",C/"tpl_x_mask_1080x2340.png")
bl=visao.delimitar_bloco(img2); print(" bloco:",bl)
perfil={"largura":w,"altura":h,
 "icone_pokegenie":{"x":det["x"],"y":det["y"],"r":det["r"],"template":"tpl_icone_1080x2340.png","mask":"tpl_icone_mask_1080x2340.png"},
 "botao_x":{"x":x["x"],"y":x["y"],"r":x["r"],"template":"tpl_x_1080x2340.png","mask":"tpl_x_mask_1080x2340.png"},
 "bloco_resultado":{"topo":bl["topo"],"base":bl["base"]}}
(C/"perfil_1080x2340.json").write_text(json.dumps(perfil,indent=2,ensure_ascii=False),encoding="utf-8")
conn.tap(*ponto((x["x"],x["y"],x["r"]*0.7)))
print(" perfil OK")

print("\n== BOT (3 ciclos) ==")
topo_calib=bl["topo"]; tol=max(12,int(0.006*h))
dia=datetime.date.today().isoformat(); pasta=Path("capturas")/dia; pasta.mkdir(parents=True,exist_ok=True)
avisos=[]; conn=FakeConn()
def achar_icone(img):
    ic=perfil["icone_pokegenie"]
    m=visao.localizar_template(img,C/ic["template"],C/ic["mask"],roi_i,limiar=0.6)
    if m: return {"x":m["x"],"y":m["y"],"r":ic["r"],"via":"template"}
    d=di.detectar(img,roi_prioritaria=roi_i)
    if d: d["via"]="cor"; return d
    return None
def achar_x(img):
    bx=perfil["botao_x"]
    m=visao.localizar_template(img,C/bx["template"],C/bx["mask"],roi_x,limiar=0.6)
    if m: return m["x"],m["y"],bx["r"]
    g=visao.detectar_botao_x(img,roi_x)
    return (g["x"],g["y"],g["r"]) if g else (bx["x"],bx["y"],bx["r"])
for n in range(1,4):
    tmp=Path("_tmp.png"); conn.screencap(tmp); img=cv2.imread(str(tmp))
    det=achar_icone(img)
    if not det: print(f"[{n}] ENCERRA"); break
    conn.tap(*ponto(zona_clique(det,img)))
    conn.screencap(tmp); res=cv2.imread(str(tmp)); cv2.imwrite(str(pasta/f"{n}.png"),res)
    topo=visao.topo_bloco(res)
    if topo is None or abs(topo-topo_calib)>tol: avisos.append(f"{n}.png topo {topo}!={topo_calib}"); print(f"[{n}] AVISO")
    else: print(f"[{n}] ok via {det['via']} topo={topo}")
    xx=achar_x(res); conn.tap(*ponto((xx[0],xx[1],xx[2]*0.7))); conn.swipe()
if avisos: (pasta/"avisos.txt").write_text("\n".join(avisos),encoding="utf-8")
import glob,os
print(" prints:",[os.path.basename(p) for p in sorted(glob.glob(f"capturas/{dia}/*.png"))]," avisos:",len(avisos))
