# -*- coding: utf-8 -*-
"""
Camada de conexao ADB Wi-Fi com um Android fisico (Windows).

Este modulo e o alicerce do projeto PokeScan: garante uma conexao ADB estavel
sobre Wi-Fi (porta fixa 5555 + perfis por rede em redes.json). A automacao em si
sera construida depois, em cima desta conexao.

Conceitos importantes (respeitados pelo codigo):
  1. A Depuracao sem fio tem uma porta de PAREAMENTO (+codigo, ambos efemeros) e
     uma porta de CONEXAO (separada). Nao confundir as duas.
  2. O pareamento persiste a quedas de rede; so a porta de conexao muda. So e
     preciso reparear se o celular reiniciar ou a depuracao for religada.
  3. `adb tcpip 5555` (rodado sobre uma conexao JA ativa) faz o adbd escutar numa
     porta estavel (5555). Isso RESETA ao reiniciar o aparelho. Sem pareamento na
     5555, use apenas em rede de confianca.
  4. O IP muda por rede (DHCP). Detectamos o SSID atual e guardamos
     SSID -> {ip, porta} em redes.json, para reconhecer cada local automaticamente.
"""

import json
import os
import re
import subprocess
from pathlib import Path

# ------------------------------------------------------------------ #
# Caminhos e defaults (edite pela GUI; aqui ficam apenas os fallbacks)
# ------------------------------------------------------------------ #
DIR_BASE = Path(__file__).resolve().parent
REDES_JSON = DIR_BASE / "redes.json"      # perfis SSID -> {ip, porta}
PORTA_FIXA = 5555                          # porta estavel via 'adb tcpip'


