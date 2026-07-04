# -*- coding: utf-8 -*-
"""
Gera um dashboard HTML autocontido a partir de um CSV exportado do PokeGenie
(pela raspagem em pokegenie.py).

Segue o mesmo padrao do relatorio do trader-agent: Python so com stdlib le o
CSV, monta um payload JSON e injeta num template HTML unico (CSS + JS embutidos,
Chart.js via CDN). O arquivo resultante abre offline no navegador, sem servidor.

Uso:
    python gerar_dashboard.py [caminho_do_csv]

Sem argumento, usa o pokegenie_*.csv mais recente (nao-parcial) em ./exports/.
Saida: pokescan/dashboard/dashboard.html (pasta propria do dashboard)
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

DIR_BASE = Path(__file__).resolve().parent
DIR_EXPORTS = DIR_BASE / "exports"
DIR_DASH = DIR_BASE.parent / "dashboard"      # area propria do dashboard
POKEDEX_CACHE = DIR_BASE / "pokedex.json"     # nome -> numero (baixado 1x do PokeAPI)

LIGAS = [("LC", "Copinha"), ("GL", "Grande Liga"), ("UL", "Ultra Liga")]


def achar_csv() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    cands = sorted(
        (p for p in DIR_EXPORTS.glob("pokegenie_*.csv") if "_parcial" not in p.name),
        key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        sys.exit("Nenhum CSV pokegenie_*.csv encontrado em exports/.")
    return cands[0]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm_nome(especie: str, genero: str = "") -> str:
    """Normaliza o nome do PokeGenie p/ o formato do PokeAPI
    (ex.: \"Mr. Mime\" -> mr-mime, \"Farfetch'd\" -> farfetchd, Nidoran+M -> nidoran-m)."""
    s = unicodedata.normalize("NFD", especie.lower().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")   # tira acentos
    s = re.sub(r"\(.*?\)", "", s).strip()   # "zygarde (10)" -> "zygarde"
    if s == "nidoran":
        s += "-f" if genero == "F" else "-m"
    s = s.replace("♀", "-f").replace("♂", "-m")
    for ch in (".", "'", "’", ":"):
        s = s.replace(ch, "")
    return re.sub(r"\s+", "-", s.strip())


def carregar_pokedex() -> dict:
    """nome (PokeAPI) -> numero da Pokedex Nacional. Usa o cache local;
    na primeira vez baixa a lista completa do PokeAPI (1 requisicao)."""
    if POKEDEX_CACHE.exists():
        try:
            return json.loads(POKEDEX_CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        url = "https://pokeapi.co/api/v2/pokemon-species?limit=2000"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        dex = {}
        for item in data.get("results", []):
            m = re.search(r"/pokemon-species/(\d+)/?$", item["url"])
            if m:
                dex[item["name"]] = int(m.group(1))
        if dex:
            POKEDEX_CACHE.write_text(json.dumps(dex), encoding="utf-8")
        return dex
    except Exception as e:
        print(f"[aviso] sem numeros da Pokedex (falha ao baixar do PokeAPI: {e}); "
              f"a ordenacao por Pokedex ficara indisponivel ate rodar com internet.")
        return {}


def liga_info(row, pre):
    """Monta o bloco de uma liga p/ um Pokemon, ou None se nao tiver rank."""
    r = num(row.get(f"{pre}_rank"))
    if r is None:
        return None
    evol = (row.get(f"{pre}_evol") or "").strip()
    manter = (not evol) or (evol == row["Especie"])
    return {
        "rank": r,
        "evol": evol,
        "acao": "Manter" if manter else f"Evoluir → {evol}",
        "manter": manter,
        "pc_alvo": row.get(f"{pre}_pc_alvo", ""),
        "poeira": row.get(f"{pre}_poeira", ""),
    }


def construir_payload(csv_path: Path) -> dict:
    with open(csv_path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    pokedex = carregar_pokedex()
    sem_dex = set()
    pokes = []
    for i, row in enumerate(rows):
        p = {
            "idx": i,                      # ordem de leitura do CSV original
            "especie": row["Especie"],
            "forma": row.get("Forma", ""),
            "genero": row.get("Genero", ""),
            "dex": pokedex.get(_norm_nome(row["Especie"], row.get("Genero", ""))),
            "pc": num(row.get("PC")),
            "ps": num(row.get("PS")),
            "iv": row.get("IV", ""),
            "level": row.get("Level", ""),
            "iv_pct": num(row.get("IV_pct")),
            "moveset": row.get("Moveset", ""),
            "move_rank": row.get("Move_Rank", ""),
        }
        if p["dex"] is None:
            sem_dex.add(row["Especie"])
        for pre, _ in LIGAS:
            p[pre] = liga_info(row, pre)
        pokes.append(p)
    if sem_dex:
        print(f"[aviso] {len(sem_dex)} especie(s) sem numero de Pokedex "
              f"(vao pro fim na ordenacao): {', '.join(sorted(sem_dex)[:10])}")

    # --- marca a MELHOR copia de cada especie+forma por liga (estrela) ---
    for pre, _ in LIGAS:
        vistos = set()
        for p in sorted((x for x in pokes if x[pre]),
                        key=lambda x: -x[pre]["rank"]):
            chave = (p["especie"], p["forma"])
            p[pre]["melhor_da_especie"] = chave not in vistos
            vistos.add(chave)
    # melhor por especie+forma no PvE (IV%)
    vistos = set()
    for p in sorted((x for x in pokes if x["iv_pct"] is not None),
                    key=lambda x: -x["iv_pct"]):
        chave = (p["especie"], p["forma"])
        p["pve_melhor"] = chave not in vistos
        vistos.add(chave)

    # --- KPIs ---
    sf = Counter((p["especie"], p["forma"]) for p in pokes)
    solitarios = sorted(f"{e}{' ('+fo+')' if fo else ''}" for (e, fo), c in sf.items() if c == 1)
    kpis = {
        "total": len(pokes),
        "especies": len({p["especie"] for p in pokes}),
        "especie_forma": len(sf),
        "solitarios": len(solitarios),
        "hundos_iv": sum(1 for p in pokes if p["iv_pct"] == 100),
    }

    # --- graficos (agregados prontos) ---
    iv_buckets = {"100": 0, "96-99": 0, "90-95": 0, "<90": 0}
    for p in pokes:
        v = p["iv_pct"]
        if v is None:
            continue
        iv_buckets["100" if v == 100 else "96-99" if v >= 96 else
                   "90-95" if v >= 90 else "<90"] += 1
    near, evo_keep = {}, {}
    for pre, nome in LIGAS:
        com = [p for p in pokes if p[pre]]
        near[nome] = sum(1 for p in com if p[pre]["rank"] >= 95)
        bons = [p for p in com if p[pre]["rank"] >= 90]
        evo_keep[nome] = [
            sum(1 for p in bons if not p[pre]["manter"]),   # evoluir
            sum(1 for p in bons if p[pre]["manter"]),        # manter
        ]

    # --- trade fodder: especie+forma com copias fracas em todas as ligas ---
    def fraco(p):
        rs = [p[pre]["rank"] for pre, _ in LIGAS if p[pre]]
        ivw = (p["iv_pct"] or 0) < 90
        return ivw and (not rs or max(rs) < 50)

    fracos_por_sf = Counter((p["especie"], p["forma"]) for p in pokes if fraco(p))
    trade = []
    for (e, fo), n_fracos in fracos_por_sf.most_common():
        if n_fracos < 1:
            continue
        total = sf[(e, fo)]
        trade.append({
            "especie": e, "forma": fo, "total": total,
            "fracos": n_fracos,
            "descartaveis": max(0, min(n_fracos, total - 1)),  # sempre guarda >=1
        })

    return {
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fonte": csv_path.name,
        "kpis": kpis,
        "solitarios": solitarios,
        "pokes": pokes,
        "graficos": {"iv_buckets": iv_buckets, "near": near, "evo_keep": evo_keep},
        "trade": trade,
    }


def gerar(csv_path: Path) -> Path:
    payload = construir_payload(csv_path)
    html = _TEMPLATE.replace("/*__DATA__*/", json.dumps(payload, ensure_ascii=False))
    DIR_DASH.mkdir(parents=True, exist_ok=True)
    destino = DIR_DASH / "dashboard.html"
    destino.write_text(html, encoding="utf-8")
    return destino


# ────────────────────────────────────────────────────────────────────────────
# Template HTML (CSS + JS embutidos; dados injetados em /*__DATA__*/)
# ────────────────────────────────────────────────────────────────────────────
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PokeScan — Dashboard da Coleção</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{
    --bg:#0f1720; --card:#17222e; --card2:#1d2a38; --line:#2b3b4d;
    --txt:#e7eef5; --dim:#8fa3b5; --accent:#3b82f6; --accent2:#ef4444;
    --ok:#22c55e; --warn:#f59e0b;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);
       font-family:"Segoe UI",system-ui,Arial,sans-serif;font-size:14px}
  header{padding:18px 22px;border-bottom:1px solid var(--line);
         display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
  header h1{margin:0;font-size:20px}
  header .meta{color:var(--dim);font-size:12px}
  .tabs{display:flex;gap:4px;padding:10px 16px 0;flex-wrap:wrap;
        border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
  .tab{padding:9px 16px;border:1px solid var(--line);border-bottom:none;
       border-radius:8px 8px 0 0;background:var(--card);color:var(--dim);cursor:pointer;font-weight:600}
  .tab.active{background:var(--card2);color:var(--txt);border-color:var(--accent)}
  .panel{display:none;padding:18px 22px}
  .panel.active{display:block}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
  .kpi .v{font-size:26px;font-weight:700}
  .kpi .l{color:var(--dim);font-size:12px;margin-top:2px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  @media(max-width:860px){.grid2{grid-template-columns:1fr}}
  .box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:16px}
  .box h3{margin:0 0 10px;font-size:14px;color:var(--dim);font-weight:600;text-transform:uppercase;letter-spacing:.5px}
  .toolbar{display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
  input[type=search]{background:var(--card2);border:1px solid var(--line);color:var(--txt);
       border-radius:8px;padding:8px 10px;min-width:200px}
  label.chk{color:var(--dim);display:flex;align-items:center;gap:6px;cursor:pointer;user-select:none}
  table{border-collapse:collapse;width:100%;font-size:13px}
  th,td{padding:7px 9px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
  th{color:var(--dim);cursor:pointer;position:sticky;top:0;background:var(--card);user-select:none;z-index:2}
  th:hover{color:var(--txt)}
  tbody tr:hover{background:var(--card2)}
  .rank{font-weight:700;border-radius:6px;padding:2px 8px;color:#04121f}
  .pill{padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600}
  .manter{background:#123524;color:#6ee7a8;border:1px solid #1f6b45}
  .evoluir{background:#3a2a12;color:#f6c874;border:1px solid #7a5a1f}
  .star{color:var(--warn)}
  .muted{color:var(--dim)}
  .note{color:var(--dim);font-size:12px;margin:8px 0 0}
  .tablewrap{max-height:70vh;overflow:auto;border:1px solid var(--line);border-radius:12px}
  /* aba Limpeza */
  .params{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-bottom:12px;color:var(--dim)}
  .params label{display:flex;align-items:center;gap:6px}
  .params input[type=number]{background:var(--card2);border:1px solid var(--line);color:var(--txt);
       border-radius:6px;padding:4px 6px;width:64px}
  .toolbar input[type=number],.toolbar select{background:var(--card2);border:1px solid var(--line);
       color:var(--txt);border-radius:8px;padding:8px 10px}
  .pgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;max-height:68vh;overflow:auto;padding:4px}
  .pcard{background:var(--card2);border:2px solid var(--line);border-radius:12px;padding:10px;text-align:center}
  .pcard.a-manter{border-color:#1f6b45}
  .pcard.a-trade{border-color:#2b5f8a}
  .pcard.a-excluir{border-color:#7a1f1f}
  .pcard.done{opacity:.4}
  .pcard .cp{color:var(--dim);font-size:12px}
  .pcard .ph{width:60px;height:60px;border-radius:50%;border:2px dashed var(--line);
       display:flex;align-items:center;justify-content:center;margin:6px auto;font-size:22px;color:var(--dim)}
</style>
</head>
<body>
<header>
  <h1>🔴 PokeScan — Coleção</h1>
  <span class="meta" id="meta"></span>
</header>

<div class="tabs" id="tabs"></div>

<div id="panels">
  <div class="panel active" data-tab="Visão Geral" id="p-geral"></div>
  <div class="panel" data-tab="PvE" id="p-pve"></div>
  <div class="panel" data-tab="Copinha" id="p-LC"></div>
  <div class="panel" data-tab="Grande Liga" id="p-GL"></div>
  <div class="panel" data-tab="Ultra Liga" id="p-UL"></div>
  <div class="panel" data-tab="Duplicados / Trade" id="p-trade"></div>
  <div class="panel" data-tab="Limpeza 🧹" id="p-limpeza"></div>
  <div class="panel" data-tab="Cobertura" id="p-cob"></div>
</div>

<script>
const D = /*__DATA__*/;

// ---------- helpers ----------
const $ = s => document.querySelector(s);
const el = (t,c,h)=>{const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.innerHTML=h; return e;};
const gen = g => g==='M'?'♂':g==='F'?'♀':'—';
const rankColor = r => `hsl(${Math.max(0,Math.min(120, r*1.2))} 70% 55%)`;
const fmt = v => v==null?'—':(Math.round(v*10)/10).toString();

// ---------- tabs ----------
const panels=[...document.querySelectorAll('.panel')];
const tabsBox=$('#tabs');
panels.forEach((p,i)=>{
  const t=el('div','tab'+(i===0?' active':''), p.dataset.tab);
  t.onclick=()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    panels.forEach(x=>x.classList.remove('active'));
    t.classList.add('active'); p.classList.add('active');
  };
  tabsBox.appendChild(t);
});

$('#meta').textContent = `${D.fonte} · gerado em ${D.gerado_em} · ${D.kpis.total} Pokémon`;

// ---------- tabela ordenavel/filtravel generica ----------
function tabela(cols, linhas, sortIdx){
  const wrap=el('div','tablewrap');
  const tb=el('table');
  const thead=el('thead'); const trh=el('tr');
  cols.forEach((c,i)=>{
    const th=el('th',null,c.t + ' <span class="muted"></span>');
    th.onclick=()=>ordenar(i, c.num);
    trh.appendChild(th);
  });
  thead.appendChild(trh); tb.appendChild(thead);
  const tbody=el('tbody'); tb.appendChild(tbody);
  wrap.appendChild(tb);

  let ordCol=sortIdx==null?-1:sortIdx, ordDir=-1;   // -1 = mantem a ordem dada
  function render(filtro=''){
    const f=filtro.toLowerCase();
    let dados=linhas.filter(l=>!f || l.busca.includes(f));
    if(ordCol>=0) dados.sort((a,b)=>{
      let x=a.v[ordCol], y=b.v[ordCol];
      if(cols[ordCol].num){x=x==null?-1:x; y=y==null?-1:y; return (x-y)*ordDir;}
      return String(x).localeCompare(String(y))*ordDir;
    });
    tbody.innerHTML='';
    dados.forEach(l=>tbody.appendChild(l.tr));
  }
  function ordenar(i,isNum){ if(i===ordCol) ordDir*=-1; else {ordCol=i; ordDir=isNum?-1:1;} render(cur); }
  let cur='';
  render.set=v=>{cur=v; render(v);};
  render();
  return {wrap, filtrar:v=>render.set(v)};
}

function celRank(li){
  if(!li) return {v:null,h:'<span class="muted">—</span>'};
  const s = li.melhor_da_especie ? '<span class="star" title="melhor cópia sua desta espécie">★</span> ' : '';
  return {v:li.rank, h:`${s}<span class="rank" style="background:${rankColor(li.rank)}">${fmt(li.rank)}%</span>`};
}
function celAcao(li){
  if(!li) return {v:'',h:'<span class="muted">—</span>'};
  const cls = li.manter?'manter':'evoluir';
  return {v:li.acao, h:`<span class="pill ${cls}">${li.acao}</span>`};
}

// ---------- painel de detalhe (drill-down) ----------
// Classifica cada copia p/ decisao rapida no jogo:
//   forte = melhor copia sua da especie em alguma frente (PvE ou liga)
//   fraco = IV<90 e nenhum rank de liga >= 50 (candidato a descarte)
function classifica(p){
  const rs=['LC','GL','UL'].map(k=>p[k]?p[k].rank:null).filter(v=>v!=null);
  const forte = p.pve_melhor || ['LC','GL','UL'].some(k=>p[k]&&p[k].melhor_da_especie);
  const fraco = (p.iv_pct||0)<90 && (!rs.length || Math.max(...rs)<50);
  return forte?'forte':(fraco?'fraco':'ok');
}
function detalhe(host, titulo, lista, ordena){
  host.innerHTML='';
  if(!lista.length){host.appendChild(el('div','box','<span class="muted">Nada para listar.</span>'));return;}
  const box=el('div','box');
  box.appendChild(el('h3',null,`${titulo} — ${lista.length} Pokémon (identifique no jogo por PC + PS + IV + Lvl + gênero)`));
  const cols=[{t:'Situação'},{t:'Espécie'},{t:'Forma'},{t:'Gên'},{t:'PC',num:true},{t:'PS',num:true},
              {t:'IV'},{t:'Lvl',num:true},{t:'IV%',num:true},{t:'Copinha%',num:true},{t:'Grande%',num:true},{t:'Ultra%',num:true}];
  const peso={forte:0,ok:1,fraco:2};
  const ordenada=[...lista].sort(ordena || ((a,b)=>peso[classifica(a)]-peso[classifica(b)] || (b.iv_pct||0)-(a.iv_pct||0)));
  const linhas=ordenada.map(p=>{
    const cl=classifica(p);
    const tag= cl==='forte' ? '<span class="pill manter">★ forte / manter</span>'
             : cl==='fraco' ? '<span class="pill" style="background:#3a1212;color:#f87171;border:1px solid #7a1f1f">descartável</span>'
             : '<span class="muted">mediano</span>';
    const rk=k=>p[k]?`<span class="rank" style="background:${rankColor(p[k].rank)}">${fmt(p[k].rank)}%</span>`:'<span class="muted">—</span>';
    const forma=p.forma?`<span class="pill" style="background:#20364d">${p.forma}</span>`:'';
    const tr=el('tr');
    tr.innerHTML=`<td>${tag}</td><td><b>${p.especie}</b></td><td>${forma}</td><td>${gen(p.genero)}</td>`+
      `<td><b>${p.pc??'—'}</b></td><td>${p.ps??'—'}</td><td>${p.iv}</td><td>${p.level}</td>`+
      `<td>${p.iv_pct!=null?`<span class="rank" style="background:${rankColor(p.iv_pct)}">${p.iv_pct}%</span>`:'—'}</td>`+
      `<td>${rk('LC')}</td><td>${rk('GL')}</td><td>${rk('UL')}</td>`;
    return {tr,busca:(p.especie+' '+p.forma).toLowerCase(),
            v:[cl,p.especie,p.forma,p.genero,p.pc,p.ps,p.iv,+p.level||0,p.iv_pct,
               p.LC?p.LC.rank:null,p.GL?p.GL.rank:null,p.UL?p.UL.rank:null]};
  });
  const t=tabela(cols,linhas,null);
  box.appendChild(t.wrap);
  host.appendChild(box);
  host.scrollIntoView({behavior:'smooth',block:'nearest'});
}

// ---------- tabela de uma liga ----------
function tabelaLiga(pre){
  const cols=[
    {t:'', num:false},{t:'Espécie',num:false},{t:'Forma',num:false},{t:'Gên',num:false},
    {t:'PC',num:true},{t:'IV',num:false},{t:'Lvl',num:false},
    {t:'Rank%',num:true},{t:'Ação',num:false},{t:'PC-alvo',num:true},{t:'Poeira',num:false},
  ];
  const linhas = D.pokes.filter(p=>p[pre]).map(p=>{
    const li=p[pre]; const r=celRank(li), a=celAcao(li);
    const tr=el('tr');
    const forma=p.forma?`<span class="pill" style="background:#20364d">${p.forma}</span>`:'';
    tr.innerHTML = `<td>${li.melhor_da_especie?'<span class=star>★</span>':''}</td>`+
      `<td><b>${p.especie}</b></td><td>${forma}</td><td>${gen(p.genero)}</td>`+
      `<td>${p.pc??'—'}</td><td>${p.iv}</td><td>${p.level}</td>`+
      `<td>${r.h}</td><td>${a.h}</td><td>${li.pc_alvo||'—'}</td><td>${li.poeira||'—'}</td>`;
    return {tr, busca:(p.especie+' '+p.forma).toLowerCase(),
            v:[li.melhor_da_especie?1:0,p.especie,p.forma,p.genero,p.pc,p.iv,p.level,li.rank,li.acao,+li.pc_alvo||0,li.poeira]};
  });
  return {cols,linhas};
}

function montarLiga(id, pre, titulo){
  const P=$('#p-'+id);
  const box=el('div','box');
  box.appendChild(el('h3',null,`${titulo} — ${D.pokes.filter(p=>p[pre]).length} com ranking · ★ = sua melhor cópia da espécie`));
  const tb=el('div','toolbar');
  const busca=el('input'); busca.type='search'; busca.placeholder='filtrar espécie...';
  const lblMelhor=el('label','chk');
  const ckMelhor=el('input'); ckMelhor.type='checkbox';
  lblMelhor.append(ckMelhor, document.createTextNode(' só a melhor de cada espécie'));
  const lblTop=el('label','chk');
  const ckTop=el('input'); ckTop.type='checkbox';
  lblTop.append(ckTop, document.createTextNode(' só rank ≥ 90'));
  tb.append(busca,lblMelhor,lblTop);
  box.appendChild(tb);

  const {cols,linhas}=tabelaLiga(pre);
  let atual=linhas;
  const host=el('div');
  box.appendChild(host);
  P.appendChild(box);
  P.appendChild(el('p','note','A "Ação" vem do próprio PokéGenie: '+
    '<span class="pill manter">Manter</span> = já é a forma ideal p/ a liga · '+
    '<span class="pill evoluir">Evoluir → X</span> = rende mais evoluindo (custo em poeira ao lado).'));

  function redesenhar(){
    let dados=linhas;
    if(ckMelhor.checked) dados=dados.filter(l=>l.v[0]===1);
    if(ckTop.checked) dados=dados.filter(l=>l.v[7]>=90);
    host.innerHTML='';
    const t=tabela(cols,dados,7);
    host.appendChild(t.wrap);
    t.filtrar(busca.value);
    busca.oninput=()=>t.filtrar(busca.value);
  }
  ckMelhor.onchange=redesenhar; ckTop.onchange=redesenhar;
  redesenhar();
}

// ---------- PvE ----------
function montarPvE(){
  const P=$('#p-pve');
  const box=el('div','box');
  box.appendChild(el('h3',null,'PvE — ordenado por IV% (★ = sua melhor cópia da espécie)'));
  const busca=el('input'); busca.type='search'; busca.placeholder='filtrar espécie...';
  const tb=el('div','toolbar'); tb.appendChild(busca); box.appendChild(tb);
  const cols=[{t:'',num:false},{t:'Espécie',num:false},{t:'Forma',num:false},{t:'Gên',num:false},
              {t:'PC',num:true},{t:'IV',num:false},{t:'Lvl',num:false},{t:'IV%',num:true}];
  const linhas=D.pokes.filter(p=>p.iv_pct!=null).map(p=>{
    const best=p.pve_melhor; const tr=el('tr');
    const forma=p.forma?`<span class="pill" style="background:#20364d">${p.forma}</span>`:'';
    tr.innerHTML=`<td>${best?'<span class=star>★</span>':''}</td><td><b>${p.especie}</b></td>`+
      `<td>${forma}</td><td>${gen(p.genero)}</td><td>${p.pc??'—'}</td><td>${p.iv}</td>`+
      `<td>${p.level}</td><td><span class="rank" style="background:${rankColor(p.iv_pct)}">${p.iv_pct}%</span></td>`;
    return {tr,busca:(p.especie+' '+p.forma).toLowerCase(),
            v:[best?1:0,p.especie,p.forma,p.genero,p.pc,p.iv,p.level,p.iv_pct]};
  });
  const host=el('div'); box.appendChild(host); P.appendChild(box);
  const t=tabela(cols,linhas,7); host.appendChild(t.wrap);
  busca.oninput=()=>t.filtrar(busca.value);
  P.appendChild(el('p','note','IV% é a métrica de PvE do PokéGenie (o círculo no modo IV). '+
    'Lembre: espécie forte importa mais que IV% para raide — cruzar com meta virá depois.'));
}

// ---------- Visão Geral ----------
function montarGeral(){
  const P=$('#p-geral');
  const k=D.kpis;
  const cards=el('div','cards');
  [['Total',k.total],['Espécies',k.especies],['Espécie+Forma',k.especie_forma],
   ['Solitários 🔒',k.solitarios],['Hundos IV',k.hundos_iv]].forEach(([l,v])=>{
    const c=el('div','kpi'); c.appendChild(el('div','v',v)); c.appendChild(el('div','l',l)); cards.appendChild(c);
  });
  P.appendChild(cards);
  const g=el('div','grid2');
  const b1=el('div','box'); b1.appendChild(el('h3',null,'Distribuição de IV% (PvE)'));
  const cv1=el('canvas'); b1.appendChild(cv1);
  const b2=el('div','box'); b2.appendChild(el('h3',null,'Quase-perfeitos por liga (rank ≥ 95)'));
  const cv2=el('canvas'); b2.appendChild(cv2);
  g.append(b1,b2); P.appendChild(g);
  const b3=el('div','box'); b3.appendChild(el('h3',null,'Rank ≥ 90: Evoluir vs Manter (por liga)'));
  const cv3=el('canvas'); cv3.style.maxHeight='260px'; b3.appendChild(cv3); P.appendChild(b3);
  P.appendChild(el('p','note','Clique numa barra para listar os Pokémon por trás dela.'));
  const det=el('div'); P.appendChild(det);   // secao de detalhe dos graficos

  const LIGA_PRE={'Copinha':'LC','Grande Liga':'GL','Ultra Liga':'UL'};

  const ivb=D.graficos.iv_buckets;
  new Chart(cv1,{type:'bar',data:{labels:Object.keys(ivb),
    datasets:[{data:Object.values(ivb),backgroundColor:'#3b82f6'}]},
    options:{plugins:{legend:{display:false}},scales:{y:{ticks:{color:'#8fa3b5'}},x:{ticks:{color:'#8fa3b5'}}},
      onClick:(e,els)=>{ if(!els.length) return;
        const lab=Object.keys(ivb)[els[0].index];
        const lista=D.pokes.filter(p=>{const v=p.iv_pct; if(v==null)return false;
          return lab==='100'?v===100 : lab==='96-99'?(v>=96&&v<100) : lab==='90-95'?(v>=90&&v<96) : v<90;});
        detalhe(det, `IV% na faixa ${lab}`, lista, (a,b)=>(b.iv_pct||0)-(a.iv_pct||0));
      }}});
  const nk=D.graficos.near;
  new Chart(cv2,{type:'bar',data:{labels:Object.keys(nk),
    datasets:[{data:Object.values(nk),backgroundColor:['#a855f7','#3b82f6','#f59e0b']}]},
    options:{plugins:{legend:{display:false}},scales:{y:{ticks:{color:'#8fa3b5'}},x:{ticks:{color:'#8fa3b5'}}},
      onClick:(e,els)=>{ if(!els.length) return;
        const nome=Object.keys(nk)[els[0].index], pre=LIGA_PRE[nome];
        const lista=D.pokes.filter(p=>p[pre]&&p[pre].rank>=95);
        detalhe(det, `${nome}: rank ≥ 95`, lista, (a,b)=>b[pre].rank-a[pre].rank);
      }}});
  const ek=D.graficos.evo_keep; const labs=Object.keys(ek);
  new Chart(cv3,{type:'bar',data:{labels:labs,datasets:[
    {label:'Evoluir',data:labs.map(l=>ek[l][0]),backgroundColor:'#f59e0b'},
    {label:'Manter',data:labs.map(l=>ek[l][1]),backgroundColor:'#22c55e'}]},
    options:{indexAxis:'y',responsive:true,scales:{x:{stacked:true,ticks:{color:'#8fa3b5'}},
      y:{stacked:true,ticks:{color:'#8fa3b5'}}},plugins:{legend:{labels:{color:'#e7eef5'}}},
      onClick:(e,els)=>{ if(!els.length) return;
        const nome=labs[els[0].index], pre=LIGA_PRE[nome];
        const querManter=els[0].datasetIndex===1;
        const lista=D.pokes.filter(p=>p[pre]&&p[pre].rank>=90&&p[pre].manter===querManter);
        detalhe(det, `${nome}: rank ≥ 90 · ${querManter?'Manter':'Evoluir'}`, lista, (a,b)=>b[pre].rank-a[pre].rank);
      }}});
}

// ---------- Trade ----------
function montarTrade(){
  const P=$('#p-trade');
  const box=el('div','box');
  box.appendChild(el('h3',null,'Candidatos a trade/transferência — cópias fracas (IV<90 e rank<50 em todas as ligas) · clique numa linha para ver as cópias'));
  const det=el('div');   // secao de detalhe, fora do box
  const cols=[{t:'Espécie',num:false},{t:'Forma',num:false},{t:'Cópias',num:true},
              {t:'Fracas',num:true},{t:'Descartáveis (guarda ≥1)',num:true}];
  const linhas=D.trade.map(t=>{
    const tr=el('tr');
    tr.style.cursor='pointer';
    const forma=t.forma?`<span class="pill" style="background:#20364d">${t.forma}</span>`:'';
    tr.innerHTML=`<td><b>${t.especie}</b></td><td>${forma}</td><td>${t.total}</td>`+
      `<td>${t.fracos}</td><td><b style="color:${t.descartaveis?'#f6c874':'#8fa3b5'}">${t.descartaveis}</b></td>`;
    tr.onclick=()=>{
      const copias=D.pokes.filter(p=>p.especie===t.especie && p.forma===t.forma);
      detalhe(det, `Cópias de ${t.especie}${t.forma?' ('+t.forma+')':''}`, copias);
    };
    return {tr,busca:(t.especie+' '+t.forma).toLowerCase(),
            v:[t.especie,t.forma,t.total,t.fracos,t.descartaveis]};
  });
  const t=tabela(cols,linhas,4); box.appendChild(t.wrap); P.appendChild(box);
  P.appendChild(el('p','note','"Descartáveis" já reserva 1 exemplar por espécie+forma. '+
    'Isto é só uma sugestão bruta — a decisão real (e proteção de Sortudo/Shiny/Sombroso) fica pro script de exclusão.'));
  P.appendChild(det);
}

// ---------- Cobertura ----------
function montarCobertura(){
  const P=$('#p-cob');
  const box=el('div','box');
  box.appendChild(el('h3',null,`Solitários — ${D.solitarios.length} espécie+forma com apenas 1 exemplar (🔒 NÃO excluir)`));
  const grid=el('div');
  grid.style.cssText='display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:6px';
  D.solitarios.forEach(s=>{const c=el('div','pill'); c.style.cssText='background:#122; border:1px solid #1f6b45; text-align:center'; c.textContent='🔒 '+s; grid.appendChild(c);});
  box.appendChild(grid); P.appendChild(box);
}

// ---------- Limpeza (planner de exclusao) ----------
function montarLimpeza(){
  const P=$('#p-limpeza');
  D.pokes.forEach(p=>p._uid=[p.especie,p.forma,p.genero,p.pc,p.ps,p.iv,p.level].join('|'));
  const copias={};
  D.pokes.forEach(p=>{const k=p.especie+'|'+p.forma; copias[k]=(copias[k]||0)+1;});

  // marcacoes "feito no jogo" persistidas no navegador (sobrevivem a regenerar o dash)
  const LS='pokescan_limpeza_v1';
  let feito={}; try{feito=JSON.parse(localStorage.getItem(LS))||{};}catch(e){}
  const salvar=()=>localStorage.setItem(LS,JSON.stringify(feito));

  // --- parametros ---
  const box=el('div','box');
  box.appendChild(el('h3',null,'Parâmetros da limpeza — mexa nos valores e o plano recalcula na hora'));
  const form=el('div','params');
  form.innerHTML=`
    <label>Cópias mín. por espécie+forma <input type="number" id="l-min" value="1" min="1"></label>
    <label><input type="checkbox" id="l-best" checked> proteger ★ melhores cópias (PvE e ligas)</label>
    <label>Proteger IV% ≥ <input type="number" id="l-iv" value="95"></label>
    <label>Copinha ≥ <input type="number" id="l-lc" value="90"></label>
    <label>Grande ≥ <input type="number" id="l-gl" value="90"></label>
    <label>Ultra ≥ <input type="number" id="l-ul" value="90"></label>
    <label>Proteger PC ≥ <input type="number" id="l-pc" value="2500" title="rede de segurança p/ Master/raides (não raspamos a Master League)"></label>
    <label>Trades por espécie ≤ <input type="number" id="l-trsp" value="2" min="0" title="dentre os condenados de cada espécie, os N de maior PC viram Trade"></label>
    <label>Limite total de trades <input type="number" id="l-tr" value="0" min="0" title="0 = sem limite; se passar, corta priorizando espécies mais raras"></label>`;
  box.appendChild(form);
  const resumo=el('div','cards'); box.appendChild(resumo);
  P.appendChild(box);

  // --- grade estilo Pokemon GO ---
  const fbox=el('div','box');
  const ftools=el('div','toolbar');
  const fBusca=el('input'); fBusca.type='search'; fBusca.placeholder='nome...';
  const fMin=el('input'); fMin.type='number'; fMin.placeholder='PC mín'; fMin.style.width='84px';
  const fMax=el('input'); fMax.type='number'; fMax.placeholder='PC máx'; fMax.style.width='84px';
  const fAcao=el('select');
  fAcao.innerHTML='<option value="">todas as ações</option><option>Excluir</option><option>Trade</option><option>Manter</option>';
  const fOrd=el('select');
  fOrd.innerHTML='<option value="dex">ordem: Pokédex</option>'+
    '<option value="csv">ordem: CSV original</option>'+
    '<option value="pc-">ordem: PC maior→menor</option>'+
    '<option value="pc+">ordem: PC menor→maior</option>'+
    '<option value="az">ordem: Nome A-Z</option>';
  const fPend=el('label','chk'); const ckPend=el('input'); ckPend.type='checkbox';
  fPend.append(ckPend, document.createTextNode(' só pendentes'));
  const btnCsv=el('button',null,'⬇ Exportar CSV do plano');
  btnCsv.style.cssText='background:var(--accent);color:#fff;border:none;border-radius:8px;padding:8px 14px;font-weight:700;cursor:pointer';
  ftools.append(fBusca,fMin,fMax,fAcao,fOrd,fPend,btnCsv);
  fbox.appendChild(ftools);
  const prog=el('div','note'); fbox.appendChild(prog);
  const grid=el('div','pgrid'); fbox.appendChild(grid);
  P.appendChild(fbox);
  P.appendChild(el('p','note','Como espelhar com o jogo: busque o mesmo nome lá e aqui e ordene por PC nos dois. '+
    'A caixa ✔ diz que você excluiu/tradeou DE FATO no jogo — fica salva neste navegador e vira a coluna "Excluido_no_jogo" do CSV.'));

  // --- motor de classificacao ---
  function planejar(){
    const cfg={min:Math.max(1,+$('#l-min').value||1), best:$('#l-best').checked,
      iv:+$('#l-iv').value||999, lc:+$('#l-lc').value||999,
      gl:+$('#l-gl').value||999, ul:+$('#l-ul').value||999,
      pc:+$('#l-pc').value||1e9,
      trsp:Math.max(0,+$('#l-trsp').value||0), tr:Math.max(0,+$('#l-tr').value||0)};
    D.pokes.forEach(p=>{p._acao='Excluir'; p._motivo='';});
    // 1) cota: as melhores K copias de cada especie+forma ficam SEMPRE
    const porSF={};
    D.pokes.forEach(p=>{(porSF[p.especie+'|'+p.forma]=porSF[p.especie+'|'+p.forma]||[]).push(p);});
    const score=p=>Math.max(p.iv_pct||0, ...['LC','GL','UL'].map(k=>p[k]?p[k].rank:0));
    Object.values(porSF).forEach(list=>{
      [...list].sort((a,b)=>score(b)-score(a)).slice(0,cfg.min)
        .forEach(p=>{p._acao='Manter'; p._motivo='cota da espécie';});
    });
    // 2) protecoes por merito
    D.pokes.forEach(p=>{
      if(p._acao==='Manter') return;
      if(cfg.best && (p.pve_melhor || ['LC','GL','UL'].some(k=>p[k]&&p[k].melhor_da_especie)))
        {p._acao='Manter'; p._motivo='★ melhor cópia'; return;}
      if((p.iv_pct||0)>=cfg.iv){p._acao='Manter'; p._motivo='IV% alto'; return;}
      if(p.LC&&p.LC.rank>=cfg.lc){p._acao='Manter'; p._motivo='Copinha'; return;}
      if(p.GL&&p.GL.rank>=cfg.gl){p._acao='Manter'; p._motivo='Grande Liga'; return;}
      if(p.UL&&p.UL.rank>=cfg.ul){p._acao='Manter'; p._motivo='Ultra Liga'; return;}
      if((p.pc||0)>=cfg.pc){p._acao='Manter'; p._motivo='PC alto (Master/raide)'; return;}
    });
    // 3) trade: por especie, ate K condenados de maior PC viram Trade
    //    (os melhores da especie ja estao protegidos pelas regras acima).
    //    Limite total opcional corta priorizando especies mais raras.
    if(cfg.trsp>0){
      const porEsp={};
      D.pokes.filter(p=>p._acao==='Excluir')
        .forEach(p=>{(porEsp[p.especie+'|'+p.forma]=porEsp[p.especie+'|'+p.forma]||[]).push(p);});
      let cand=[];
      Object.values(porEsp).forEach(list=>{
        list.sort((a,b)=>(b.pc||0)-(a.pc||0));
        cand.push(...list.slice(0,cfg.trsp));
      });
      if(cfg.tr>0){
        cand.sort((a,b)=>(copias[a.especie+'|'+a.forma]-copias[b.especie+'|'+b.forma])||((b.pc||0)-(a.pc||0)));
        cand=cand.slice(0,cfg.tr);
      }
      cand.forEach(p=>{p._acao='Trade'; p._motivo='melhor condenado da espécie';});
    }
    // resumo
    const c={Manter:0,Trade:0,Excluir:0};
    D.pokes.forEach(p=>c[p._acao]++);
    resumo.innerHTML='';
    [['Manter',c.Manter,'#22c55e'],['Trade',c.Trade,'#3b82f6'],['Excluir',c.Excluir,'#ef4444'],
     ['Espaço liberado',c.Trade+c.Excluir,'#f59e0b']].forEach(([l,v,cor])=>{
      const k=el('div','kpi');
      k.innerHTML=`<div class="v" style="color:${cor}">${v}</div><div class="l">${l}</div>`;
      resumo.appendChild(k);
    });
    desenhar();
  }

  // --- grade ---
  function desenhar(){
    const f=fBusca.value.toLowerCase(), mn=+fMin.value||0, mx=+fMax.value||1e9, ac=fAcao.value;
    let lista=D.pokes.filter(p=>(!f||p.especie.toLowerCase().includes(f))
      && (p.pc||0)>=mn && (p.pc||0)<=mx && (!ac||p._acao===ac)
      && (!ckPend.checked || (p._acao!=='Manter' && !feito[p._uid])));
    const ord=fOrd.value;
    lista.sort((a,b)=>{
      if(ord==='dex') return ((a.dex??99999)-(b.dex??99999))
        || a.especie.localeCompare(b.especie) || (b.pc||0)-(a.pc||0);
      if(ord==='csv') return a.idx-b.idx;
      if(ord==='pc-') return (b.pc||0)-(a.pc||0);
      if(ord==='pc+') return (a.pc||0)-(b.pc||0);
      return a.especie.localeCompare(b.especie) || (b.pc||0)-(a.pc||0);
    });
    const alvo=D.pokes.filter(p=>p._acao!=='Manter');
    const feitos=alvo.filter(p=>feito[p._uid]).length;
    const corte=lista.length>600;
    prog.textContent=`Exibindo ${corte?600:lista.length} de ${lista.length}`+
      `${corte?' (refine os filtros p/ ver o resto)':''} · Faxina: ${feitos} de ${alvo.length} feitos`;
    grid.innerHTML='';
    lista.slice(0,600).forEach(p=>{
      const done=!!feito[p._uid];
      const card=el('div',`pcard a-${p._acao.toLowerCase()}${done?' done':''}`);
      const forma=p.forma?` <span class="pill" style="background:#20364d">${p.forma}</span>`:'';
      const pill=p._acao==='Manter'?'<span class="pill manter">Manter</span>':
                 p._acao==='Trade'?'<span class="pill" style="background:#12283a;color:#7cc0f8;border:1px solid #2b5f8a">Trade</span>':
                 '<span class="pill" style="background:#3a1212;color:#f87171;border:1px solid #7a1f1f">Excluir</span>';
      const mini=(lab,v)=>v==null
        ?`<span class="muted" style="font-size:11px">${lab} —</span>`
        :`<span style="font-size:11px;color:#04121f;background:${rankColor(v)};border-radius:5px;padding:1px 5px;font-weight:700">${lab} ${fmt(v)}%</span>`;
      card.innerHTML=`<div class="cp">${p.dex?'#'+String(p.dex).padStart(3,'0')+' · ':''}PC <b style="color:var(--txt);font-size:15px">${p.pc??'—'}</b></div>`+
        `<div class="ph">?</div>`+
        `<div><b>${p.especie}</b>${forma} ${gen(p.genero)}</div>`+
        `<div class="muted" style="font-size:12px">IV ${p.iv} · lvl ${p.level} · PS ${p.ps??'—'}</div>`+
        `<div style="display:flex;gap:4px;justify-content:center;flex-wrap:wrap;margin-top:5px">`+
          mini('PvE',p.iv_pct)+mini('Cop',p.LC?p.LC.rank:null)+
          mini('GL',p.GL?p.GL.rank:null)+mini('UL',p.UL?p.UL.rank:null)+`</div>`+
        `<div style="margin:6px 0" title="${p._motivo}">${pill}</div>`;
      if(p._acao!=='Manter'){
        const lb=el('label','chk'); lb.style.justifyContent='center';
        const ck=el('input'); ck.type='checkbox'; ck.checked=done;
        ck.onchange=()=>{ if(ck.checked) feito[p._uid]=new Date().toISOString();
                          else delete feito[p._uid]; salvar(); desenhar(); };
        lb.append(ck, document.createTextNode(' feito no jogo'));
        card.appendChild(lb);
      }
      grid.appendChild(card);
    });
  }

  // --- exportacao ---
  btnCsv.onclick=()=>{
    const cols=['Especie','Forma','Genero','PC','PS','IV','Level','IV_pct',
                'LC_rank','GL_rank','UL_rank','Acao','Excluido_no_jogo','Data_marcacao'];
    const esc=v=>{v=(v==null?'':String(v)); return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;};
    const linhas=[cols.join(',')];
    D.pokes.forEach(p=>{
      linhas.push([p.especie,p.forma,p.genero,p.pc,p.ps,p.iv,p.level,p.iv_pct,
        p.LC?p.LC.rank:'',p.GL?p.GL.rank:'',p.UL?p.UL.rank:'',p._acao,
        feito[p._uid]?'sim':'nao', feito[p._uid]||''].map(esc).join(','));
    });
    const blob=new Blob(['﻿'+linhas.join('\r\n')],{type:'text/csv;charset=utf-8'});
    const a=document.createElement('a');
    const d=new Date(), pad=n=>String(n).padStart(2,'0');
    a.download=`plano_limpeza_${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}.csv`;
    a.href=URL.createObjectURL(blob); a.click(); URL.revokeObjectURL(a.href);
  };

  ['l-min','l-best','l-iv','l-lc','l-gl','l-ul','l-pc','l-trsp','l-tr'].forEach(id=>{$('#'+id).onchange=planejar;});
  [fBusca,fMin,fMax].forEach(i=>i.oninput=desenhar);
  fAcao.onchange=desenhar; fOrd.onchange=desenhar; ckPend.onchange=desenhar;
  planejar();
}

// ---------- rodape: legenda das formas ----------
function montarRodape(){
  const f=el('div','box');
  f.style.cssText='margin:18px 22px';
  f.innerHTML=`
  <h3>Legenda das formas — a letra abrevia o NOME da forma e depende da espécie</h3>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px">
    <div>
      <b>Regionais</b><br>
      <span class="pill" style="background:#20364d">A</span> Alola &nbsp;·&nbsp;
      <span class="pill" style="background:#20364d">G</span> Galar &nbsp;·&nbsp;
      <span class="pill" style="background:#20364d">H</span> Hisui &nbsp;·&nbsp;
      <span class="pill" style="background:#20364d">P</span> Paldea (Wooper)
    </div>
    <div>
      <b>Específicas da espécie</b><br>
      Pumpkaboo <span class="pill" style="background:#20364d">S</span>/<span class="pill" style="background:#20364d">A</span>/<span class="pill" style="background:#20364d">L</span> = tamanho Pequeno/Médio/Grande ·
      Indeedee &amp; Oinkologne <span class="pill" style="background:#20364d">M</span>/<span class="pill" style="background:#20364d">F</span> = Macho/Fêmea ·
      Shaymin <span class="pill" style="background:#20364d">T</span> = Terrestre ·
      Meloetta <span class="pill" style="background:#20364d">C</span> = Canto (Aria) ·
      Castform <span class="pill" style="background:#20364d">C</span>/<span class="pill" style="background:#20364d">S</span> = climáticas ·
      Oricorio <span class="pill" style="background:#20364d">P</span> = estilo de dança
    </div>
  </div>
  <p class="note">⚠ Atenção à pegadinha: Vulpix (A) é de <b>Alola</b>, mas Pumpkaboo (A) é tamanho <b>Médio</b> (Average) — sempre leia a letra junto com a espécie.</p>`;
  document.body.appendChild(f);
}

montarGeral(); montarPvE();
montarLiga('LC','LC','Copinha'); montarLiga('GL','GL','Grande Liga'); montarLiga('UL','UL','Ultra Liga');
montarTrade(); montarLimpeza(); montarCobertura(); montarRodape();
</script>
</body>
</html>"""


if __name__ == "__main__":
    csv_path = achar_csv()
    saida = gerar(csv_path)
    print(f"Dashboard gerado: {saida}")
    print(f"Fonte: {csv_path.name}")
