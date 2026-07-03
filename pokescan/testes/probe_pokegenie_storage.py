#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_pokegenie_storage.py

Script de investigacao (somente leitura) para descobrir se o Poke Genie
guarda dados de scan localmente no telefone e se algo disso e acessivel
sem root, via ADB (Wi-Fi), a partir do Windows.

Uso:
    python probe_pokegenie_storage.py

Pressupostos:
    - O dispositivo Android ja foi conectado via "adb connect" (feito pela
      GUI do projeto PokeScan).
    - O caminho do adb.exe fica em app/config.json, chave "adb_path".
    - Nao requer nenhuma dependencia externa (apenas biblioteca padrao).
"""

import json
import subprocess
import sys
from pathlib import Path

TIMEOUT_PADRAO = 30  # segundos por comando


def carregar_adb_path():
    """Le o caminho do adb a partir de app/config.json (relativo a este
    script). Se nao encontrar, usa 'adb' assumindo que esta no PATH."""
    script_dir = Path(__file__).resolve().parent
    config_path = script_dir.parent / "app" / "config.json"

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            adb_path = config.get("adb_path")
            if adb_path:
                print(f"[config] adb_path lido de {config_path}: {adb_path}")
                return adb_path
            else:
                print(f"[config] Chave 'adb_path' nao encontrada em {config_path}. "
                      f"Usando 'adb' do PATH.")
        except Exception as e:
            print(f"[config] Falha ao ler {config_path}: {e}. Usando 'adb' do PATH.")
    else:
        print(f"[config] Arquivo de config nao encontrado em {config_path}. "
              f"Usando 'adb' do PATH.")

    return "adb"


def rodar_comando(args, timeout=TIMEOUT_PADRAO):
    """Executa um comando via subprocess.run, capturando stdout/stderr como
    texto. Nunca levanta excecao para fora: qualquer erro e reportado como
    string no retorno. Retorna (stdout, stderr, codigo_retorno)."""
    cmd_str = " ".join(f'"{a}"' if " " in a else a for a in args)
    print(f"\n$ {cmd_str}")
    try:
        resultado = subprocess.run(
            args,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        stdout = resultado.stdout or ""
        stderr = resultado.stderr or ""
        if stdout.strip():
            print(stdout.rstrip())
        if stderr.strip():
            print(f"[stderr] {stderr.rstrip()}")
        return stdout, stderr, resultado.returncode
    except subprocess.TimeoutExpired:
        msg = f"[ERRO] Comando expirou apos {timeout}s (timeout)."
        print(msg)
        return "", msg, -1
    except Exception as e:
        msg = f"[ERRO] Falha ao executar comando: {e}"
        print(msg)
        return "", msg, -1


def secao(titulo):
    """Imprime um cabecalho de secao bem visivel."""
    linha = "=" * 70
    print(f"\n{linha}\n{titulo}\n{linha}")


def verificar_dispositivo(adb_path):
    """Roda 'adb devices' e verifica se ha pelo menos um dispositivo
    conectado e em estado 'device' (autorizado)."""
    secao("1. VERIFICANDO DISPOSITIVO CONECTADO (adb devices)")
    stdout, stderr, code = rodar_comando([adb_path, "devices"])

    linhas = [l.strip() for l in stdout.splitlines() if l.strip()]
    # A primeira linha normalmente e "List of devices attached"
    dispositivos = []
    for l in linhas[1:]:
        partes = l.split()
        if len(partes) >= 2:
            dispositivos.append((partes[0], partes[1]))

    dispositivos_ok = [d for d in dispositivos if d[1] == "device"]

    if not dispositivos_ok:
        print("\n[ABORTANDO] Nenhum dispositivo Android conectado e autorizado "
              "foi encontrado.")
        print("Verifique se o 'adb connect <ip>:<porta>' foi feito pela GUI do "
              "PokeScan e se o telefone autorizou a depuracao USB/Wi-Fi.")
        if dispositivos:
            print("Dispositivos listados, mas em estado diferente de 'device':")
            for serial, estado in dispositivos:
                print(f"  - {serial}: {estado}")
        sys.exit(1)

    print(f"\n[OK] {len(dispositivos_ok)} dispositivo(s) conectado(s):")
    for serial, estado in dispositivos_ok:
        print(f"  - {serial}: {estado}")


def encontrar_pacotes_pokegenie(adb_path):
    """Lista pacotes instalados e filtra por 'genie' ou 'poke' (case
    insensitive). Retorna lista de package ids encontrados."""
    secao("2. PROCURANDO O PACOTE DO POKE GENIE (adb shell pm list packages)")
    stdout, stderr, code = rodar_comando([adb_path, "shell", "pm", "list", "packages"])

    pacotes = []
    for linha in stdout.splitlines():
        linha = linha.strip()
        if not linha.startswith("package:"):
            continue
        pkg = linha[len("package:"):].strip()
        pkg_lower = pkg.lower()
        if "genie" in pkg_lower or "poke" in pkg_lower:
            pacotes.append(pkg)

    print("\nPacotes candidatos encontrados (contem 'genie' ou 'poke'):")
    if pacotes:
        for p in pacotes:
            print(f"  - {p}")
    else:
        print("  Nenhum pacote encontrado com 'genie' ou 'poke' no nome.")
        print("  Pacote esperado (conhecido): nrs.pokegenie")

    return pacotes


def investigar_pacote(adb_path, pkg):
    """Roda a bateria de comandos de investigacao para um pacote especifico."""
    secao(f"3. INVESTIGANDO PACOTE: {pkg}")

    # --- dumpsys package, filtrando linhas relevantes ---
    print(f"\n--- dumpsys package {pkg} (filtrado) ---")
    stdout, stderr, code = rodar_comando(
        [adb_path, "shell", "dumpsys", "package", pkg]
    )
    filtros = [
        "versionName", "dataDir", "codePath", "flags",
        "ALLOW_BACKUP", "debuggable",
    ]
    linhas_relevantes = []
    for linha in stdout.splitlines():
        if any(f.lower() in linha.lower() for f in filtros):
            linhas_relevantes.append(linha.strip())

    print("\nLinhas relevantes (versionName, dataDir, codePath, flags, "
          "ALLOW_BACKUP, debuggable):")
    if linhas_relevantes:
        for l in linhas_relevantes:
            print(f"  {l}")
    else:
        print("  Nenhuma linha relevante encontrada no dumpsys (pacote pode "
              "nao existir ou dumpsys retornou vazio).")

    allow_backup = any("ALLOW_BACKUP" in l for l in linhas_relevantes)
    debuggable = any("debuggable" in l.lower() and "true" in l.lower()
                      for l in linhas_relevantes)

    # --- /data/data/<pkg> (deve dar Permission denied sem root) ---
    secao(f"3a. /data/data/{pkg} (esperado: Permission denied sem root)")
    rodar_comando([adb_path, "shell", "ls", "-la", f"/data/data/{pkg}"])
    print("\n[Explicacao] Sem root, o Android bloqueia o acesso direto a pasta "
          "interna do app (/data/data/<pkg>). E normal ver 'Permission denied'.")

    # --- run-as <pkg> (so funciona se debuggable=true) ---
    secao(f"3b. run-as {pkg} ls -la (so funciona se o app for 'debuggable')")
    rodar_comando([adb_path, "shell", "run-as", pkg, "ls", "-la"])
    print("\n[Explicacao] 'run-as' so funciona se o app tiver a flag "
          "'debuggable' no manifesto (builds de debug). Apps de producao da "
          "Play Store normalmente NAO sao debuggable, entao isso deve falhar "
          "com algo como 'run-as: package not debuggable'.")

    # --- armazenamento externo com escopo (scoped storage) ---
    secao(f"3c. /sdcard/Android/data/{pkg} (armazenamento externo do app)")
    rodar_comando([adb_path, "shell", "ls", "-la", f"/sdcard/Android/data/{pkg}"])

    secao(f"3d. /sdcard/Android/data/{pkg}/files")
    rodar_comando([adb_path, "shell", "ls", "-la", f"/sdcard/Android/data/{pkg}/files"])

    print("\n[Explicacao] Desde o Android 11+, /sdcard/Android/data costuma "
          "estar bloqueado tambem para o adb comum (scoped storage), mas em "
          "algumas versoes/configuracoes ainda e legivel. Vale a pena testar.")

    # --- obb ---
    secao(f"3e. /sdcard/Android/obb/{pkg} (arquivos obb, se existirem)")
    rodar_comando([adb_path, "shell", "ls", "-la", f"/sdcard/Android/obb/{pkg}"])

    # --- teste de backup (so relato, sem executar) ---
    secao(f"3f. Possibilidade de 'adb backup' para {pkg}")
    if allow_backup:
        print("[Resultado] Flag ALLOW_BACKUP encontrada no dumpsys -> "
              f"vale a pena tentar manualmente:\n"
              f"  adb backup -f pokegenie.ab {pkg}\n"
              "(Nao executado automaticamente por este script, pois pode "
              "exigir confirmacao manual na tela do celular.)")
    else:
        print("[Resultado] Flag ALLOW_BACKUP NAO encontrada (ou nao "
              "identificada) no dumpsys -> 'adb backup' provavelmente "
              "retornara um arquivo vazio ou sera bloqueado. Ainda assim, "
              "pode ser testado manualmente, mas expectativa e baixa.")

    return {
        "pkg": pkg,
        "allow_backup": allow_backup,
        "debuggable": debuggable,
    }


def buscar_arquivos_compartilhados(adb_path):
    """Procura por arquivos relacionados ao Poke Genie e por exports CSV
    genericos em pastas comuns de armazenamento compartilhado."""
    secao("4. BUSCANDO ARQUIVOS EM ARMAZENAMENTO COMPARTILHADO (/sdcard)")

    print("\n--- Procurando por qualquer arquivo/pasta com 'genie' no nome "
          "(ate 3 niveis de profundidade em /sdcard) ---")
    rodar_comando([
        adb_path, "shell",
        "find", "/sdcard", "-maxdepth", "3", "-iname", "*genie*",
    ])

    print("\n--- Procurando por arquivos .csv em /sdcard/Download e "
          "/sdcard/Documents (possiveis exports) ---")
    rodar_comando([
        adb_path, "shell",
        "find", "/sdcard/Download", "/sdcard/Documents",
        "-iname", "*.csv",
    ])

    print("\n[Explicacao] Muitos apps de scan/coleta oferecem opcao de "
          "'exportar CSV' que salva em Download ou em uma pasta propria "
          "dentro de /sdcard. Esta busca tenta achar esses arquivos "
          "independentemente do pacote detectado.")


def imprimir_resumo(pacotes_encontrados, resultados_pacotes):
    """Imprime a secao final de resumo/interpretacao."""
    secao("RESUMO")

    if not pacotes_encontrados:
        print("Nenhum pacote do Poke Genie foi encontrado no dispositivo.")
        print("Nao foi possivel investigar dados locais porque o app parece "
              "nao estar instalado (ou o nome do pacote nao contem 'genie' "
              "nem 'poke').")
        print("\nRecomendacao: confirmar manualmente o nome do pacote "
              "instalado (ex.: nrs.pokegenie) e reexecutar este script, ou "
              "seguir direto para a estrategia de OCR sobre screenshots da "
              "tela do app.")
        return

    print(f"Pacotes investigados: {', '.join(pacotes_encontrados)}\n")

    algum_debuggable = any(r["debuggable"] for r in resultados_pacotes)
    algum_allow_backup = any(r["allow_backup"] for r in resultados_pacotes)

    print("Interpretacao dos resultados:")
    print("- Dados internos do app (/data/data/<pkg>): normalmente "
          "INACESSIVEIS sem root, pois o Android protege essa area por "
          "sandboxing. O resultado de 'ls -la' ali deve mostrar "
          "'Permission denied' em um dispositivo sem root.")

    if algum_debuggable:
        print("- 'run-as' funcionou (ou o app aparenta ser 'debuggable') em "
              "pelo menos um pacote: isso pode permitir acessar os dados "
              "internos SEM root, via 'adb shell run-as <pkg> ...'. Vale a "
              "pena explorar mais essa via.")
    else:
        print("- 'run-as' provavelmente NAO funciona (app nao e "
              "'debuggable', como e comum em apps de producao da Play "
              "Store). Essa via de acesso aos dados internos esta fechada "
              "sem root.")

    if algum_allow_backup:
        print("- ALLOW_BACKUP esta ativo em pelo menos um pacote: "
              "'adb backup' pode ser uma via viavel para extrair dados sem "
              "root (requer confirmacao manual na tela do celular).")
    else:
        print("- ALLOW_BACKUP nao foi identificado como ativo: 'adb backup' "
              "tem baixa chance de trazer dados uteis.")

    print("- Armazenamento externo (/sdcard/Android/data/<pkg> e "
          "/sdcard/Android/obb/<pkg>): pode ou nao estar acessivel "
          "dependendo da versao do Android (scoped storage). Verifique os "
          "resultados das secoes 3c/3d/3e acima.")

    print("- Busca por arquivos com 'genie' no nome e por CSVs em "
          "Download/Documents: verifique a secao 4 acima. Se algo foi "
          "encontrado, essa e provavelmente a via mais simples de extracao "
          "de dados.")

    print("\nCaminho recomendado, em ordem de preferencia:")
    print("  1) CSV export do proprio app (se o Poke Genie tiver essa opcao "
          "no menu e um arquivo .csv foi encontrado em Download/Documents "
          "ou em uma pasta propria em /sdcard).")
    print("  2) Arquivos em /sdcard/Android/data|obb/<pkg> (se acessiveis "
          "sem root, conforme testado acima).")
    print("  3) Dados internos via 'run-as' (somente se o app for "
          "'debuggable', o que e incomum em builds de producao).")
    print("  4) Se nenhuma das opcoes acima trouxer dados uteis: seguir com "
          "a estrategia de OCR sobre screenshots da tela do app (via ADB "
          "screencap), que e o fallback mais robusto e independente de "
          "root/permissoes de armazenamento.")


def main():
    print("Investigacao de armazenamento local do Poke Genie via ADB")
    print("(script somente leitura, nao modifica nada no dispositivo)\n")

    adb_path = carregar_adb_path()

    verificar_dispositivo(adb_path)

    pacotes = encontrar_pacotes_pokegenie(adb_path)

    resultados_pacotes = []
    for pkg in pacotes:
        resultado = investigar_pacote(adb_path, pkg)
        resultados_pacotes.append(resultado)

    buscar_arquivos_compartilhados(adb_path)

    imprimir_resumo(pacotes, resultados_pacotes)

    print("\nInvestigacao concluida.")


if __name__ == "__main__":
    main()
