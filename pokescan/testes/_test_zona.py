import cv2, numpy as np, random, math
import detectar_icone as di

img = cv2.imread("capturas/1.png"); h, w = img.shape[:2]
roi = (int(0.5*w), 0, w, int(0.5*h))
det = di.detectar(img, roi_prioritaria=roi)
O = (det["x"], det["y"]); ro = det["r"]

# --- detecta o disco azul que contem o laranja ---
def detectar_disco(img, O, ro):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, np.array([90,25,150]), np.array([125,140,255]))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7,7),np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5,5),np.uint8))
    cnts,_ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best=None
    for c in cnts:
        a=cv2.contourArea(c)
        if a<500: continue
        (x,y),r=cv2.minEnclosingCircle(c)
        if math.hypot(x-O[0],y-O[1])<r and (best is None or a>best[0]):
            best=(a,x,y,r)
    if best: return (best[1],best[2],best[3])
    return None

# --- zona de clique ---
def zona_clique(O, ro, disco):
    if disco:
        cx,cy,R = disco
        return (cx, cy, R*0.7)          # dentro do disco, com margem
    # fallback: estima centro do disco a partir do laranja (direita+baixo)
    return (O[0]+1.6*ro, O[1]+0.8*ro, 2.0*ro)

# --- ponto de clique humano: gaussiano em torno do centro, truncado ---
def ponto_clique(zona):
    cx,cy,R = zona
    for _ in range(20):
        ang=random.uniform(0,2*math.pi)
        rad=abs(random.gauss(0, R*0.38))
        if rad<=R*0.85:
            return int(cx+rad*math.cos(ang)), int(cy+rad*math.sin(ang))
    return int(cx),int(cy)

disco = detectar_disco(img, O, ro)
zona = zona_clique(O, ro, disco)
print("laranja", O, "ro", ro)
print("disco", disco)
print("zona (cx,cy,R)", tuple(round(v,1) for v in zona))

# ================= VISUAL COMPARATIVO =================
def recorte(base):
    return base[760:940, 860:1080].copy()

# A) BOT: 40 cliques no centro exato do laranja
botimg = img.copy()
for _ in range(40):
    cv2.circle(botimg, O, 2, (0,0,255), -1)
cv2.putText(botimg,"BOT: sempre no centro",(860,780),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,0,255),2)

# B) HUMANO: 40 cliques sorteados na zona
humimg = img.copy()
zx,zy,zr = zona
cv2.circle(humimg,(int(zx),int(zy)),int(zr),(0,180,0),2)   # limite da zona
for _ in range(40):
    p=ponto_clique(zona)
    cv2.circle(humimg, p, 2, (0,0,255), -1)
cv2.putText(humimg,"HUMANO: espalhado na zona",(860,780),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,120,0),2)

comp = np.hstack([recorte(botimg), recorte(humimg)])
cv2.imwrite("calibração/_comparacao_cliques.png", comp)
print("salvo _comparacao_cliques.png")
