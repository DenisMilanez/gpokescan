import shutil
from pathlib import Path
import calibracao, regioes

class FakeConn:
    wm_size = (1080, 2340)
    def verificar_conexao(self): return True, "fake device"
    def screencap(self, destino):
        shutil.copy("capturas/1.png", destino); return True, str(destino)

ok = calibracao.iniciar(FakeConn(), log=print)
print("iniciar retornou:", ok)
print("perfil carregado:", calibracao.carregar_perfil(1080, 2340))
