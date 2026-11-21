"""Hub do adlens: um site com abas, no estilo de um dashboard.

`adlens hub` gera uma pasta com o index.html (e as imagens dos criativos)
pronta para publicar no GitHub Pages. Tudo é calculado aqui, no Python:
os efeitos de cada segmento (todos, cada país, cada plataforma) já vão
prontos dentro da página, e o navegador só mostra e filtra. Assim a
lógica da análise continua num lugar só.

O visual reaproveita o relatório: as cores, as fontes, o gráfico e os
destaques vêm de `adlens.report`.
"""

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from adlens.analysis import BINARY_TAGS, CATEGORICAL_TAGS
from adlens.confidence import Interval
from adlens.export import _dimensions
from adlens.performance import PerformanceRow
from adlens.regression import compute_effects
from adlens.report import (
    _ESTILO,
    TEMA_PADRAO,
    THEMES,
    Theme,
    _destaques,
    _pct,
    _vars,
    lift_chart,
)
from adlens.storage import load_countries, load_dataset
from adlens.synthetic import CreativeSpec

# (id da aba, nome no menu, selo)
ABAS = [
    ("visao", "Visão geral", ""),
    ("efeitos", "Efeitos", ""),
    ("criativos", "Criativos", ""),
    ("analisar", "Analisar criativo", "em breve"),
    ("audiencia", "Audiência sintética", "em breve"),
    ("custos", "Custos", "admin"),
    ("sobre", "Sobre", ""),
]
AMOSTRA_MINIMA = 30  # grupos menores que isso ganham um aviso
REFERENCIAS = {nome: ref for nome, ref in CATEGORICAL_TAGS.values()}
COLUNAS = {nome: col for col, nome in BINARY_TAGS.items()}
COLUNAS |= {nome: col for col, (nome, _) in CATEGORICAL_TAGS.items()}


@dataclass(frozen=True)
class Segmento:
    """Um recorte dos dados: todos, um país ou uma plataforma."""

    chave: str  # ex.: "todos", "pais-BR", "plataforma-meta"
    nome: str  # ex.: "País: BR"
    specs: list[CreativeSpec]
    rows: list[PerformanceRow]


def segments(
    specs: list[CreativeSpec], rows: list[PerformanceRow], dims: dict[str, dict]
) -> list[Segmento]:
    """Monta os segmentos: todos os criativos, cada país e cada plataforma."""
    perf = {r.creative_id: r for r in rows}
    segs = [Segmento("todos", "Todos os criativos", specs, rows)]
    for campo, rotulo, prefixo in (
        ("country", "País", "pais"),
        ("platform", "Plataforma", "plataforma"),
    ):
        valores = sorted({d[campo] for d in dims.values() if d.get(campo)})
        for valor in valores:
            sel = [s for s in specs if dims.get(s.creative_id, {}).get(campo) == valor]
            segs.append(
                Segmento(
                    f"{prefixo}-{valor}",
                    f"{rotulo}: {valor}",
                    sel,
                    [perf[s.creative_id] for s in sel],
                )
            )
    return segs


def group_size(specs: list[CreativeSpec], tag: str, value: str) -> int:
    """Quantos criativos têm aquele valor de etiqueta (ex.: cor = vermelho)."""
    coluna = COLUNAS[tag]
    if tag in REFERENCIAS:
        return sum(getattr(s, coluna) == value for s in specs)
    return sum(bool(getattr(s, coluna)) == (value == "sim") for s in specs)


def _kpis(seg: Segmento) -> str:
    impressoes = sum(r.impressions for r in seg.rows)
    cliques = sum(r.clicks for r in seg.rows)
    investimento = sum(r.spend for r in seg.rows)
    ctr = cliques / impressoes if impressoes else 0.0
    valores = [
        (f"{len(seg.specs):,}".replace(",", "."), "criativos"),
        (f"{impressoes:,}".replace(",", "."), "impressões"),
        (f"{ctr:.2%}".replace(".", ","), "CTR médio"),
        (f"R$ {investimento:,.0f}".replace(",", "."), "investimento"),
    ]
    return "".join(
        f'<div class="kpi"><b>{v}</b><span>{t}</span></div>' for v, t in valores
    )


