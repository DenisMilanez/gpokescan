# -*- coding: utf-8 -*-
"""
Calibracao de SWIPE horizontal (perfil de gesto do usuario).

Fluxo (chamado pela GUI ou via linha de comando):
    .venv\\Scripts\\python.exe calibrar_swipe.py [segundos]

  1. Conecta pela config salva e auto-descobre o touchscreen.
  2. Janelinha com contagem de 5s + bip; grava N segundos de getevent enquanto
     voce desliza; bip ao terminar.
  3. Salva perfil_swipe.json (com features por gesto + touch), renderiza cada
     swipe capturado e a montagem CAPTURADOS.
  4. Gera 20 swipes de teste + a montagem GERADOS na subpasta 'gerados'.
"""

import json
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

import config_store
import swipe_calibra as sw
import swipe_util
from adb_connect import ADBConnector, PORTA_FIXA

COOLDOWN = 5
N_TESTES = 20

try:
    import winsound

    def bip(f=880, ms=200):
        try: winsound.Beep(int(f), int(ms))
        except Exception: pass
except Exception:
    def bip(f=880, ms=200):
        try: print("\a", end="", flush=True)
        except Exception: pass


def bip_inicio(): bip(1047, 140); bip(1319, 160)
def bip_fim(): bip(880, 160); bip(660, 160); bip(520, 320)


def preparar_conexao():
    cfg = config_store.carregar()
    conn = ADBConnector(cfg.get("adb_path", ""), log=print)
    ok, info = conn.testar_adb()
    if not ok:
        return None, f"adb indisponivel: {info}"
    ok, resumo = conn.verificar_conexao()
    if not ok and cfg.get("ip"):
        conn.conectar(cfg["ip"], PORTA_FIXA)
        ok, resumo = conn.verificar_conexao()
    if not ok:
        return None, f"sem device: {resumo}"
    return conn, None


def rodar(conn, segundos, ui):
    w, h = conn.wm_size
    serial = conn.serial()
    ui("Descobrindo o touchscreen...")
    touch = sw.descobrir_touch(conn.adb_path, serial)
    if not touch:
        ui("ERRO: nao achei o touchscreen (getevent -pl)."); return
    ui(f"Touch: {touch['device']} ({touch['x_max']}x{touch['y_max']})")

    for s in range(COOLDOWN, 0, -1):
        ui(f"Prepare-se... {s}"); time.sleep(1)

    ui(f"DESLIZE AGORA!  ({segundos}s)")
    bip_inicio()
    linhas = sw.gravar(conn.adb_path, serial, touch["device"], segundos)
    bip_fim()
    ui("Processando...")

    gestos = sw.parsear_swipes(linhas, touch["x_max"], touch["y_max"], w, h)
    sw.DIR_SWIPE.mkdir(parents=True, exist_ok=True)
    for f in sw.DIR_SWIPE.glob("swipe_*.png"):
        try: f.unlink()
        except Exception: pass

    if not gestos:
        ui("Nenhum swipe detectado. Deslize na tela do celular e tente de novo.")
        return

    # renderiza cada swipe capturado + montagem CAPTURADOS
    for i, g in enumerate(gestos, 1):
        swipe_util.render_swipe(g, w, h, sw.DIR_SWIPE / f"swipe_{i}.png", titulo=f"swipe {i}")
    swipe_util.montar(sw.DIR_SWIPE, "swipe_*.png", sw.DIR_SWIPE / "_montagem_CAPTURADOS.png")

    # perfil (features por gesto) + touch + resolucao
    perfil = sw.extrair_perfil(gestos)
    perfil["largura"], perfil["altura"] = w, h
    perfil["touch"] = touch
    (sw.DIR_SWIPE / "perfil_swipe.json").write_text(
        json.dumps(perfil, ensure_ascii=False, indent=2), encoding="utf-8")

    # 20 testes gerados + montagem GERADOS
    ui("Gerando 20 swipes de teste...")
    swipe_util.gerar_testes(perfil, w, h, sw.DIR_SWIPE / "gerados", n=N_TESTES)

    bip(988, 220)
    ui(f"Pronto! {len(gestos)} capturados + {N_TESTES} testes.\n"
       f"Veja as montagens em calibracao/swipe_horizontal/ (e /gerados).")


def main():
    segundos = 15
    if len(sys.argv) > 1:
        try: segundos = max(3, int(sys.argv[1]))
        except ValueError: pass

    conn, erro = preparar_conexao()
    root = tk.Tk()
    root.title("Calibracao de Swipe")
    root.geometry("470x230")
    root.configure(bg="#111")
    lbl = tk.Label(root, text="", bg="#111", fg="#0f0",
                   font=("Segoe UI", 15, "bold"), wraplength=430, justify="center")
    lbl.pack(expand=True, fill="both", padx=16, pady=16)

    def ui(msg): root.after(0, lambda: lbl.config(text=msg))

    if erro:
        lbl.config(text=f"Falha: {erro}\nConecte o celular pela GUI primeiro.", fg="#f55")
    else:
        threading.Thread(target=lambda: rodar(conn, segundos, ui), daemon=True).start()
    root.mainloop()


if __name__ == "__main__":
    main()
