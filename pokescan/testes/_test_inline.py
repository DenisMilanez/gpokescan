import shutil, json, datetime, random, time
from pathlib import Path
import cv2
import detectar_icone as di
import visao

C = Path("calibração")
CARD = "capturas/1.png"; RES = str(C/"modelo_captura_1080x2340.png")
w, h = 1080, 2340
roi_i = (int(0.5*w),0,w,int(0.5*h)); roi_x = (0,0,int(0.4*w),int(0.4*h))

class FakeConn:
    wm_size=(w,h)
    def __init__(self): self.n=0
    def screencap(self,d):
        self.n+=1; shutil.copy(CARD if self.n%2==1 else RES, d); return True,str(d)
    def tap(self,x,y): return True,""
    def swipe(self,*a): return True,""

# ================= CALIBRACAO (inline) =================
print("== CALIBRACAO ==")
conn=FakeConn()
t1=C/"_ref_card.png"; conn.screencap(t1); img1=cv2.imread(str(t1))
det=di.detectar(img1, roi_prioritaria=roi_i); print(" icone:", det)
visao.salvar_template_icone(img1,det["x"],det["y"],det["r"],C/"tpl_icone_1080x2340.png",C/"tpl_icone_mask_1080x2340.png")
zona=di.zona_clique(det,img1); px,py=di.ponto_clique(zona); conn.tap(px,py)
t2=C/"_ref_res.png"; conn.screencap(t2); img2=cv2.imread(str(t2))
x=visao.detectar_botao_x(img2, roi_x); print(" X:", x)
visao.salvar_template_circular(img2,x["x"],x["y"],x["r"],C/"tpl_x_1080x2340.png",C/"tpl_x_mask_1080x2340.png")
bloco=visao.delimitar_bloco(img2); print(" bloco:", bloco)
perfil={"largura":w,"altura":h,
  "icone_pokegenie":{"x":det["x"],"y":det["y"],"r":det["r"],"template":"tpl_icone_1080x2340.png","mask":"tpl_icone_mask_1080x2340.png"},
  "botao_x":{"x":x["x"],"y":x["y"],"r":x["r"],"template":"tpl_x_1080x2340.png","mask":"tpl_x_mask_1080x2340.png"},
  "bloco_resultado":{"topo":bloco["topo"],"base":bloco["base"]}}
(C/"perfil_1080x2340.json").write_text(json.dumps(perfil,indent=2,ensure_ascii=False),encoding="utf-8")
zx=(x["x"],x["y"],x["r"]*0.7); tx,ty=di.ponto_clique(zx); conn.tap(tx,ty)
print(" perfil salvo OK")

# ================= BOT (inline, 3 ciclos) =================
print("\n== BOT (3 ciclos) ==")
perfil=json.loads((C/"perfil_1080x2340.json").read_text(encoding="utf-8"))
topo_calib=perfil["bloco_resultado"]["topo"]; tol=max(12,int(0.006*h))
dia=datetime.date.today().isoformat(); pasta=Path("capturas")/dia; pasta.mkdir(parents=True,exist_ok=True)
avisos=[]
conn=FakeConn()
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
    if g: return g["x"],g["y"],g["r"]
    return bx["x"],bx["y"],bx["r"]
for n in range(1,4):
    tmp=Path("_tmp.png"); conn.screencap(tmp); img=cv2.imread(str(tmp))
    det=achar_icone(img)
    if not det: print(f"[{n}] ENCERRA: icone nao achado"); break
    zona=di.zona_clique(det,img); px,py=di.ponto_clique(zona); conn.tap(px,py)
    conn.screencap(tmp); res=cv2.imread(str(tmp))
    cv2.imwrite(str(pasta/f"{n}.png"),res)
    topo=visao.topo_bloco(res)
    if topo is None or abs(topo-topo_calib)>tol:
        avisos.append(f"imagem {n}.png: topo {topo} != {topo_calib}"); print(f"[{n}] AVISO topo")
    else:
        print(f"[{n}] ok via {det['via']} topo={topo}")
    xx=achar_x(res); zx=(xx[0],xx[1],xx[2]*0.7); tx,ty=di.ponto_clique(zx); conn.tap(tx,ty)
    conn.swipe()
if avisos:
    (pasta/"avisos.txt").write_text("\n".join(avisos),encoding="utf-8")
import glob,os
print(" prints:", [os.path.basename(p) for p in sorted(glob.glob(f"capturas/{dia}/*.png"))])
print(" avisos:", len(avisos))