def _tabela(seg: Segmento, intervals: list[Interval]) -> str:
    linhas = []
    for r in sorted(intervals, key=lambda r: r.lift, reverse=True):
        n = group_size(seg.specs, r.tag, r.value)
        pouco = (
            ' <span class="selo nao">amostra pequena</span>'
            if n < AMOSTRA_MINIMA
            else ""
        )
        real = "sim" if r.significant else "nao"
        linhas.append(
            f"<tr><td>{escape(r.tag)}</td><td>{escape(r.value)}</td>"
            f"<td>{escape(REFERENCIAS.get(r.tag, 'não'))}</td>"
            f'<td class="num">{_pct(r.lift)}</td>'
            f'<td class="num">{_pct(r.low)} a {_pct(r.high)}</td>'
            f'<td class="num">{n}{pouco}</td>'
            f'<td><span class="selo {real}">'
            f"{'sim' if r.significant else 'não'}</span></td></tr>"
        )
    return (
        '<div class="cartao rolagem"><table><thead><tr><th>Etiqueta</th>'
        "<th>Valor</th><th>Comparado com</th><th>Lift</th><th>Intervalo de 95%</th>"
        "<th>Criativos</th><th>Efeito real?</th></tr></thead>"
        f"<tbody>{''.join(linhas)}</tbody></table></div>"
    )


def _por_segmento(blocos: list[tuple[Segmento, str]]) -> str:
    """Um bloco por segmento; só o de "todos" começa visível."""
    return "".join(
        f'<div data-seg="{seg.chave}"{"" if seg.chave == "todos" else " hidden"}>'
        f"{html}</div>"
        for seg, html in blocos
    )


def creatives_json(
    specs: list[CreativeSpec], rows: list[PerformanceRow], dims: dict[str, dict]
) -> str:
    """Os criativos em JSON (o que a aba Criativos precisa), seguro para o HTML."""
    perf = {r.creative_id: r for r in rows}
    dados = []
    for s in specs:
        p, d = perf[s.creative_id], dims.get(s.creative_id, {})
        dados.append(
            {
                "id": s.creative_id,
                "plataforma": d.get("platform") or "",
                "pais": d.get("country") or "",
                "rosto": s.has_face,
                "produto": s.has_product,
                "cta": s.has_cta,
                "cor": s.dominant_color,
                "formato": s.format,
                "impressoes": p.impressions,
                "ctr": round(p.ctr, 6),
            }
        )
    # "</" dentro de um <script> fecharia a tag antes da hora
    return json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")


