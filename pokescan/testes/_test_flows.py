import shutil, threading
from pathlib import Path
import cv2

CARD = "capturas/1.png"                     # pagina do card (tem a bola laranja)
RES  = "calibração/modelo_captura_1080x2340.png"  # resultado (tem X + bloco)

class FakeConn:
    wm_size = (1080, 2340)
    def __init__(self): self.n = 0
    def verificar_conexao(self): return True, "fake device"
    def screencap(self, destino):
        # alterna: chamada impar = card, par = resultado
        self.n += 1
        src = CARD if self.n % 2 == 1 else RES
        shutil.copy(src, destino); return True, str(destino)
    def tap(self, x, y): return True, f"tap {x},{y}"
    def swipe(self, *a): return True, "swipe"

print("===== CALIBRACAO =====")
import calibracao
c = FakeConn()
print("resultado:", calibracao.iniciar(c, log=print))
print("perfil:", calibracao.carregar_perfil(1080, 2340) is not None)

print("\n===== BOT (3 ciclos) =====")
import importlib, varredura; importlib.reload(varredura)
c2 = FakeConn()
varredura.executar(c2, 3, log=print, parar=threading.Event())

import datetime, glob, os
dia = datetime.date.today().isoformat()
pngs = sorted(glob.glob(f"capturas/{dia}/*.png"))
print("\nprints salvos:", [os.path.basename(p) for p in pngs])
