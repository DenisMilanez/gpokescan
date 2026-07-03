import cv2
from pathlib import Path
import visao, detectar_icone as di

C = Path("calibração"); C.mkdir(exist_ok=True)
modelo = cv2.imread("calibração/modelo_captura_1080x2340.png")
card   = cv2.imread("capturas/1.png")
H, W = modelo.shape[:2]

# 1) X: detecta + salva template + re-localiza por template
xroi = (0, 0, int(0.40*W), int(0.40*H))
x = visao.detectar_botao_x(modelo, xroi)
print("X detectado:", x)
visao.salvar_template_circular(modelo, x["x"], x["y"], x["r"],
    C/"tpl_x.png", C/"tpl_x_mask.png")
mx = visao.localizar_template(modelo, C/"tpl_x.png", C/"tpl_x_mask.png", xroi)
print("X por template:", mx)

# 2) bloco branco
print("bloco:", visao.delimitar_bloco(modelo))

# 3) icone laranja: detecta (cor) no card, salva template, re-localiza por template
iroi = (int(0.5*W), 0, W, int(0.5*H))
ic = di.detectar(card, roi_prioritaria=iroi)
print("icone (cor):", ic)
visao.salvar_template_icone(card, ic["x"], ic["y"], ic["r"],
    C/"tpl_icone.png", C/"tpl_icone_mask.png")
mi = visao.localizar_template(card, C/"tpl_icone.png", C/"tpl_icone_mask.png", iroi)
print("icone por template:", mi)

# 4) match do template do icone em TODAS as capturas (robustez)
import glob, os
oks=0
for f in sorted(glob.glob("capturas/*.png"), key=lambda p:int(os.path.basename(p)[:-4])):
    im=cv2.imread(f); h,w=im.shape[:2]
    r=visao.localizar_template(im, C/"tpl_icone.png", C/"tpl_icone_mask.png",
                               (int(0.5*w),0,w,int(0.5*h)))
    oks += 1 if r else 0
print(f"icone por template achado em {oks}/10 capturas")