_CSS_HUB = """
body{display:grid;grid-template-columns:248px minmax(0,1fr);min-height:100vh}
.lado{position:sticky;top:0;height:100vh;background:var(--hero);color:#fff;display:flex;
  flex-direction:column;gap:24px;padding:24px 14px;overflow:hidden}
.lado .marca{padding:0 10px}
.nav{display:flex;flex-direction:column;gap:4px}
.nav a{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 12px;
  border-radius:12px;color:rgba(255,255,255,.75);text-decoration:none;font-weight:600;font-size:15px;
  transition:background .2s,color .2s}
.nav a:hover{background:rgba(255,255,255,.08);color:#fff}
.nav a:focus-visible,.btn:focus-visible,.chipsfiltro button:focus-visible,select:focus-visible{
  outline:2px solid var(--glow);outline-offset:2px}
.nav a[aria-current="page"]{background:rgba(255,255,255,.12);color:#fff;
  box-shadow:inset 3px 0 0 var(--glow)}
.nav small{font-size:10px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;
  padding:2px 7px;border-radius:999px;background:rgba(255,255,255,.12);color:var(--glow);white-space:nowrap}
.rodape-lado{margin-top:auto;font-size:12px;color:rgba(255,255,255,.55);padding:0 10px}
.conteudo{min-width:0;display:flex;flex-direction:column}
.topo{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 90%,transparent);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;
  align-items:center;gap:12px;padding:14px max(16px,env(safe-area-inset-right,0px)) 14px 28px}
.topo h1{font-family:var(--display);font-size:22px;margin:0;letter-spacing:-.3px}
.selo-demo{font-size:12px;font-weight:800;letter-spacing:.4px;padding:5px 10px;border-radius:999px;
  background:color-mix(in srgb,var(--glow) 24%,transparent);color:#6B4400}
.filtro{margin-left:auto;display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600;
  color:var(--muted)}
select{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--line);
  border-radius:12px;padding:8px 12px}
main{max-width:1100px;width:100%;margin:0 auto;padding:28px 28px 64px;display:flex;
  flex-direction:column;gap:32px}
[hidden]{display:none!important}
.kpis{grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}
.kpi b{font-size:clamp(22px,2.4vw,30px)}
.painel{display:flex;flex-direction:column;gap:32px;animation:sobe .45s cubic-bezier(.2,.8,.2,1) both}
.boas-vindas{border-radius:24px;padding:40px 36px}
.boas-vindas .hero-in{margin:0}
.link{color:var(--ink);font-weight:700}
.btn{font:inherit;font-weight:700;padding:10px 16px;border-radius:12px;border:0;background:var(--hero);
  color:#fff;cursor:pointer;text-decoration:none;align-self:flex-start}
.chipsfiltro{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.chipsfiltro button{font:inherit;font-size:14px;font-weight:600;padding:7px 12px;border-radius:999px;
  border:1px solid var(--line);background:var(--surface);color:var(--ink);cursor:pointer}
.chipsfiltro button[aria-pressed="true"]{background:var(--hero);color:#fff;border-color:var(--hero)}
.grade{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px}
.criativo{background:var(--surface);border:1px solid var(--line);border-radius:18px;overflow:hidden;
  display:flex;flex-direction:column;animation:sobe .4s both}
.criativo .img{position:relative;aspect-ratio:1/1;background:#E9EBF3;overflow:hidden}
.criativo img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
.criativo .info{padding:12px 14px;display:flex;flex-direction:column;gap:6px}
.criativo .ctr{font-family:var(--display);font-size:22px;font-weight:800}
.criativo .meta{font-size:13px;color:var(--muted)}
.tags{display:flex;flex-wrap:wrap;gap:5px}
.tags span{font-size:12px;font-weight:700;padding:2px 8px;border-radius:999px;background:#EEF0F6;
  color:var(--muted)}
.vazio{color:var(--muted)}
.embreve{display:flex;flex-direction:column;gap:20px}
.soltar{border:2px dashed var(--line);border-radius:20px;padding:40px 20px;text-align:center;
  color:var(--muted);background:var(--surface);display:flex;flex-direction:column;gap:8px;align-items:center}
.soltar b{font-family:var(--display);color:var(--ink);font-size:18px}
.passos3{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.passos3 div{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:18px}
.passos3 span{font-family:var(--display);font-weight:800;font-size:28px;color:var(--glow)}
.passos3 b{display:block;font-family:var(--display);margin:4px 0}
.passos3 p{margin:0;color:var(--muted);font-size:15px}
.cadeado{display:flex;gap:18px;align-items:flex-start;background:var(--hero);color:#fff;border-radius:20px;
  padding:24px}
.cadeado svg{flex-shrink:0}
.cadeado p{margin:4px 0 0;color:rgba(255,255,255,.75)}
.aviso-amostra{background:color-mix(in srgb,var(--glow) 18%,transparent);border-radius:14px;
  padding:12px 16px;font-size:15px}
@media (max-width:860px){
  body{display:block}
  .lado{position:sticky;z-index:10;height:auto;flex-direction:row;align-items:center;gap:14px;
    padding:12px 16px;overflow-x:auto}
  .nav{flex-direction:row}
  .nav a{white-space:nowrap}
  .rodape-lado{display:none}
  .topo{position:static;padding-left:16px}
  main{padding:20px 16px 48px}
  .boas-vindas{padding:28px 20px}
}
"""