class ADBConnector:
    """Encapsula todas as operacoes de conexao ADB Wi-Fi."""

    def __init__(self, adb_path: str, log=None):
        # Caminho do adb.exe (informado pelo usuario na GUI)
        self.adb_path = adb_path
        # Callback de log; se nao vier, imprime no console
        self._log = log or (lambda msg: print(msg))
        # Guarda a resolucao da tela apos o smoke test (normaliza toques depois)
        self.wm_size = None

    # ----------------------------------------------------------- #
    # Utilitarios base
    # ----------------------------------------------------------- #
    def log(self, msg: str):
        """Envia uma mensagem para o log (GUI ou console)."""
        self._log(str(msg))

    def adb(self, *args, timeout: int = 30):
        """
        Roda o adb via subprocess.
        Retorna (stdout, stderr, returncode) com strings ja decodificadas.
        """
        if not self.adb_path or not Path(self.adb_path).exists():
            return ("", f"adb.exe nao encontrado em: {self.adb_path}", 1)
        cmd = [self.adb_path, *[str(a) for a in args]]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                # CREATE_NO_WINDOW evita piscar janela de console no Windows
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return (proc.stdout.strip(), proc.stderr.strip(), proc.returncode)
        except subprocess.TimeoutExpired:
            return ("", f"timeout ao rodar: {' '.join(cmd)}", 1)
        except Exception as e:
            return ("", f"erro ao rodar adb: {e}", 1)

    def testar_adb(self):
        """Confere se o adb.exe responde. Retorna a versao ou uma mensagem de erro."""
        out, err, rc = self.adb("version")
        if rc == 0 and out:
            # inicia o servidor logo de cara para as chamadas seguintes
            self.adb("start-server")
            return True, out.splitlines()[0]
        return False, err or "adb nao respondeu"

    # ----------------------------------------------------------- #
    # SSID / perfis de rede
    # ----------------------------------------------------------- #
    def ssid_atual(self):
        """
        Retorna o SSID do Wi-Fi atual via 'netsh wlan show interfaces'.
        Retorna None se nao conseguir detectar (ex.: sem Wi-Fi).
        """
        try:
            proc = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            return None
        # A saida pode vir localizada (pt-BR "SSID" tambem). Pegamos a linha
        # cujo rotulo e exatamente "SSID" (ignorando "BSSID").
        for linha in proc.stdout.splitlines():
            m = re.match(r"\s*SSID\s*:\s*(.+?)\s*$", linha)
            if m and "BSSID" not in linha:
                return m.group(1).strip()
        return None

    def _carregar_redes(self) -> dict:
        """Le o redes.json (ou retorna {} se nao existir/estiver corrompido)."""
        if REDES_JSON.exists():
            try:
                return json.loads(REDES_JSON.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _gravar_redes(self, dados: dict):
        """Grava o dicionario de perfis no redes.json (formatado)."""
        REDES_JSON.write_text(
            json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def config_rede(self):
        """
        Resolve (ip, porta) pela rede atual usando o redes.json.
        Retorna (ssid, ip, porta) — ip/porta podem ser None se a rede for nova.
        """
        ssid = self.ssid_atual()
        redes = self._carregar_redes()
        if ssid and ssid in redes:
            perfil = redes[ssid]
            return ssid, perfil.get("ip"), perfil.get("porta")
        return ssid, None, None

    def salvar_rede(self, ip: str, porta: int):
        """Grava o perfil {ip, porta} para o SSID atual no redes.json."""
        ssid = self.ssid_atual()
        if not ssid:
            self.log("Nao foi possivel detectar o SSID; perfil nao salvo.")
            return None
        redes = self._carregar_redes()
        redes[ssid] = {"ip": ip, "porta": int(porta)}
        self._gravar_redes(redes)
        self.log(f"redes.json atualizado: {ssid} -> {ip}:{porta}")
        return ssid

    # ----------------------------------------------------------- #
    # Conexao / pareamento
    # ----------------------------------------------------------- #
    def _serial_conectado(self):
        """
        Retorna o serial (ex.: '192.168.0.5:5555') do primeiro device Wi-Fi
        com status 'device'. None se nao houver.
        """
        out, _, _ = self.adb("devices")
        for linha in out.splitlines()[1:]:  # pula o cabecalho "List of devices"
            partes = linha.split()
            if len(partes) >= 2 and partes[1] == "device" and ":" in partes[0]:
                return partes[0]
        return None

    def serial(self):
        """Acesso publico ao serial do device conectado (ou None)."""
        return self._serial_conectado()

    def screencap(self, destino, timeout: int = 30):
        """
        Captura a tela do device e grava o PNG em 'destino' (bytes binarios).
        Usa 'exec-out screencap -p' (nao passa pelo shell de texto, evita
        corromper o PNG). Retorna (ok, mensagem).
        """
        serial = self._serial_conectado()
        if not serial:
            return False, "nenhum device conectado"
        if not self.adb_path or not Path(self.adb_path).exists():
            return False, f"adb.exe nao encontrado: {self.adb_path}"
        cmd = [self.adb_path, "-s", serial, "exec-out", "screencap", "-p"]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=timeout,  # sem text=True: binario
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            return False, f"erro no screencap: {e}"
        if proc.returncode != 0 or not proc.stdout:
            return False, proc.stderr.decode(errors="ignore") or "screencap vazio"
        Path(destino).write_bytes(proc.stdout)
        return True, str(destino)

    def screencap_bytes(self, timeout: int = 30):
        """Captura a tela e retorna os bytes do PNG (sem gravar arquivo).
        Usado para prints 'so na memoria' (decisao/cliques). None se falhar."""
        serial = self._serial_conectado()
        if not serial or not self.adb_path or not Path(self.adb_path).exists():
            return None
        cmd = [self.adb_path, "-s", serial, "exec-out", "screencap", "-p"]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            return None
        if proc.returncode != 0 or not proc.stdout:
            return None
        return proc.stdout

    def swipe(self, x1, y1, x2, y2, dur_ms):
        """
        Executa um swipe (deslize) de (x1,y1) ate (x2,y2) na duracao dur_ms.
        Wrapper de 'input swipe' — a humanizacao (jitter/tempos) fica em quem chama.
        """
        serial = self._serial_conectado()
        if not serial:
            return False, "nenhum device conectado"
        out, err, rc = self.adb(
            "-s", serial, "shell", "input", "swipe",
            int(x1), int(y1), int(x2), int(y2), int(dur_ms), timeout=15)
        return rc == 0, (out + " " + err).strip()

    def tap(self, x, y):
        """Toque simples em (x,y) via 'input tap'. A humanizacao (jitter do
        ponto) fica em quem chama (ver detectar_icone.ponto_clique)."""
        serial = self._serial_conectado()
        if not serial:
            return False, "nenhum device conectado"
        out, err, rc = self.adb(
            "-s", serial, "shell", "input", "tap", int(x), int(y), timeout=15)
        return rc == 0, (out + " " + err).strip()

    def parear(self, ip: str, porta_pair: str, codigo: str):
        """
        Realiza o pareamento (1a vez numa rede ou apos religar a depuracao).
        IP:porta_pair e o codigo de 6 digitos vem do popup 'Parear com codigo'
        e EXPIRAM rapido — por isso sao pedidos em runtime.
        """
        self.log(f"Pareando com {ip}:{porta_pair} ...")
        out, err, rc = self.adb("pair", f"{ip}:{porta_pair}", str(codigo), timeout=25)
        msg = (out + " " + err).strip()
        self.log(msg or "(sem saida)")
        # Sucesso quando o adb responde "Successfully paired"
        return rc == 0 and "success" in msg.lower()

    def conectar(self, ip: str, porta):
        """
        Roda 'adb connect ip:porta'. Retorna (ok, mensagem).
        Trata as respostas do adb (connected / already connected / recusada).
        """
        alvo = f"{ip}:{porta}"
        self.log(f"Conectando em {alvo} ...")
        out, err, rc = self.adb("connect", alvo, timeout=20)
        msg = (out + " " + err).strip()
        self.log(msg or "(sem saida)")
        ok = ("connected to" in msg.lower()) or ("already connected" in msg.lower())
        # 'connected to X:Y' as vezes aparece mesmo com falha posterior; o
        # verificar_conexao() abaixo confirma o estado real.
        return ok, msg

    def fixar_porta(self, porta: int = PORTA_FIXA):
        """
        Deriva o IP do device JA conectado (nao de um default), roda
        'adb -s <serial> tcpip <porta>' e reconecta em <ip>:<porta>.
        Retorna (ok, ip) — ip do device fixado, para salvar no perfil.
        """
        serial = self._serial_conectado()
        if not serial:
            self.log("Nenhum device conectado para fixar a porta.")
            return False, None
        ip = serial.split(":")[0]
        self.log(f"Fixando porta {porta} no device {serial} ...")
        # Coloca o adbd escutando na porta fixa
        out, err, rc = self.adb("-s", serial, "tcpip", str(porta), timeout=15)
        self.log((out + " " + err).strip() or "(sem saida)")
        # Da um tempo para o adbd reiniciar e reconecta na porta fixa
        import time
        time.sleep(2)
        ok, _ = self.conectar(ip, porta)
        return ok, ip

    def device_model(self):
        """
        Retorna o fabricante + modelo do device (ex.: 'Samsung SM-G991B').
        Usa 'adb shell getprop ro.product.manufacturer/model'. String vazia
        se falhar (sem device conectado, propriedade vazia, etc.).
        """
        serial = self._serial_conectado()
        if not serial:
            return ""
        out_fab, _, rc_fab = self.adb(
            "-s", serial, "shell", "getprop", "ro.product.manufacturer", timeout=15)
        out_mod, _, rc_mod = self.adb(
            "-s", serial, "shell", "getprop", "ro.product.model", timeout=15)
        if rc_fab != 0 and rc_mod != 0:
            return ""
        fabricante = out_fab.strip().title()
        modelo = out_mod.strip()
        partes = [p for p in (fabricante, modelo) if p]
        return " ".join(partes)

    def verificar_conexao(self):
        """
        Confirma o estado real: 'adb devices' (status 'device') + smoke test
        'adb shell wm size' (guarda a resolucao). Retorna (ok, resumo).
        """
        serial = self._serial_conectado()
        if not serial:
            return False, "Nenhum device com status 'device' em 'adb devices'."
        # Smoke test: pega a resolucao da tela
        out, err, rc = self.adb("-s", serial, "shell", "wm", "size", timeout=15)
        if rc == 0 and "size" in out.lower():
            # Ex.: "Physical size: 1080x2400"
            m = re.search(r"(\d+)x(\d+)", out)
            if m:
                self.wm_size = (int(m.group(1)), int(m.group(2)))
            self.log(f"Smoke test OK: {out}")
            return True, f"{serial} | {out}"
        return False, err or "wm size falhou"


# ------------------------------------------------------------------ #
# Orquestracao: segue o algoritmo do briefing, passo a passo.
# ------------------------------------------------------------------ #
def fluxo_conexao(conn: ADBConnector, ip_manual=None, porta_manual=None,
                  pedir_conexao=None, pedir_pareamento=None):
    """
    Executa o algoritmo de conexao completo.

    Callbacks (usados pela GUI para pedir dados efemeros em runtime):
      - pedir_conexao()  -> deve retornar (ip, porta_connect) ou None
      - pedir_pareamento() -> deve retornar (ip, porta_pair, codigo) ou None

    Se ip_manual/porta_manual forem passados, sao usados direto no passo 3.
    Retorna (ok: bool, resumo: str).
    """
    # 0) adb responde?
    ok_adb, versao = conn.testar_adb()
    if not ok_adb:
        return False, f"adb indisponivel: {versao}"
    conn.log(f"adb OK: {versao}")

    # 1) Detecta o SSID e tenta carregar (ip, porta) do redes.json
    ssid, ip_conhecido, porta_conhecida = conn.config_rede()
    conn.log(f"SSID atual: {ssid or '(desconhecido)'}")

    # 2) Caminho rapido: tenta a 5555 conhecida
    if ip_conhecido:
        conn.log(f"Tentando caminho rapido em {ip_conhecido}:{porta_conhecida or PORTA_FIXA} ...")
        conn.conectar(ip_conhecido, porta_conhecida or PORTA_FIXA)
        ok, resumo = conn.verificar_conexao()
        if ok:
            conn.log("Conexao rapida bem-sucedida.")
            return True, resumo
        conn.log("Caminho rapido falhou (5555 caiu ou IP mudou). Seguindo...")

    # 3) Pede IP:porta_connect atual e tenta conectar (pareamento pode estar intacto)
    if ip_manual and porta_manual:
        ip, porta_connect = ip_manual, porta_manual
    elif pedir_conexao:
        dados = pedir_conexao()
        if not dados:
            return False, "Conexao cancelada pelo usuario (sem IP:porta)."
        ip, porta_connect = dados
    else:
        return False, "Faltam IP e porta de conexao."

    conn.conectar(ip, porta_connect)
    ok, resumo = conn.verificar_conexao()

    # 4) Se falhou, provavelmente precisa parear
    if not ok and pedir_pareamento:
        conn.log("Conexao direta falhou; parece precisar de pareamento.")
        dados = pedir_pareamento()
        if not dados:
            return False, "Pareamento cancelado pelo usuario."
        ip_p, porta_pair, codigo = dados
        if not conn.parear(ip_p, porta_pair, codigo):
            return False, "Falha no pareamento (codigo pode ter expirado)."
        conn.conectar(ip, porta_connect)
        ok, resumo = conn.verificar_conexao()

    if not ok:
        return False, f"Nao foi possivel conectar. Ultimo estado: {resumo}"

    # 5) Fixa a porta 5555 e salva o perfil da rede
    ok_fix, ip_fix = conn.fixar_porta(PORTA_FIXA)
    if ok_fix and ip_fix:
        conn.salvar_rede(ip_fix, PORTA_FIXA)

    # 6) Confirma o estado final
    ok, resumo = conn.verificar_conexao()
    return ok, resumo
