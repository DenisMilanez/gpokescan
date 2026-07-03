# -*- coding: utf-8 -*-
"""
Varredura do PokeGenie via arvore de UI (uiautomator).

Diferente da varredura do Pokemon GO (que usa visao/template matching de
proposito, para nao parecer bot dentro do jogo), aqui NAO ha jogo nem risco de
deteccao: estamos so lendo a nossa propria lista dentro do app PokeGenie. Por
isso usamos o caminho limpo e preciso:

  - `uiautomator dump` devolve a arvore de componentes em XML, com o TEXTO real
    de cada elemento (nome, PC, PS, IV, level, objetivo, rank...) e as
    coordenadas (`bounds`) de cada um. Nada de OCR, nada de template.
  - A leitura e independente da resolucao: o texto vem da arvore logica, nao dos
    pixels. Os poucos toques (abrir ordenacao, escolher filtro, rolar) sao
    resolvidos por fracao da tela / pelos proprios `bounds` reportados, entao
    rodam em qualquer celular.

Fluxo geral (executar):
  1. Garante que a lista "Meus Pokemons" esta aberta.
  2. Para cada filtro selecionado (IV / Grande Liga / Ultra Liga / Copinha):
       a. aplica a ordenacao correspondente (muda os dados exibidos por linha);
       b. rola do topo ate o fim capturando dumps;
       c. extrai as linhas, deduplicando as sobreposicoes da rolagem.
  3. Junta tudo num unico registro por Pokemon (formato LARGO) e salva o CSV.

Chave de identidade (invariante entre filtros), usada para juntar os modos:
  Especie + Forma + Genero + PC + PS + IV + Level
"""

import csv
import datetime
import html
import re
import subprocess
import time
from pathlib import Path

PKG = "com.cjin.pokegenie.standard"

DIR_BASE = Path(__file__).resolve().parent
DIR_SAIDA = DIR_BASE / "exports"

# Modos suportados -> texto EXATO da opcao na tela "Ordenar por" (PT-BR).
# Se o app estiver noutro idioma, e so ajustar estes rotulos.
MODO_SORT = {
    "IV": "IV",
    "GL": "PvP IV Grande Liga",
    "UL": "PvP IV Ultra Liga",
    "LC": "PvP IV Copinha",
}
MODO_NOME = {
    "IV": "IV (PvE)",
    "GL": "Grande Liga",
    "UL": "Ultra Liga",
    "LC": "Copinha",
}

# ------------------------------------------------------------------ #
# Regex de parsing das linhas
# ------------------------------------------------------------------ #
NAME_RE = re.compile(r"^(.*?) - PC (\d+) / PS (\d+)$")
IVLINE_RE = re.compile(r"^IV (.+?) / lvl ([\d.]+)")           # tolera lixo apos
OBJ_RE = re.compile(r"^Objetivo:\s*(.+?)\s*/\s*PC\s*(\d+)\s*/\s*Poeira\s*(\S+)")
DATE_RE = re.compile(r"\d{1,2}\s+de\s+\w+\.?\s+de\s+\d{4}")   # data de registro
TITLE_RE = re.compile(r"Meu Pokemon\s*\((\d+)\)")
NUM_RE = re.compile(r"^\d{1,3}(,\d)?$")                        # circulo (int ou dec)
SEC_PCT_RE = re.compile(r"^\d{1,3},\d%$")                     # % secundario (esq)
MOVE_RANK_RE = re.compile(r"^[A-F]$")                          # nota do moveset

NODE_RE = re.compile(r"<node\b[^>]*?>")


# ------------------------------------------------------------------ #
# Camada adb / dump
# ------------------------------------------------------------------ #
def _cat_bytes(conn, serial, caminho, timeout=25):
    """Le um arquivo do device como BYTES (preserva UTF-8: acentos, ♂/♀)."""
    if not conn.adb_path:
        return b""
    cmd = [conn.adb_path, "-s", serial, "exec-out", "cat", caminho]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return b""
    if proc.returncode == 0 and proc.stdout:
        return proc.stdout
    return b""