_JS_HUB = """
(function(){
  var DADOS = JSON.parse(document.getElementById('dados').textContent);
  var IMAGENS = document.body.dataset.imagens === '1';
  var sel = document.getElementById('segmento');
  var calmo = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function contar(){
    if (calmo) return;
    document.querySelectorAll('[data-seg]:not([hidden]) .kpi b').forEach(function(el){
      var txt = el.dataset.final || el.textContent; el.dataset.final = txt;
      var m = txt.match(/[0-9][0-9.,]*/); if (!m) return;
      var bruto = m[0], dec = (bruto.split(',')[1] || '').length;
      var alvo = parseFloat(bruto.replace(/\\./g, '').replace(',', '.'));
      var ini = null;
      function passo(t){
        if (ini === null) ini = t;
        var p = Math.min(1, (t - ini) / 900); p = 1 - Math.pow(1 - p, 3);
        el.textContent = txt.replace(bruto, (alvo * p).toLocaleString('pt-BR',
          {minimumFractionDigits: dec, maximumFractionDigits: dec}));
        if (p < 1) requestAnimationFrame(passo); else el.textContent = txt;
      }
      requestAnimationFrame(passo);
    });
  }

  function mostrarAba(){
    var id = (location.hash || '#visao').slice(1);
    if (!document.getElementById('aba-' + id)) id = 'visao';
    document.querySelectorAll('.painel').forEach(function(p){ p.hidden = p.id !== 'aba-' + id; });
    document.querySelectorAll('.nav a').forEach(function(a){
      if (a.getAttribute('href') === '#' + id) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    document.getElementById('titulo').textContent =
      document.querySelector('.nav a[href="#' + id + '"] span').textContent;
    if (id === 'visao') contar();
  }

  // ---- aba Criativos ----
  var filtros = {rosto: false, produto: false, cta: false};
  var limite = 24;
  var grade = document.getElementById('grade');
  var mais = document.getElementById('mais');

  function noSegmento(c){
    var s = sel.value;
    if (s === 'todos') return true;
    var partes = s.split('-'), campo = partes[0], valor = partes.slice(1).join('-');
    return campo === 'pais' ? c.pais === valor : c.plataforma === valor;
  }

  function cartao(c){
    var el = document.createElement('article');
    el.className = 'criativo';
    var img = document.createElement('div'); img.className = 'img';
    if (IMAGENS) {
      var i = document.createElement('img');
      i.src = 'imagens/' + c.id + '.png'; i.loading = 'lazy';
      i.alt = 'criativo ' + c.id; img.appendChild(i);
    }
    var info = document.createElement('div'); info.className = 'info';
    var ctr = document.createElement('span'); ctr.className = 'ctr';
    ctr.textContent = (c.ctr * 100).toLocaleString('pt-BR',
      {minimumFractionDigits: 2, maximumFractionDigits: 2}) + '% CTR';
    var meta = document.createElement('span'); meta.className = 'meta';
    meta.textContent = c.id + ' · ' + c.plataforma + ' · ' + c.pais;
    var tags = document.createElement('div'); tags.className = 'tags';
    [c.rosto && 'rosto', c.produto && 'produto', c.cta && 'cta', c.cor, c.formato]
      .filter(Boolean).forEach(function(t){
        var s = document.createElement('span'); s.textContent = t; tags.appendChild(s);
      });
    info.append(ctr, meta, tags);
    el.append(img, info);
    return el;
  }

  function desenhar(){
    var cor = document.getElementById('f-cor').value;
    var formato = document.getElementById('f-formato').value;
    var ordem = document.getElementById('f-ordem').value;
    var lista = DADOS.filter(function(c){
      return noSegmento(c) && c.impressoes >= 1000
        && (!filtros.rosto || c.rosto) && (!filtros.produto || c.produto)
        && (!filtros.cta || c.cta) && (!cor || c.cor === cor)
        && (!formato || c.formato === formato);
    }).sort(function(a, b){ return ordem === 'asc' ? a.ctr - b.ctr : b.ctr - a.ctr; });
    grade.replaceChildren();
    lista.slice(0, limite).forEach(function(c){ grade.appendChild(cartao(c)); });
    document.getElementById('total').textContent =
      lista.length + ' criativo' + (lista.length === 1 ? '' : 's');
    document.getElementById('vazio').hidden = lista.length > 0;
    mais.hidden = lista.length <= limite;
  }

  document.querySelectorAll('.chipsfiltro button[data-filtro]').forEach(function(b){
    b.addEventListener('click', function(){
      var k = b.dataset.filtro; filtros[k] = !filtros[k];
      b.setAttribute('aria-pressed', filtros[k] ? 'true' : 'false');
      limite = 24; desenhar();
    });
  });
  ['f-cor', 'f-formato', 'f-ordem'].forEach(function(id){
    document.getElementById(id).addEventListener('change', function(){ limite = 24; desenhar(); });
  });
  mais.addEventListener('click', function(){ limite += 24; desenhar(); });

  sel.addEventListener('change', function(){
    document.querySelectorAll('[data-seg]').forEach(function(el){
      el.hidden = el.dataset.seg !== sel.value;
    });
    limite = 24; desenhar(); contar();
  });

  window.addEventListener('hashchange', mostrarAba);
  mostrarAba();
  desenhar();
})();
"""

