# -*- coding: utf-8 -*-
# Script unico para regenerar o overlay novo (evita cache stale do shell).
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

_T, _M = 1/3, 2/3
GRADE = {
    "sup_esq": (0.0, 0.0, _T, _T), "sup_centro": (_T, 0.0, _M, _T), "sup_dir": (_M, 0.0, 1.0, _T),
    "meio_esq": (0.0, _T, _T, _M), "meio_centro": (_T, _T, _M, _M), "meio_dir": (_M, _T, 1.0, _M),
    "inf_esq": (0.0, _M, _T, 1.0), "inf_centro": (_T, _M, _M, 1.0), "inf_dir": (_M, _M, 1.0, 1.0),
}

DIR = Path(__file__).resolve().parent
img = Image.open(DIR / "capturas" / "1.png").convert("RGB")
d = ImageDraw.Draw(img)
w, h = img.size


def linha(p0, p1, cor, lg):
    d.line([p0, p1], fill=(0, 0, 0), width=lg + 4)
    d.line([p0, p1], fill=cor, width=lg)


linha((w//2, 0), (w//2, h), (255, 140, 0), 8)
linha((0, h//2), (w, h//2), (255, 140, 0), 8)
for f in (_T, _M):
    linha((int(f*w), 0), (int(f*w), h), (0, 220, 255), 6)
    linha((0, int(f*h)), (w, int(f*h)), (0, 220, 255), 6)

try:
    fonte = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
except Exception:
    fonte = ImageFont.load_default()

for nome, (x0, y0, x1, y1) in GRADE.items():
    cx, cy = int((x0+x1)/2*w), int((y0+y1)/2*h)
    try:
        bb = d.textbbox((0, 0), nome, font=fonte); tw, th = bb[2]-bb[0], bb[3]-bb[1]
    except Exception:
        tw, th = len(nome)*12, 16
    pad = 8
    d.rectangle([cx-tw//2-pad, cy-th//2-pad, cx+tw//2+pad, cy+th//2+pad],
                fill=(0, 130, 160), outline=(0, 0, 0), width=2)
    d.text((cx-tw//2, cy-th//2), nome, fill=(255, 255, 255), font=fonte,
           stroke_width=2, stroke_fill=(0, 0, 0))

out = DIR / "calibração" / "_grade_overlay_1080x2340.png"
img.save(out)
print("salvo:", out)