def _dump_xml(conn, retries=3):
    """Roda `uiautomator dump` e devolve o XML (str UTF-8). '' se falhar."""
    serial = conn.serial()
    if not serial:
        return ""
    for _ in range(retries):
        out, err, _ = conn.adb(
            "-s", serial, "shell", "uiautomator", "dump", "/sdcard/pg_ui.xml",
            timeout=25)
        saida = (out + " " + err)
        if "dumped to" in saida.lower():
            data = _cat_bytes(conn, serial, "/sdcard/pg_ui.xml")
            if data:
                return data.decode("utf-8", "replace")
        time.sleep(0.5)  # tela ainda animando / "could not get idle state"
    return ""


def _parse(xml):
    """
    Extrai os nos de texto do XML: lista de dicts com
    {t, xc, yc, x1, y1, x2, y2, rid}. Ignora nos sem texto (exceto pelos que
    precisamos por resource-id, tratados a parte em _find_resource).
    """
    nodes = []
    for m in NODE_RE.finditer(xml):
        s = m.group(0)
        mt = re.search(r'text="([^"]*)"', s)
        txt = html.unescape(mt.group(1)).strip() if mt else ""
        mb = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', s)
        if not mb:
            continue
        x1, y1, x2, y2 = map(int, mb.groups())
        mr = re.search(r'resource-id="([^"]*)"', s)
        rid = mr.group(1) if mr else ""
        mc = re.search(r'class="([^"]*)"', s)
        cls = mc.group(1) if mc else ""
        nodes.append({
            "t": txt, "rid": rid, "cls": cls,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "xc": (x1 + x2) // 2, "yc": (y1 + y2) // 2,
        })
    return nodes


def _topo_anuncio(nodes):
    """
    Devolve o Y do topo do banner de anuncio (AdMob) ou None se nao houver.
    O anuncio fica dentro dos bounds da lista, mas tem containers proprios
    (adview_layout / adbackground / WebView). Detectamos pelos bounds reais
    para recortar tudo abaixo dele (independe da resolucao).
    """
    tops = []
    for n in nodes:
        rid = n["rid"].lower()
        if ("adview" in rid or "adbackground" in rid or "admob" in rid
                or n["cls"].endswith("WebView")):
            tops.append(n["y1"])
    return min(tops) if tops else None


def _find_resource(nodes, rid_suffix):
    for n in nodes:
        if n["rid"].endswith(rid_suffix):
            return n
    return None


def _find_text(nodes, texto, exato=True):
    for n in nodes:
        if (n["t"] == texto) if exato else (texto in n["t"]):
            return n
    return None


def _title_count(xml):
    """Devolve N de 'Meu Pokemon (N)' ou None se nao estiver na lista."""
    m = TITLE_RE.search(xml)
    return int(m.group(1)) if m else None


# ------------------------------------------------------------------ #
# Navegacao (adaptativa: usa bounds / fracao de tela)
# ------------------------------------------------------------------ #
def _ensure_list(conn, log):
    """Garante que a lista 'Meus Pokemons' esta aberta. Retorna (ok, N)."""
    # acorda a tela caso esteja apagada (desbloqueio com PIN fica a cargo do
    # usuario; sem PIN, a lista abre normalmente).
    conn.adb("-s", conn.serial(), "shell", "input", "keyevent", "KEYCODE_WAKEUP")
    time.sleep(0.5)
    xml = _dump_xml(conn)
    n = _title_count(xml)
    if n is not None:
        return True, n

    log("PokeGenie: abrindo o app...")
    conn.adb("-s", conn.serial(), "shell", "monkey", "-p", PKG,
             "-c", "android.intent.category.LAUNCHER", "1", timeout=20)
    time.sleep(2.5)
    xml = _dump_xml(conn)
    n = _title_count(xml)
    if n is not None:
        return True, n

    # tela inicial do app -> toca em "Meus Pokemons"
    alvo = _find_text(_parse(xml), "Meus Pokemons", exato=True)
    if alvo:
        conn.tap(alvo["xc"], alvo["yc"])
        time.sleep(2.0)
        xml = _dump_xml(conn)
        n = _title_count(xml)
        if n is not None:
            return True, n
    return False, None