_ICONE_CADEADO = (
    '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" aria-hidden="true"><rect x="4" y="11" width="16" height="10" '
    'rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>'
)


def build_hub(
    resultados: list[tuple[Segmento, list[Interval]]],
    criativos_json: str,
    tem_imagens: bool,
    gerado_em: datetime,
    theme: Theme = THEMES[TEMA_PADRAO],
) -> str:
    """Monta o HTML do hub (uma página só, com todas as abas)."""
    t = theme
    nav = "".join(
        f'<a href="#{aba}"><span>{nome}</span>'
        f"{f'<small>{selo}</small>' if selo else ''}</a>"
        for aba, nome, selo in ABAS
    )
    opcoes = "".join(
        f'<option value="{seg.chave}">{escape(seg.nome)}</option>'
        for seg, _ in resultados
    )
    kpis = _por_segmento(
        [(s, f'<div class="kpis">{_kpis(s)}</div>') for s, _ in resultados]
    )
    destaques = _por_segmento([(s, _destaques(i)) for s, i in resultados])

    efeitos = []
    for seg, intervals in resultados:
        pequenos = [
            r
            for r in intervals
            if group_size(seg.specs, r.tag, r.value) < AMOSTRA_MINIMA
        ]
        aviso = (
            f'<p class="aviso-amostra">Atenção: {len(pequenos)} grupo(s) com menos de '
            f"{AMOSTRA_MINIMA} criativos. Nesses, o resultado é menos confiável.</p>"
            if pequenos
            else ""
        )
        grafico = (
            f'<div class="cartao">{lift_chart(intervals, t)}<div class="legenda">'
            f'<span><i style="background:{t.positive}"></i>aumenta o CTR</span>'
            f'<span><i style="background:{t.negative}"></i>diminui o CTR</span>'
            f'<span><i style="background:{t.neutral}"></i>não dá pra afirmar</span>'
            "</div></div>"
        )
        efeitos.append((seg, aviso + grafico + _tabela(seg, intervals)))

    cores = sorted(
        {c for s, _ in resultados for c in (x.dominant_color for x in s.specs)}
    )
    formatos = sorted({f for s, _ in resultados for f in (x.format for x in s.specs)})
    op_cores = "".join(
        f'<option value="{escape(c)}">{escape(c)}</option>' for c in cores
    )
    op_formatos = "".join(
        f'<option value="{escape(f)}">{escape(f)}</option>' for f in formatos
    )
    fonte = f'<link rel="stylesheet" href="{t.font_url}">' if t.font_url else ""
    quando = gerado_em.strftime("%d/%m/%Y %H:%M UTC")

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>adlens · hub</title>{fonte}
<style>{_vars(t)}{_ESTILO}{_CSS_HUB}</style></head>
<body data-imagens="{"1" if tem_imagens else "0"}">
<aside class="lado">
<div class="marca"><i></i>adlens</div>
<nav class="nav" aria-label="Abas do hub">{nav}</nav>
<p class="rodape-lado">Atualizado em {quando}</p>
</aside>

