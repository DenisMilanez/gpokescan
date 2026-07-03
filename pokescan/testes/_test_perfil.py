import json, cv2
from pathlib import Path
import detectar_icone

w, h = 1080, 2340
img = cv2.imread("capturas/1.png")
roi = (int(0.5*w), 0, w, int(0.5*h))
det = detectar_icone.detectar(img, roi_prioritaria=roi)
perfil = {"largura": w, "altura": h, "icone_pokegenie": None}
if det:
    det["rel_x"] = round(det["x"]/w, 5)
    det["rel_y"] = round(det["y"]/h, 5)
    perfil["icone_pokegenie"] = det
out = Path("calibração/perfil_1080x2340.json")
out.write_text(json.dumps(perfil, indent=2, ensure_ascii=False), encoding="utf-8")
print(out.read_text(encoding="utf-8"))
