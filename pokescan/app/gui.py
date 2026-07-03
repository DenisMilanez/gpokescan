# -*- coding: utf-8 -*-
"""
GoPokeScan - Dashboard (Tkinter)

Painel principal no estilo do mockup:
  - STATUS & CONEXAO : mostra Conectado/Desconectado; botoes 'Testar Conexao'
    e 'Configuracoes' (abre o formulario de conexao). Config salva em config.json;
    ao abrir, tenta reconectar sozinho com os dados salvos.
  - INFO DO DISPOSITIVO : mostra as dimensoes da tela (so quando conectado) e o
    botao 'Calibrar Tela de Jogo'.
  - COLETA DE DADOS : campo com o limite (nº de Pokemon = nº de ciclos) e o botao
    'INICIAR VARREDURA'.
  - LOG : reflete tudo que esta acontecendo (teste de conexao, varredura...).
"""

import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import calibracao
import config_store
import pokegenie
import varredura
from adb_connect import ADBConnector, fluxo_conexao

# ------------------------------------------------------------------ #
# Paleta (aproxima o visual do mockup dentro dos limites do Tkinter)
# ------------------------------------------------------------------ #
BG_APP = "#e9f1f7"
BG_CARD = "#f7fbfd"
BORDA = "#b9d0e0"
TXT = "#173747"
AZUL = "#2f7fd1"
CINZA = "#8494a0"
VERDE = "#37b24d"
VERMELHO = "#e03131"

CANDIDATOS_ADB = [
    r"D:\platform-tools\adb.exe",
    r"C:\platform-tools\adb.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
]


def detectar_adb():
    """Tenta achar o adb.exe no PATH ou nos caminhos candidatos comuns."""
    no_path = shutil.which("adb")
    if no_path:
        return no_path
    for c in CANDIDATOS_ADB:
        if c and Path(c).exists():
            return c
    return ""


class GoPokeScanGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GOPOKESCAN v1.0 (Pokemon GO Data Utility)")
        self.geometry("540x800")
        self.minsize(520, 720)
        self.configure(bg=BG_APP)

        self.cfg = config_store.carregar()      # config persistida
        self._log_queue = queue.Queue()
        self._conn = None                        # ADBConnector do device conectado
        self._conectado = False
        self._parar = threading.Event()          # sinaliza parar a varredura (Pokemon GO)
        self._parar_pg = threading.Event()       # sinaliza parar a varredura (PokeGenie)
        self._pogo_running = False               # varredura Pokemon GO em andamento
        self._pg_running = False                 # varredura PokeGenie em andamento
        self._ocupado = False                    # evita acoes concorrentes

        self._montar_widgets()
        self.var_limite.trace_add("write", lambda *_: self._atualizar_estimativa())
        self._atualizar_estimativa()
        self.after(100, self._drenar_log)
        self.after(300, self._auto_conectar)     # tenta conectar ao abrir

    # ----------------------------------------------------------- #
    # Layout
    # ----------------------------------------------------------- #
    def _card(self, titulo):
        """Cria um 'cartao' com titulo e retorna o frame de conteudo."""
        wrap = tk.Frame(self, bg=BG_APP)
        wrap.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(wrap, text=titulo, bg=BG_APP, fg=TXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=4)
        card = tk.Frame(wrap, bg=BG_CARD, highlightbackground=BORDA,
                        highlightthickness=1, bd=0)
        card.pack(fill="x", pady=(2, 0))
        return card

    def _montar_widgets(self):
        tk.Label(self, text="GoPokeScan", bg=BG_APP, fg=AZUL,
                 font=("Segoe UI", 16, "bold")).pack(pady=(10, 0))

        # --- STATUS & CONEXAO ---
        c1 = self._card("STATUS & CONEXAO")
        linha1 = tk.Frame(c1, bg=BG_CARD)
        linha1.pack(fill="x", padx=12, pady=(10, 12))
        self.var_status = tk.StringVar(value="●  Desconectado")
        self.lbl_status = tk.Label(linha1, textvariable=self.var_status, bg=BG_CARD,
                                   fg=VERMELHO, font=("Segoe UI", 14, "bold"))
        self.lbl_status.pack(side="left")
        tk.Button(linha1, text="Configuracoes ⚙", bg=CINZA, fg="white",
                  font=("Segoe UI", 10, "bold"), relief="flat",
                  activebackground="#6f7d88", command=self._abrir_config).pack(
            side="right", padx=(8, 0), ipadx=8, ipady=4)
        self.btn_testar = tk.Button(linha1, text="Testar Conexao", bg=AZUL, fg="white",
                                    font=("Segoe UI", 10, "bold"), relief="flat",
                                    activebackground="#2569b0", command=self._testar_conexao)
        self.btn_testar.pack(side="right", ipadx=8, ipady=4)

        # --- INFO DO DISPOSITIVO ---
        c2 = self._card("INFO DO DISPOSITIVO")
        self.var_dim = tk.StringVar(value="Dimensoes da Tela:  -- x --")
        tk.Label(c2, textvariable=self.var_dim, bg=BG_CARD, fg=TXT,
                 font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(10, 6))
        self.btn_calibrar = tk.Button(c2, text="◎  Calibrar Tela de Jogo",
                                      font=("Segoe UI", 10, "bold"), relief="flat",
                                      bg="#dfe9f0", fg=TXT, state="disabled",
                                      command=self._calibrar)
        self.btn_calibrar.pack(fill="x", padx=12, pady=(0, 4), ipady=5)

        # Calibrar Swipe Horizontal + campo de segundos
        linha_sw = tk.Frame(c2, bg=BG_CARD)
        linha_sw.pack(fill="x", padx=12, pady=(0, 12))
        self.btn_swipe = tk.Button(
            linha_sw, text="〰  Calibrar Swipe Horizontal", font=("Segoe UI", 10, "bold"),
            relief="flat", bg="#dfe9f0", fg=TXT, command=self._calibrar_swipe)
        self.btn_swipe.pack(side="left", fill="x", expand=True, ipady=5)
        tk.Label(linha_sw, text="seg:", bg=BG_CARD, fg=TXT).pack(side="left", padx=(8, 2))
        self.var_seg_swipe = tk.StringVar(value="15")
        tk.Spinbox(linha_sw, from_=3, to=120, width=4, textvariable=self.var_seg_swipe,
                   justify="center").pack(side="left")

        # --- COLETA DE DADOS (Pokemon GO + PokeGenie na mesma secao) ---
        c3 = self._card("COLETA DE DADOS")

        # Box 1: limite + botao Pokemon GO (verde<->vermelho, mesmo botao)
        linha3 = tk.Frame(c3, bg=BG_CARD)
        linha3.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(linha3, text="Limitar Colecao para:", bg=BG_CARD, fg=TXT,
                 font=("Segoe UI", 11)).pack(side="left")
        self.var_limite = tk.StringVar(value=str(self.cfg.get("limite_colecao", 50)))
        tk.Spinbox(linha3, from_=1, to=9999, width=6, textvariable=self.var_limite,
                   font=("Segoe UI", 11), justify="center").pack(side="left", padx=8)
        tk.Label(linha3, text="Pokemon", bg=BG_CARD, fg=TXT,
                 font=("Segoe UI", 11)).pack(side="left")
        tk.Button(linha3, text="⚙", bg=CINZA, fg="white",
                  font=("Segoe UI", 10, "bold"), relief="flat",
                  activebackground="#6f7d88", command=self._abrir_config_coleta).pack(
            side="right", padx=4, ipadx=6, ipady=2)
        self.var_estimativa = tk.StringVar(value="≈ --")
        tk.Label(linha3, textvariable=self.var_estimativa, bg=BG_CARD, fg=CINZA,
                 font=("Segoe UI", 10)).pack(side="right", padx=(0, 8))
        self.btn_varredura = tk.Button(
            c3, text="▶  POKEMON GO", bg=VERDE, fg="white",
            font=("Segoe UI", 12, "bold"), relief="flat", activebackground="#2f9e44",
            state="disabled", command=self._toggle_pogo)
        self.btn_varredura.pack(fill="x", padx=12, pady=(4, 10), ipady=8)

        # separador entre os dois boxes
        tk.Frame(c3, bg=BORDA, height=1).pack(fill="x", padx=12)

        # Box 2: filtros + botao PokeGenie (verde<->vermelho, mesmo botao)
        tk.Label(c3, text="Selecione os filtros:", bg=BG_CARD, fg=TXT,
                 font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(10, 2))
        linha_pg = tk.Frame(c3, bg=BG_CARD)
        linha_pg.pack(fill="x", padx=12, pady=(0, 6))
        # ordem/rotulo -> chave do modo em pokegenie.py
        self._pg_modos = {
            "IV (PvE)": "IV",
            "Grande Liga": "GL",
            "Ultra Liga": "UL",
            "Copinha": "LC",
        }
        self._pg_vars = {}
        for rotulo in self._pg_modos:
            v = tk.BooleanVar(value=True)
            self._pg_vars[rotulo] = v
            tk.Checkbutton(linha_pg, text=rotulo, variable=v, bg=BG_CARD, fg=TXT,
                           font=("Segoe UI", 10), activebackground=BG_CARD,
                           selectcolor="#dfe9f0", anchor="w").pack(side="left", padx=(0, 10))
        self.btn_pg = tk.Button(
            c3, text="▶  POKEGENIE", bg=VERDE, fg="white",
            font=("Segoe UI", 12, "bold"), relief="flat", activebackground="#2f9e44",
            state="disabled", command=self._toggle_pokegenie)
        self.btn_pg.pack(fill="x", padx=12, pady=(4, 12), ipady=8)

        # --- LOG ---
        c4 = self._card("LOG")
        self.txt_log = tk.Text(c4, height=10, wrap="word", state="disabled",
                               bg="#111", fg="#e0e0e0", insertbackground="#fff",
                               font=("Consolas", 9), bd=0)
        self.txt_log.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        sb = ttk.Scrollbar(c4, command=self.txt_log.yview)
        sb.pack(side="right", fill="y", pady=8)
        self.txt_log.config(yscrollcommand=sb.set)

    # ----------------------------------------------------------- #
    # Log thread-safe
    # ----------------------------------------------------------- #
    def log(self, msg):
        self._log_queue.put(str(msg))

    def _drenar_log(self):
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self.txt_log.config(state="normal")
                self.txt_log.insert("end", msg + "\n")
                self.txt_log.see("end")
                self.txt_log.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drenar_log)

    # ----------------------------------------------------------- #
    # Estado da conexao (UI)
    # ----------------------------------------------------------- #
    def _set_status(self, conectado, dims=None, modelo=None):
        self._conectado = conectado
        if conectado:
            self.var_status.set("●  Conectado")
            self.lbl_status.config(fg=VERDE)
            self.btn_calibrar.config(state="normal")
            self.btn_varredura.config(state="normal")
            self.btn_pg.config(state="normal")
            if dims:
                texto = f"Dimensoes da Tela:  {dims[0]} x {dims[1]}"
                if modelo:
                    texto += f" — {modelo}"
                self.var_dim.set(texto)
        else:
            self.var_status.set("●  Desconectado")
            self.lbl_status.config(fg=VERMELHO)
            self.btn_calibrar.config(state="disabled")
            self.btn_varredura.config(state="disabled")
            self.btn_pg.config(state="disabled")
            self.var_dim.set("Dimensoes da Tela:  -- x --")

    def _conector(self):
        return ADBConnector(self.cfg.get("adb_path", ""), log=self.log)

    # ----------------------------------------------------------- #
    # Estimativa de tempo da varredura (Coleta de Dados)
    # ----------------------------------------------------------- #
    def _estimar_varredura(self):
        """Estima a faixa (min, max) de tempo total da varredura com base na
        config de coleta (config_store) e no limite atual (self.var_limite).
        Retorna (t_min, t_max) em segundos (float) ou None se o limite nao
        for um inteiro positivo valido."""
        try:
            n = int(self.var_limite.get())
        except (ValueError, tk.TclError):
            return None
        if n <= 0:
            return None

        # Overhead por ciclo (adb screencap + deteccao): varia conforme o
        # dispositivo, entao usamos uma faixa em vez de um valor fixo.
        OVERHEAD_MIN = 2.0
        OVERHEAD_MAX = 3.5
        SWIPE_S = 0.35

        coleta = config_store.carregar().get("coleta", dict(config_store.PADRAO["coleta"]))

        def media_var(chave, padrao):
            """Retorna (media, variancia) assumindo distribuicao uniforme [a, b]."""
            par = coleta.get(chave, padrao)
            a, b = par[0], par[1]
            m = (a + b) / 2
            v = ((b - a) ** 2) / 12
            return m, v

        chaves = [
            ("pausa_menu", [0.5, 0.8]),
            ("pausa_avaliar", [0.2, 0.8]),
            ("pausa_avaliar_genie", [0.4, 0.8]),
            ("pausa_render", [0.5, 1.5]),
            ("pausa_pos_x", [0.3, 0.8]),
            ("pausa_entre", [0.2, 2.0]),
        ]
        M = SWIPE_S
        V = 0.0
        for chave, padrao in chaves:
            m, v = media_var(chave, padrao)
            M += m
            V += v

        # Espalhamento estatistico do total de n ciclos (desvio padrao * 2).
        sigma = (n * V) ** 0.5
        spread = 2 * sigma

        # Descanso (rest) esperado: quantidade de pausas de descanso ao
        # longo da varredura, com sua propria faixa min/max.
        desc_ciclos = coleta.get("descanso_ciclos", [5, 30])
        media_ciclos = (desc_ciclos[0] + desc_ciclos[1]) / 2
        rests_expected = 0.0
        if max(desc_ciclos) >= 1 and media_ciclos > 0:
            rests_expected = max(0, (n - 1) / media_ciclos)

        desc_seg = coleta.get("descanso_segundos", [2.0, 30.0])
        D_min = rests_expected * desc_seg[0]
        D_max = rests_expected * desc_seg[1]

        t_min = n * (M + OVERHEAD_MIN) - spread + D_min
        t_max = n * (M + OVERHEAD_MAX) + spread + D_max

        t_min = max(0.0, t_min)
        if t_min > t_max:
            t_min = t_max

        return t_min, t_max

    def _formatar_tempo(self, segundos):
        """Formata um valor em segundos para 'N min' ou 'Hh MMmin'."""
        minutos = segundos / 60
        if minutos < 60:
            return f"{round(minutos)} min"
        horas = int(minutos // 60)
        resto = round(minutos % 60)
        if resto == 60:
            horas += 1
            resto = 0
        return f"{horas}h {resto:02d}min"

    def _atualizar_estimativa(self):
        """Recalcula e exibe a estimativa (faixa) de tempo da varredura."""
        faixa = self._estimar_varredura()
        if faixa is None:
            self.var_estimativa.set("≈ --")
            return
        t_min, t_max = faixa
        if t_min < 60 and t_max < 60:
            self.var_estimativa.set("≈ <1 min")
            return

        txt_min = self._formatar_tempo(t_min)
        txt_max = self._formatar_tempo(t_max)

        if txt_min == txt_max:
            self.var_estimativa.set(f"≈ {txt_min}")
            return

        # Quando as duas pontas sao so minutos (sem hora), escreve a
        # unidade uma unica vez no final: "≈ 12 a 15 min".
        if "h" not in txt_min and "h" not in txt_max:
            n_min = txt_min.replace(" min", "")
            n_max = txt_max.replace(" min", "")
            self.var_estimativa.set(f"≈ {n_min} a {n_max} min")
        else:
            self.var_estimativa.set(f"≈ {txt_min} a {txt_max}")

    # ----------------------------------------------------------- #
    # Conexao
    # ----------------------------------------------------------- #
    def _auto_conectar(self):
        """Ao abrir: se ha dados salvos, tenta conectar em segundo plano."""
        if self.cfg.get("adb_path"):
            self.log("Tentando reconectar com a config salva...")
            threading.Thread(target=self._worker_conexao, daemon=True).start()
        else:
            self.log("Sem config salva. Abra 'Configuracoes' para conectar.")

    def _testar_conexao(self):
        """Botao 'Testar Conexao': usa os dados salvos na config."""
        if self._ocupado:
            return
        if not self.cfg.get("adb_path"):
            messagebox.showwarning("Config", "Abra 'Configuracoes' e informe o adb + IP.")
            return
        threading.Thread(target=self._worker_conexao, daemon=True).start()

    def _worker_conexao(self, pair=None):
        """
        Executa o fluxo de conexao. 'pair' opcional = (ip, porta_pair, codigo)
        vindo do dialogo de Configuracoes (pareamento efemero).
        """
        self._ocupado = True
        self.after(0, lambda: self.btn_testar.config(state="disabled"))
        conn = self._conector()

        ip = self.cfg.get("ip", "").strip()
        porta = self.cfg.get("porta", "").strip()

        def pedir_conexao():
            return (ip, porta) if ip and porta else None

        def pedir_pareamento():
            return pair

        try:
            ok, resumo = fluxo_conexao(
                conn, pedir_conexao=pedir_conexao, pedir_pareamento=pedir_pareamento)
        except Exception as e:
            ok, resumo = False, f"erro inesperado: {e}"

        def concluir():
            self._ocupado = False
            self.btn_testar.config(state="normal")
            if ok:
                self._conn = conn
                try:
                    modelo = conn.device_model()
                except Exception:
                    modelo = ""
                self._set_status(True, conn.wm_size, modelo)
                self.log(f"[OK] {resumo}")
            else:
                self._set_status(False)
                self.log(f"[FALHA] {resumo}")
        self.after(0, concluir)

    # ----------------------------------------------------------- #
    # Dialogo de Configuracoes (formulario de conexao)
    # ----------------------------------------------------------- #
    def _abrir_config(self):
        dlg = tk.Toplevel(self)
        dlg.title("Configuracoes - Conexao ADB Wi-Fi")
        dlg.geometry("560x420")
        dlg.configure(bg=BG_APP)
        dlg.transient(self)
        dlg.grab_set()

        v_adb = tk.StringVar(value=self.cfg.get("adb_path", "") or detectar_adb())
        v_ip = tk.StringVar(value=self.cfg.get("ip", ""))
        v_porta = tk.StringVar(value=self.cfg.get("porta", ""))
        v_ip_pair = tk.StringVar()
        v_porta_pair = tk.StringVar()
        v_codigo = tk.StringVar()

        # adb.exe
        f1 = ttk.LabelFrame(dlg, text="Caminho do adb.exe")
        f1.pack(fill="x", padx=10, pady=6)
        ttk.Entry(f1, textvariable=v_adb).pack(
            side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(f1, text="Procurar...",
                   command=lambda: self._procurar_adb(v_adb)).pack(side="left", padx=2)
        ttk.Button(f1, text="Testar adb",
                   command=lambda: self._testar_adb(v_adb.get())).pack(side="left", padx=6)

        # conexao
        f2 = ttk.LabelFrame(dlg, text="Conexao (tela principal da Depuracao sem fio)")
        f2.pack(fill="x", padx=10, pady=6)
        self._campo(f2, "IP do celular:", v_ip, "192.168.x.x", 0)
        self._campo(f2, "Porta de conexao:", v_porta, "ex.: 41069", 1)

        # pareamento
        f3 = ttk.LabelFrame(dlg, text="Pareamento - so na 1a vez / apos religar (EXPIRA!)")
        f3.pack(fill="x", padx=10, pady=6)
        self._campo(f3, "IP:", v_ip_pair, "geralmente o mesmo IP", 0)
        self._campo(f3, "Porta de pareamento:", v_porta_pair, "do popup", 1)
        self._campo(f3, "Codigo (6 digitos):", v_codigo, "do popup", 2)

        # botoes
        fb = tk.Frame(dlg, bg=BG_APP)
        fb.pack(fill="x", padx=10, pady=10)

        def salvar_e_conectar():
            # persiste o essencial (nunca o codigo de pareamento)
            self.cfg = config_store.salvar(
                adb_path=v_adb.get().strip(),
                ip=v_ip.get().strip(),
                porta=v_porta.get().strip(),
            )
            self.log("Config salva em config.json.")
            pair = None
            if v_ip_pair.get().strip() and v_porta_pair.get().strip() and v_codigo.get().strip():
                pair = (v_ip_pair.get().strip() or v_ip.get().strip(),
                        v_porta_pair.get().strip(), v_codigo.get().strip())
            dlg.destroy()
            if not self._ocupado:
                threading.Thread(target=self._worker_conexao,
                                 kwargs={"pair": pair}, daemon=True).start()

        ttk.Button(fb, text="Salvar e conectar", command=salvar_e_conectar).pack(
            side="right", padx=4)
        ttk.Button(fb, text="Cancelar", command=dlg.destroy).pack(side="right")

    def _campo(self, parent, rotulo, var, placeholder, linha):
        ttk.Label(parent, text=rotulo).grid(row=linha, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(parent, textvariable=var, width=38).grid(
            row=linha, column=1, sticky="w", padx=6, pady=3)
        if placeholder:
            ttk.Label(parent, text=placeholder, foreground="#888").grid(
                row=linha, column=2, sticky="w", padx=6)

    def _procurar_adb(self, var):
        cam = filedialog.askopenfilename(
            title="Selecione o adb.exe",
            filetypes=[("adb.exe", "adb.exe"), ("Executaveis", "*.exe"), ("Todos", "*.*")])
        if cam:
            var.set(cam)

    def _testar_adb(self, caminho):
        ok, info = ADBConnector(caminho.strip(), log=self.log).testar_adb()
        if ok:
            messagebox.showinfo("adb", f"adb OK:\n{info}")
        else:
            messagebox.showerror("adb", f"adb nao respondeu:\n{info}")

    # ----------------------------------------------------------- #
    # Dialogo de Configuracoes (pausas humanizadas da coleta)
    # ----------------------------------------------------------- #
    def _abrir_config_coleta(self):
        coleta = config_store.carregar().get("coleta", dict(config_store.PADRAO["coleta"]))
        dlg = tk.Toplevel(self)
        dlg.title("Configuracoes - Coleta Pokemon GO")
        dlg.geometry("560x620")
        dlg.configure(bg=BG_APP)
        dlg.transient(self)
        dlg.grab_set()

        # ---- Secao Pokemon GO ----
        f1 = ttk.LabelFrame(dlg, text="Pokemon GO")
        f1.pack(fill="x", padx=10, pady=6)
        v_menu_min, v_menu_max = self._campo_par(
            f1, "Pausa apos clicar no menu", coleta.get("pausa_menu", [0.5, 0.8]), 0)
        v_aval_min, v_aval_max = self._campo_par(
            f1, "Clique avaliacao", coleta.get("pausa_avaliar", [0.2, 0.8]), 1)
        v_avgn_min, v_avgn_max = self._campo_par(
            f1, "Pausa entre avaliar > genie",
            coleta.get("pausa_avaliar_genie", [0.4, 0.8]), 2)

        # ---- Secao Interface Genie ----
        f2 = ttk.LabelFrame(dlg, text="Interface Genie")
        f2.pack(fill="x", padx=10, pady=6)
        v_rend_min, v_rend_max = self._campo_par(
            f2, "Espera da pagina de resultado", coleta.get("pausa_render", [0.5, 1.5]), 0)
        v_posx_min, v_posx_max = self._campo_par(
            f2, "Pausa apos fechar no X", coleta.get("pausa_pos_x", [0.3, 0.8]), 1)

        # ---- Secao Sessao / Volume ----
        f3 = ttk.LabelFrame(dlg, text="Sessao / Volume")
        f3.pack(fill="x", padx=10, pady=6)
        v_entre_min, v_entre_max = self._campo_par(
            f3, "Pausa entre ciclos", coleta.get("pausa_entre", [0.2, 2.0]), 0)

        desc_ciclos = coleta.get("descanso_ciclos", [5, 30])
        linha_desc1 = tk.Frame(f3, bg=BG_APP)
        linha_desc1.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(linha_desc1, text="Pausa de descanso: a cada").pack(side="left")
        v_desc_ciclos_min = tk.StringVar(value=str(desc_ciclos[0]))
        ttk.Entry(linha_desc1, textvariable=v_desc_ciclos_min, width=5).pack(side="left", padx=4)
        ttk.Label(linha_desc1, text="a").pack(side="left")
        v_desc_ciclos_max = tk.StringVar(value=str(desc_ciclos[1]))
        ttk.Entry(linha_desc1, textvariable=v_desc_ciclos_max, width=5).pack(side="left", padx=4)
        ttk.Label(linha_desc1, text="ciclos").pack(side="left")
        ttk.Label(linha_desc1, text="(0 ciclos = desativado)",
                  foreground="#888").pack(side="left", padx=(6, 0))

        linha_desc2 = tk.Frame(f3, bg=BG_APP)
        linha_desc2.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(linha_desc2, text="descansar entre").pack(side="left")
        desc_seg = coleta.get("descanso_segundos", [2.0, 30.0])
        v_desc_min = tk.StringVar(value=str(desc_seg[0]))
        ttk.Entry(linha_desc2, textvariable=v_desc_min, width=6).pack(side="left", padx=4)
        ttk.Label(linha_desc2, text="e").pack(side="left")
        v_desc_max = tk.StringVar(value=str(desc_seg[1]))
        ttk.Entry(linha_desc2, textvariable=v_desc_max, width=6).pack(side="left", padx=4)
        ttk.Label(linha_desc2, text="segundos").pack(side="left")

        # ---- Botoes ----
        fb = tk.Frame(dlg, bg=BG_APP)
        fb.pack(fill="x", padx=10, pady=10)

        def ler_par(v_min, v_max, nome):
            try:
                a = float(v_min.get())
                b = float(v_max.get())
            except ValueError:
                raise ValueError(f"'{nome}' precisa ser numerico.")
            if a > b:
                raise ValueError(f"'{nome}': o minimo nao pode ser maior que o maximo.")
            return [a, b]

        def ler_par_ciclos(v_min, v_max, nome):
            try:
                a = int(v_min.get())
                b = int(v_max.get())
            except ValueError:
                raise ValueError(f"'{nome}' precisa ser inteiro.")
            if a < 0 or b < 0:
                raise ValueError(f"'{nome}' nao pode ser negativo.")
            if a > b:
                raise ValueError(f"'{nome}': o minimo nao pode ser maior que o maximo.")
            return [a, b]

        def salvar():
            try:
                pausa_menu = ler_par(v_menu_min, v_menu_max, "Pausa apos clicar no menu")
                pausa_avaliar = ler_par(v_aval_min, v_aval_max, "Clique avaliacao")
                pausa_avaliar_genie = ler_par(
                    v_avgn_min, v_avgn_max, "Pausa entre avaliar > genie")
                pausa_render = ler_par(
                    v_rend_min, v_rend_max, "Espera da pagina de resultado")
                pausa_pos_x = ler_par(v_posx_min, v_posx_max, "Pausa apos fechar no X")
                pausa_entre = ler_par(v_entre_min, v_entre_max, "Pausa entre ciclos")
                desc_ciclos = ler_par_ciclos(
                    v_desc_ciclos_min, v_desc_ciclos_max, "Pausa de descanso (ciclos)")
                descanso_segundos = ler_par(v_desc_min, v_desc_max, "Pausa de descanso (segundos)")
            except ValueError as e:
                messagebox.showwarning("Configuracoes de Coleta", str(e))
                return
            nova_coleta = {
                "pausa_menu": pausa_menu,
                "pausa_avaliar": pausa_avaliar,
                "pausa_avaliar_genie": pausa_avaliar_genie,
                "pausa_render": pausa_render,
                "pausa_pos_x": pausa_pos_x,
                "pausa_entre": pausa_entre,
                "descanso_ciclos": desc_ciclos,
                "descanso_segundos": descanso_segundos,
            }
            self.cfg = config_store.salvar(coleta=nova_coleta)
            self.log("Configuracoes de coleta salvas em config.json.")
            self._atualizar_estimativa()
            dlg.destroy()

        def restaurar_padroes():
            padrao = dict(config_store.PADRAO["coleta"])
            v_menu_min.set(str(padrao["pausa_menu"][0])); v_menu_max.set(str(padrao["pausa_menu"][1]))
            v_aval_min.set(str(padrao["pausa_avaliar"][0])); v_aval_max.set(str(padrao["pausa_avaliar"][1]))
            v_avgn_min.set(str(padrao["pausa_avaliar_genie"][0])); v_avgn_max.set(str(padrao["pausa_avaliar_genie"][1]))
            v_rend_min.set(str(padrao["pausa_render"][0])); v_rend_max.set(str(padrao["pausa_render"][1]))
            v_posx_min.set(str(padrao["pausa_pos_x"][0])); v_posx_max.set(str(padrao["pausa_pos_x"][1]))
            v_entre_min.set(str(padrao["pausa_entre"][0])); v_entre_max.set(str(padrao["pausa_entre"][1]))
            v_desc_ciclos_min.set(str(padrao["descanso_ciclos"][0]))
            v_desc_ciclos_max.set(str(padrao["descanso_ciclos"][1]))
            v_desc_min.set(str(padrao["descanso_segundos"][0]))
            v_desc_max.set(str(padrao["descanso_segundos"][1]))
            self.cfg = config_store.salvar(coleta=padrao)
            self.log("Configuracoes de coleta restauradas para o padrao.")
            self._atualizar_estimativa()

        ttk.Button(fb, text="Salvar", command=salvar).pack(side="right", padx=4)
        ttk.Button(fb, text="Restaurar padroes", command=restaurar_padroes).pack(
            side="right", padx=4)
        ttk.Button(fb, text="Fechar", command=dlg.destroy).pack(side="right")

    def _campo_par(self, parent, rotulo, valores, linha):
        """Cria uma linha com rotulo + dois campos (min, max). Retorna (v_min, v_max)."""
        f = tk.Frame(parent, bg=BG_APP)
        f.pack(fill="x", padx=6, pady=3)
        ttk.Label(f, text=rotulo, width=32, anchor="w").pack(side="left")
        v_min = tk.StringVar(value=str(valores[0]))
        ttk.Entry(f, textvariable=v_min, width=7).pack(side="left", padx=(4, 2))
        ttk.Label(f, text="a").pack(side="left")
        v_max = tk.StringVar(value=str(valores[1]))
        ttk.Entry(f, textvariable=v_max, width=7).pack(side="left", padx=(2, 0))
        ttk.Label(f, text="s").pack(side="left", padx=(2, 0))
        return v_min, v_max

    # ----------------------------------------------------------- #
    # Calibracao e Varredura
    # ----------------------------------------------------------- #
    def _calibrar(self):
        if not self._conectado or not self._conn:
            return
        threading.Thread(
            target=lambda: calibracao.iniciar(self._conn, self.log), daemon=True).start()

    def _calibrar_swipe(self):
        """Abre a calibracao de swipe (processo proprio, com janelinha + contagem)."""
        try:
            seg = int(self.var_seg_swipe.get())
        except ValueError:
            messagebox.showwarning("Swipe", "Informe os segundos (numero).")
            return
        script = Path(__file__).resolve().parent / "calibrar_swipe.py"
        try:
            subprocess.Popen([sys.executable, str(script), str(seg)],
                             cwd=str(script.parent))
            self.log(f"Calibracao de swipe iniciada ({seg}s). Siga a janelinha.")
        except Exception as e:
            messagebox.showerror("Swipe", f"Falha ao iniciar: {e}")

    def _btn_estado(self, btn, rodando, nome):
        """Alterna o mesmo botao entre INICIAR (verde) e ABORTAR (vermelho)."""
        if rodando:
            btn.config(text=f"■  ABORTAR {nome}", bg=VERMELHO,
                       activebackground="#c92a2a")
        else:
            btn.config(text=f"▶  {nome}", bg=VERDE, activebackground="#2f9e44")

    # ----------------------------------------------------------- #
    # Varredura Pokemon GO (mesmo botao: iniciar <-> abortar)
    # ----------------------------------------------------------- #
    def _toggle_pogo(self):
        if self._pogo_running:
            self._abortar_varredura()
        else:
            self._iniciar_varredura()

    def _iniciar_varredura(self):
        if not self._conectado or not self._conn:
            return
        try:
            n = int(self.var_limite.get())
        except ValueError:
            messagebox.showwarning("Varredura", "Informe um numero valido.")
            return
        # persiste o limite escolhido
        self.cfg = config_store.salvar(limite_colecao=n)
        self._parar.clear()
        self._pogo_running = True
        self._btn_estado(self.btn_varredura, True, "POKEMON GO")

        def run():
            try:
                varredura.executar(self._conn, n, log=self.log, parar=self._parar)
            finally:
                def restaurar():
                    self._pogo_running = False
                    self._btn_estado(self.btn_varredura, False, "POKEMON GO")
                    self.btn_varredura.config(
                        state="normal" if self._conectado else "disabled")
                self.after(0, restaurar)
        threading.Thread(target=run, daemon=True).start()

    def _abortar_varredura(self):
        """Sinaliza a varredura para parar no proximo ciclo."""
        self._parar.set()
        self.btn_varredura.config(state="disabled")  # ate encerrar de fato
        self.log("Abortando Pokemon GO... (para no proximo ciclo)")

    # ----------------------------------------------------------- #
    # Varredura PokeGenie (uiautomator) - mesmo botao: iniciar <-> abortar
    # ----------------------------------------------------------- #
    def _toggle_pokegenie(self):
        if self._pg_running:
            self._abortar_pokegenie()
        else:
            self._iniciar_pokegenie()

    def _iniciar_pokegenie(self):
        if not self._conectado or not self._conn:
            return
        modos = [chave for rotulo, chave in self._pg_modos.items()
                 if self._pg_vars[rotulo].get()]
        if not modos:
            messagebox.showwarning(
                "PokeGenie", "Marque pelo menos um filtro para raspar.")
            return
        self._parar_pg.clear()
        self._pg_running = True
        self._btn_estado(self.btn_pg, True, "POKEGENIE")

        def run():
            try:
                pokegenie.executar(self._conn, modos, log=self.log,
                                   parar=self._parar_pg)
            except Exception as e:
                self.log(f"[ERRO] PokeGenie: {e}")
            finally:
                def restaurar():
                    self._pg_running = False
                    self._btn_estado(self.btn_pg, False, "POKEGENIE")
                    self.btn_pg.config(
                        state="normal" if self._conectado else "disabled")
                self.after(0, restaurar)
        threading.Thread(target=run, daemon=True).start()

    def _abortar_pokegenie(self):
        """Sinaliza a varredura do PokeGenie para parar no proximo passo."""
        self._parar_pg.set()
        self.btn_pg.config(state="disabled")  # ate encerrar de fato
        self.log("Abortando PokeGenie... (para no proximo passo)")


if __name__ == "__main__":
    GoPokeScanGUI().mainloop()