<div class="conteudo">
<header class="topo">
<h1 id="titulo">Visão geral</h1>
<span class="selo-demo">dados de demonstração</span>
<label class="filtro" for="segmento">Ver
<select id="segmento">{opcoes}</select></label>
</header>
<main>

<section class="painel" id="aba-visao">
<div class="hero boas-vindas">
<svg class="lente" viewBox="0 0 520 520" aria-hidden="true">
<circle class="anel1" cx="260" cy="260" r="240" stroke-width="2"/>
<circle class="anel2" cx="260" cy="260" r="180" stroke-width="10"/>
<circle class="anel3" cx="260" cy="260" r="120" stroke-width="2"/>
<circle class="foco" cx="260" cy="260" r="14"/>
</svg>
<div class="hero-in">
<h2 style="font-size:clamp(28px,4.5vw,46px);line-height:1.05;max-width:16ch">
O que faz um criativo <em style="font-style:normal;color:var(--glow)">performar</em></h2>
<p>Quanto cada característica dos criativos muda o CTR, com o intervalo de confiança
de cada resposta. Escolha um país ou uma plataforma no filtro do topo.</p>
</div></div>
{kpis}
<section class="secao"><header><h2>Em destaque</h2>
<p>Os maiores efeitos que dá pra afirmar com 95% de confiança.</p></header>
{destaques}
<a class="btn" href="#efeitos">Ver todos os efeitos</a></section>
</section>

<section class="painel" id="aba-efeitos" hidden>
<section class="secao"><header><h2>Lift de cada etiqueta</h2>
<p>Barra = quanto o CTR muda com a característica. Linha = intervalo de 95%.</p></header>
{_por_segmento(efeitos)}</section>
</section>

<section class="painel" id="aba-criativos" hidden>
<section class="secao"><header><h2>Criativos da base</h2>
<p>Peças com pelo menos 1.000 impressões. Use os filtros para comparar.</p></header>
<div class="chipsfiltro">
<button type="button" data-filtro="rosto" aria-pressed="false">Com rosto</button>
<button type="button" data-filtro="produto" aria-pressed="false">Com produto</button>
<button type="button" data-filtro="cta" aria-pressed="false">Com CTA</button>
<select id="f-cor" aria-label="Cor"><option value="">Todas as cores</option>{op_cores}</select>
<select id="f-formato" aria-label="Formato"><option value="">Todos os formatos</option>
{op_formatos}</select>
<select id="f-ordem" aria-label="Ordem"><option value="desc">Maior CTR primeiro</option>
<option value="asc">Menor CTR primeiro</option></select>
<span class="meta" id="total"></span>
</div>
<div class="grade" id="grade"></div>
<p class="vazio" id="vazio" hidden>Nenhum criativo com esses filtros.</p>
<button type="button" class="btn" id="mais" hidden>Mostrar mais</button>
</section>
</section>

<section class="painel" id="aba-analisar" hidden>
<div class="embreve">
<header class="secao"><h2>Analisar um criativo</h2>
<p class="vazio">Em breve: suba uma peça e o adlens diz o que, nos dados da base, costuma
puxar o CTR pra cima ou pra baixo.</p></header>
<div class="soltar" aria-disabled="true"><b>Solte aqui uma imagem, GIF ou vídeo</b>
<span>Disponível quando o adlens tiver um servidor (fase futura)</span></div>
<div class="passos3">
<div><span>1</span><b>Sobe a peça</b><p>Estático, GIF ou vídeo. Do vídeo, o adlens
pega alguns quadros.</p></div>
<div><span>2</span><b>O Claude etiqueta</b><p>Rosto, produto, CTA, cor e formato, com a
precisão medida antes contra um gabarito.</p></div>
<div><span>3</span><b>Compara com a base</b><p>Mostra o efeito de cada característica
da peça nos dados, com o intervalo de confiança.</p></div>
</div></div>
</section>