def _aplicar_filtro(conn, modo, log):
    """Abre 'Ordenar por' e seleciona o filtro do modo. Retorna bool."""
    xml = _dump_xml(conn)
    nodes = _parse(xml)
    sort_btn = _find_resource(nodes, ":id/action_sort")
    if not sort_btn:
        log(f"  [!] botao de ordenacao nao encontrado.")
        return False
    conn.tap(sort_btn["xc"], sort_btn["yc"])
    time.sleep(1.2)

    nodes = _parse(_dump_xml(conn))
    opt = _find_text(nodes, MODO_SORT[modo], exato=True)
    if not opt:
        log(f"  [!] opcao '{MODO_SORT[modo]}' nao encontrada na ordenacao.")
        return False
    conn.tap(opt["xc"], opt["yc"])
    time.sleep(1.6)  # volta pra lista ja reordenada
    return True


def _nomes_visiveis(nodes):
    """Assinatura da tela: os nomes de Pokemon atualmente visiveis."""
    return tuple(n["t"] for n in nodes if NAME_RE.match(n["t"]))


def _swipe_frac(conn, y_ini, y_fim, dur=550):
    """Deslize vertical no centro, em fracao da altura (independe da resolucao)."""
    w, h = conn.wm_size
    x = int(w * 0.5)
    conn.swipe(x, int(h * y_ini), x, int(h * y_fim), dur)


def _rolar_ao_topo(conn, dica_swipes=0, parar=None, max_iter=80):
    """
    Sobe a lista ate o topo (assinatura estabiliza).

    'dica_swipes' = nº de rolagens que a descida anterior precisou. Quando > 0,
    subimos essa mesma quantidade em MODO RAPIDO: swipes curtos em sequencia,
    sem dump/verificacao entre eles (a verificacao e o que custa ~1,5s por
    passo). Swipe curto ainda gera fling (inercia), entao cada um sobe MAIS que
    um swipe lento — e passar do topo e impossivel (a lista para la), o
    overshoot e inofensivo. So depois entra o modo verificado para confirmar.
    """
    for _ in range(int(dica_swipes)):
        if parar is not None and parar.is_set():
            return
        _swipe_frac(conn, 0.30, 0.82, dur=250)   # curto -> fling
        time.sleep(0.15)
    prev = None
    for _ in range(max_iter):
        if parar is not None and parar.is_set():
            return
        nodes = _parse(_dump_xml(conn))
        sig = _nomes_visiveis(nodes)
        if sig and sig == prev:
            return
        prev = sig
        _swipe_frac(conn, 0.30, 0.82)   # arrasta pra baixo = sobe o conteudo
        time.sleep(0.55)


# ------------------------------------------------------------------ #
# Extracao das linhas
# ------------------------------------------------------------------ #
def _split_nome(full):
    """De 'Vulpix (A) ♀' -> (especie='Vulpix', forma='A', genero='F')."""
    genero = "M" if "♂" in full else ("F" if "♀" in full else "")
    fm = re.search(r"\(([A-Za-z])\)", full)
    forma = fm.group(1) if fm else ""
    especie = re.sub(r"\([A-Za-z]\)", "", re.sub(r"[♂♀]", "", full)).strip()
    return especie, forma, genero


