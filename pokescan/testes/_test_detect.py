import cv2, glob, os
import detectar_icone as di

# regiao prioritaria = quad_sup_dir (0.5,0,1,0.5)
def roi(w,h): return (int(0.5*w),0,w,int(0.5*h))

for f in sorted(glob.glob("capturas/*.png"), key=lambda p:int(os.path.basename(p)[:-4])):
    img=cv2.imread(f); h,w=img.shape[:2]
    r=di.detectar(img, roi_prioritaria=roi(w,h))
    print(os.path.basename(f), r)

# marca em 1.png
img=cv2.imread("capturas/1.png"); h,w=img.shape[:2]
r=di.detectar(img, roi_prioritaria=roi(w,h))
if r:
    cv2.circle(img,(r["x"],r["y"]),r["r"]+6,(0,0,255),4)
    cv2.drawMarker(img,(r["x"],r["y"]),(0,0,255),cv2.MARKER_CROSS,40,3)
    cv2.imwrite("calibração/_deteccao_marcada.png", img[650:950,680:1080])
    print("marcado")