<section class="painel" id="aba-audiencia" hidden>
<div class="embreve">
<header class="secao"><h2>Audiência sintética</h2>
<p class="vazio">Em breve: testar um criativo com audiências simuladas antes de veicular.</p>
</header>
<div class="passos3">
<div><span>1</span><b>Escolhe a peça</b><p>Um criativo da base ou um enviado.</p></div>
<div><span>2</span><b>Escolhe os perfis</b><p>Audiências segmentadas, por exemplo por
idade, região e interesse.</p></div>
<div><span>3</span><b>Vê a reação</b><p>Como cada perfil reagiria e o sentimento
geral, como um primeiro filtro antes do teste real.</p></div>
</div></div>
</section>

<section class="painel" id="aba-custos" hidden>
<div class="cadeado">{_ICONE_CADEADO}<div><h2 style="color:#fff">Só para editores</h2>
<p>No hub oficial, esta aba mostra o custo de cada execução: imagens enviadas à IA,
tokens, bytes lidos no BigQuery e tempo. Os dados ficam num dataset separado e a
página só aparece para quem edita. Num site público não existe área de admin, por
isso ela fica fechada aqui.</p></div></div>
</section>

<section class="painel" id="aba-sobre" hidden>
<section class="secao"><header><h2>Como ler</h2></header>
<div class="como">
<div><b>Lift</b><p>Quanto o CTR de quem tem a característica muda em relação à
referência (sem a característica, cor azul ou formato quadrado).</p></div>
<div><b>Intervalo de 95%</b><p>A faixa onde o efeito real provavelmente está,
calculada sorteando os criativos centenas de vezes.</p></div>
<div><b>Efeito real?</b><p>“Sim” quando o intervalo inteiro fica de um lado do zero.
Grupos com menos de {AMOSTRA_MINIMA} criativos ganham aviso.</p></div>
</div></section>
<section class="secao"><header><h2>Como o hub é feito</h2></header>
<div class="passos3">
<div><span>1</span><b>Dados</b><p>O adlens gera criativos e mídia sintéticos, com
efeitos plantados (nenhum dado de cliente).</p></div>
<div><span>2</span><b>Análise</b><p>O comando <code>adlens hub</code> calcula os efeitos
de cada país e plataforma e monta esta página.</p></div>
<div><span>3</span><b>Publicação</b><p>A cada mudança aprovada no código, o GitHub
Actions refaz o hub e publica sozinho no GitHub Pages.</p></div>
</div>
<a class="link" href="https://github.com/AryaneMuniz/adlens">Ver o código no GitHub</a>
</section>
</section>

</main>
</div>
<script type="application/json" id="dados">{criativos_json}</script>
<script>{_JS_HUB}</script>
</body></html>
"""


def publish_hub(
    pasta: Path, saida: Path, boot: int = 200, method: str = "regressao"
) -> Path:
    """Calcula tudo, grava o index.html e copia as imagens dos criativos."""
    specs, rows, _ = load_dataset(pasta)
    midia = pasta / "midia_diaria.csv"
    dims = _dimensions(midia) if midia.exists() else {}
    paises = load_countries(pasta)
    resultados = [
        (seg, compute_effects(seg.specs, seg.rows, paises, method, boot))
        for seg in segments(specs, rows, dims)
    ]
    imagens = pasta / "imagens"
    saida.mkdir(parents=True, exist_ok=True)
    if imagens.exists():
        shutil.copytree(imagens, saida / "imagens", dirs_exist_ok=True)
    html = build_hub(
        resultados,
        creatives_json(specs, rows, dims),
        imagens.exists(),
        datetime.now(UTC),
    )
    destino = saida / "index.html"
    destino.write_text(html, encoding="utf-8")
    return destino