def _extrair_linhas(nodes, modo, wm_size, rows):
    """
    Percorre os blocos (um por Pokemon) do dump e preenche 'rows'
    (dict chave_identidade -> registro), mesclando campos faltantes.
    Descarta linhas parciais (sem IV) das bordas da tela.
    """
    largura, altura = wm_size
    # recorta tudo abaixo do topo do anuncio (senao o banner vaza pro moveset)
    teto_anuncio = _topo_anuncio(nodes)
    if teto_anuncio is not None:
        nodes = [n for n in nodes if n["yc"] < teto_anuncio - 5]
    idx_nomes = [i for i, n in enumerate(nodes) if NAME_RE.match(n["t"])]
    x_dir = largura * 0.72   # divisor: acima disso = coluna do circulo (direita)

    # altura tipica de uma linha (mediana dos espacamentos entre nomes). Serve
    # para NAO deixar o bloco do ultimo Pokemon estender ate o banner de anuncio.
    ys = [nodes[i]["yc"] for i in idx_nomes]
    if len(ys) >= 2:
        deltas = sorted(ys[j + 1] - ys[j] for j in range(len(ys) - 1))
        row_h = deltas[len(deltas) // 2]
    else:
        row_h = int(0.11 * altura)

    for k, i in enumerate(idx_nomes):
        n = nodes[i]
        mn = NAME_RE.match(n["t"])
        full, pc, ps = mn.group(1).strip(), mn.group(2), mn.group(3)
        especie, forma, genero = _split_nome(full)

        y_ini = n["yc"]
        y_next = nodes[idx_nomes[k + 1]]["yc"] if k + 1 < len(idx_nomes) else 10 ** 9
        # limita o bloco a UMA linha (evita o anuncio no ultimo item)
        y_fim = min(y_next, y_ini + int(row_h * 1.1))
        bloco = [nd for nd in nodes if y_ini - 5 <= nd["yc"] < y_fim - 5]

        # linha do IV (obrigatoria; se ausente, e captura parcial de borda)
        iv = lvl = ""
        iv_y = None
        for nd in bloco:
            mm = IVLINE_RE.match(nd["t"])
            if mm:
                iv, lvl = mm.group(1).strip(), mm.group(2)
                iv_y = nd["yc"]
                break
        if not iv:
            continue

        # valor do circulo (coluna da direita): int no IV, decimal no PvP
        circulo = ""
        for nd in bloco:
            if nd["xc"] > x_dir and NUM_RE.match(nd["t"]):
                circulo = nd["t"].replace(",", ".")
                break

        dados = {
            "Especie": especie, "Forma": forma, "Genero": genero,
            "PC": pc, "PS": ps, "IV": iv, "Level": lvl,
        }

        if modo == "IV":
            dados["IV_pct"] = circulo
            # 3a linha (ABAIXO do IV): moveset (golpes + nota) OU data (ignorada).
            # Exige estar abaixo da linha do IV para nao pegar o % secundario que
            # fica na mesma linha do IV (ex.: "59,4%" / faixa "24,0-88,9%").
            piso = (iv_y if iv_y is not None else y_ini) + int(row_h * 0.2)
            golpes, nota = [], ""
            for nd in bloco:
                t = nd["t"]
                if not t or nd["yc"] < piso:
                    continue
                if NAME_RE.match(t) or IVLINE_RE.match(t):
                    continue
                if DATE_RE.search(t) or t == "%":
                    continue
                if "%" in t and any(c.isdigit() for c in t):   # qualquer % -> descarta
                    continue
                if nd["xc"] > x_dir:             # circulo / etc.
                    continue
                if MOVE_RANK_RE.match(t) and nd["xc"] > largura * 0.5:
                    nota = t
                    continue
                golpes.append(t)
            dados["Moveset"] = " / ".join(golpes)
            dados["Move_Rank"] = nota
        else:
            dados[f"{modo}_rank"] = circulo
            for nd in bloco:
                mo = OBJ_RE.match(nd["t"])
                if mo:
                    dados[f"{modo}_evol"] = mo.group(1)
                    dados[f"{modo}_pc_alvo"] = mo.group(2)
                    dados[f"{modo}_poeira"] = mo.group(3)
                    break

        chave = (especie, forma, genero, pc, ps, iv, lvl)
        reg = rows.setdefault(chave, {})
        for kk, vv in dados.items():
            if vv and not reg.get(kk):
                reg[kk] = vv


def _varrer_modo(conn, modo, esperado, parar, log, dica_topo=0):
    """
    Rola a lista inteira no modo atual. Devolve (rows, n_swipes):
      rows      = chave_identidade -> registro
      n_swipes  = quantas rolagens a descida levou (vira a 'dica_topo' da
                  proxima passada, para a volta rapida ao topo).
    """
    _rolar_ao_topo(conn, dica_swipes=dica_topo, parar=parar)
    rows = {}
    prev = None
    estavel = 0
    n_swipes = 0
    falhas = 0
    teto = max(60, (esperado or 300) // 3 + 30)
    for _ in range(teto):
        if parar.is_set():
            break
        nodes = _parse(_dump_xml(conn))
        sig = _nomes_visiveis(nodes)
        if not sig:
            # Dump falhou (tipico: anuncio em video animando -> uiautomator
            # nao atinge o idle). NUNCA rolar sem ter lido a tela, senao o
            # bloco se perde. Espera o anuncio assentar e tenta de novo.
            falhas += 1
            if falhas >= 8:
                log("  [!] tela ilegivel apos varias tentativas; seguindo.")
                falhas = 0
            else:
                time.sleep(1.2)
                continue
        else:
            falhas = 0
        _extrair_linhas(nodes, modo, conn.wm_size, rows)
        if sig and sig == prev:
            estavel += 1
            if estavel >= 2:      # tela nao muda mais = fim da lista
                break
        else:
            estavel = 0
        prev = sig
        _swipe_frac(conn, 0.80, 0.32)   # arrasta pra cima = desce o conteudo
        n_swipes += 1
        time.sleep(0.6)
    return rows, n_swipes


# ------------------------------------------------------------------ #
# Saida
# ------------------------------------------------------------------ #
def _colunas(modos):
    cols = ["Especie", "Forma", "Genero", "PC", "PS", "IV", "Level"]
    if "IV" in modos:
        cols += ["IV_pct", "Moveset", "Move_Rank"]
    for m in ("GL", "UL", "LC"):
        if m in modos:
            cols += [f"{m}_rank", f"{m}_evol", f"{m}_pc_alvo", f"{m}_poeira"]
    return cols


def _salvar_csv(all_rows, modos, saida_dir=None, parcial=False):
    DIR = Path(saida_dir) if saida_dir else DIR_SAIDA
    DIR.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    sufixo = "_parcial" if parcial else ""
    destino = DIR / f"pokegenie_{carimbo}{sufixo}.csv"
    cols = _colunas(modos)

    def ordem(item):
        r = item[1]
        try:
            pc = -int(r.get("PC", 0))
        except ValueError:
            pc = 0
        return (r.get("Especie", ""), pc)

    with open(destino, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for _, reg in sorted(all_rows.items(), key=ordem):
            w.writerow(reg)
    return destino


# ------------------------------------------------------------------ #
# Orquestracao (chamada pela GUI, em thread separada)
# ------------------------------------------------------------------ #
def executar(conn, modos, log=print, parar=None, saida_dir=None):
    """
    Roda a varredura do PokeGenie para os 'modos' selecionados
    (subconjunto de ['IV','GL','UL','LC']) e salva o CSV largo.
    """
    import threading
    if parar is None:
        parar = threading.Event()

    if not conn or not conn.serial():
        log("PokeGenie: nenhum device conectado.")
        return
    if not conn.wm_size:
        conn.verificar_conexao()
    if not conn.wm_size:
        log("PokeGenie: nao consegui obter a resolucao da tela.")
        return

    modos = [m for m in ("IV", "GL", "UL", "LC") if m in modos]
    if not modos:
        log("PokeGenie: nenhum filtro selecionado.")
        return

    ok, esperado = _ensure_list(conn, log)
    if not ok:
        log("PokeGenie: nao encontrei a lista 'Meus Pokemons'. "
            "Abra o PokeGenie e tente de novo.")
        return
    log(f"PokeGenie: lista aberta com {esperado} Pokemon. "
        f"Filtros: {', '.join(MODO_NOME[m] for m in modos)}.")

    all_rows = {}
    dica_topo = 0    # nº de rolagens da descida anterior -> volta rapida ao topo
    for modo in modos:
        if parar.is_set():
            log("PokeGenie: abortado pelo usuario.")
            break
        log(f"— Filtro {MODO_NOME[modo]} —")
        if not _aplicar_filtro(conn, modo, log):
            log(f"  [!] pulando {MODO_NOME[modo]} (falha ao aplicar o filtro).")
            continue
        rows, dica_topo = _varrer_modo(conn, modo, esperado, parar, log,
                                       dica_topo=dica_topo)
        status = "OK" if (esperado and len(rows) == esperado) else "CONFERIR"
        log(f"  {MODO_NOME[modo]}: {len(rows)} unicos "
            f"(esperado {esperado}) [{status}]")
        if esperado and len(rows) < esperado - 5:
            log(f"  [!] faltaram {esperado - len(rows)} neste filtro — "
                f"vale rodar de novo so ele (anuncios podem ter atrapalhado).")
        for chave, dados in rows.items():
            reg = all_rows.setdefault(chave, {})
            for kk, vv in dados.items():
                if vv and not reg.get(kk):
                    reg[kk] = vv

    if not all_rows:
        log("PokeGenie: nada foi coletado.")
        return

    parcial = parar.is_set()
    if parcial:
        log("PokeGenie: salvando CSV PARCIAL (so o que foi coletado ate o abort).")
    destino = _salvar_csv(all_rows, modos, saida_dir, parcial=parcial)
    rotulo = "PARCIAL" if parcial else "OK"
    log(f"[{rotulo}] PokeGenie: CSV salvo em {destino}  ({len(all_rows)} Pokemon).")
    return destino
