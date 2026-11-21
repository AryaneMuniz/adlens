"""Página do adlens para o Hub (rascunho).

Mostra como uma página no Dataviz pode ser montada SÓ com as tabelas do
contrato de dados (adlens_criativos e adlens_efeitos). Se esta página
funciona lendo apenas os arquivos exportados, a página oficial também vai
funcionar lendo as mesmas tabelas no BigQuery.

Os filtros de país e plataforma rodam no navegador (JavaScript), sem
precisar de servidor.
"""

import csv
import json
from dataclasses import dataclass
from html import escape
from pathlib import Path

from adlens.analysis import BINARY_TAGS
from adlens.export import CRIATIVOS_SCHEMA, EFEITOS_SCHEMA
from adlens.report import TEMA_PADRAO, THEMES, Theme, _css, lift_chart


def _ler(path: Path, schema: list[tuple[str, str, str]]) -> list[dict]:
    """Lê uma tabela do contrato e confere se as colunas são as combinadas."""
    if not path.exists():
        raise FileNotFoundError(
            f"Não achei {path.name} em {path.parent.resolve()}. "
            "Rode antes: adlens exportar"
        )
    esperado = [c for c, _, _ in schema]
    with path.open(encoding="utf-8", newline="") as f:
        leitor = csv.DictReader(f)
        if leitor.fieldnames != esperado:
            raise ValueError(f"{path.name} está fora do contrato de dados")
        return list(leitor)


def read_contract(pasta: Path) -> tuple[list[dict], list[dict]]:
    """Lê as duas tabelas do contrato (criativos e efeitos)."""
    criativos = _ler(pasta / "adlens_criativos.csv", CRIATIVOS_SCHEMA)
    efeitos = _ler(pasta / "adlens_efeitos.csv", EFEITOS_SCHEMA)
    return criativos, efeitos


def latest_run(rows: list[dict]) -> list[dict]:
    """Só as linhas da execução mais recente.

    No BigQuery as execuções se acumulam; a página mostra a última.
    """
    if not rows:
        return []
    ultimo = max(r["run_id"] for r in rows)
    return [r for r in rows if r["run_id"] == ultimo]


@dataclass(frozen=True)
class ContractEffect:
    """Uma linha da tabela de efeitos, já com os tipos certos.

    O "efeito real?" vem pronto da coluna `significant`: a página não refaz a
    conta (na regressão, ele depende da correção para muitas etiquetas).
    """

    tag: str
    value: str
    lift: float
    low: float
    high: float
    significant: bool


def to_intervals(efeitos: list[dict]) -> list[ContractEffect]:
    """Transforma as linhas da tabela de efeitos no formato do gráfico."""
    return [
        ContractEffect(
            e["tag"],
            e["value"],
            float(e["lift"]),
            float(e["ci_low"]),
            float(e["ci_high"]),
            e["significant"] == "true",
        )
        for e in efeitos
    ]


def _etiquetas(c: dict) -> str:
    """Resumo das etiquetas de um criativo, ex.: 'rosto · cta · vermelho · vertical'."""
    sim = [nome for coluna, nome in BINARY_TAGS.items() if c[coluna] == "true"]
    return " · ".join([*sim, c["dominant_color"], c["format"]])


def _dados_json(criativos: list[dict]) -> str:
    """Os criativos em JSON (só o que a página usa), seguro para ir no HTML."""
    linhas = [
        {
            "ad_name": c["ad_name"],
            "platform": c["platform"],
            "country": c["country"],
            "tags": _etiquetas(c),
            "impressions": int(c["impressions"]),
            "clicks": int(c["clicks"]),
            "investment": float(c["investment"]),
        }
        for c in criativos
    ]
    # "</" dentro de um <script> fecharia a tag antes da hora
    return json.dumps(linhas, ensure_ascii=False).replace("</", "<\\/")


def _opcoes(criativos: list[dict], coluna: str) -> str:
    valores = sorted({c[coluna] for c in criativos})
    return "".join(f'<option value="{escape(v)}">{escape(v)}</option>' for v in valores)


# Roda no navegador: refaz os números e as tabelas quando o filtro muda
_JS = """
const DADOS = JSON.parse(document.getElementById('dados').textContent);
const $ = (id) => document.getElementById(id);
const inteiro = (n) => n.toLocaleString('pt-BR');
const reais = (n) => 'R$ ' + inteiro(Math.round(n));
const pct = (x) => (x * 100).toLocaleString('pt-BR',
  {minimumFractionDigits: 2, maximumFractionDigits: 2}) + '%';

function somar(lista) {
  const t = {n: lista.length, impressions: 0, clicks: 0, investment: 0};
  for (const c of lista) {
    t.impressions += c.impressions;
    t.clicks += c.clicks;
    t.investment += c.investment;
  }
  t.ctr = t.impressions ? t.clicks / t.impressions : 0;
  return t;
}

function preencher(id, linhas, primeiraNumerica) {
  const corpo = $(id).tBodies[0];
  corpo.replaceChildren();
  for (const valores of linhas) {
    const tr = corpo.insertRow();
    valores.forEach((v, i) => {
      const td = tr.insertCell();
      td.textContent = v;
      if (i >= primeiraNumerica) td.className = 'num';
    });
  }
}

function porGrupo(lista, campo) {
  const grupos = {};
  for (const c of lista) (grupos[c[campo]] ??= []).push(c);
  return Object.entries(grupos)
    .map(([nome, itens]) => [nome, somar(itens)])
    .sort((a, b) => b[1].impressions - a[1].impressions)
    .map(([nome, t]) => [nome, inteiro(t.n), inteiro(t.impressions),
                         pct(t.ctr), reais(t.investment)]);
}

function atualizar() {
  const pais = $('pais').value;
  const plataforma = $('plataforma').value;
  const lista = DADOS.filter((c) =>
    (!pais || c.country === pais) && (!plataforma || c.platform === plataforma));
  const t = somar(lista);
  $('k-criativos').textContent = inteiro(t.n);
  $('k-impressoes').textContent = inteiro(t.impressions);
  $('k-ctr').textContent = pct(t.ctr);
  $('k-investimento').textContent = reais(t.investment);
  preencher('t-plataforma', porGrupo(lista, 'platform'), 1);
  preencher('t-pais', porGrupo(lista, 'country'), 1);
  const top = lista.filter((c) => c.impressions >= 1000)
    .sort((a, b) => b.clicks / b.impressions - a.clicks / a.impressions)
    .slice(0, 10)
    .map((c) => [c.ad_name, c.platform, c.country, c.tags,
                 inteiro(c.impressions), pct(c.clicks / c.impressions)]);
  preencher('t-top', top, 4);
}

$('pais').addEventListener('change', atualizar);
$('plataforma').addEventListener('change', atualizar);
atualizar();
"""

_CSS_EXTRA = """
.filtros{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.filtros label{font-size:13px}
.filtros select{display:block;margin-top:4px;padding:6px 8px;font:inherit}
.rolagem{overflow-x:auto}
.grafico-rola{overflow-x:auto}
.grafico-rola .grafico{display:block}
@media (max-width:640px){
  .rolagem table{min-width:560px}
  .grafico-rola .grafico{min-width:560px}
  .grafico-rola::before{content:"Deslize para o lado para ver o gráfico inteiro →";
    display:block;font-size:13px;font-weight:600;color:#5A5F7A;margin-bottom:8px}
}
.duas{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}
"""


def build_panel(
    criativos: list[dict], efeitos: list[dict], theme: Theme = THEMES[TEMA_PADRAO]
) -> str:
    """Monta o HTML da página, usando só as tabelas do contrato."""
    efeitos = latest_run(efeitos)
    fonte = f'<link rel="stylesheet" href="{theme.font_url}">' if theme.font_url else ""
    execucao = f"execução {escape(efeitos[0]['run_id'])}" if efeitos else "sem execução"
    grupo = (
        "<thead><tr><th>{}</th><th>Criativos</th><th>Impressões</th>"
        "<th>CTR</th><th>Investimento</th></tr></thead><tbody></tbody>"
    )

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>adlens · painel</title>{fonte}<style>{_css(theme)}{_CSS_EXTRA}</style></head>
<body><div class="faixa"></div><main>
<h1>adlens · painel de criativos</h1>
<p class="sub">Rascunho da página do Hub · lê só as tabelas do contrato
(adlens_criativos e adlens_efeitos) · {execucao}</p>

<div class="filtros">
<label>País<select id="pais"><option value="">Todos</option>
{_opcoes(criativos, "country")}</select></label>
<label>Plataforma<select id="plataforma"><option value="">Todas</option>
{_opcoes(criativos, "platform")}</select></label>
</div>

<div class="kpis">
<div class="kpi"><b id="k-criativos">{len(criativos)}</b><span>criativos</span></div>
<div class="kpi"><b id="k-impressoes">-</b><span>impressões</span></div>
<div class="kpi"><b id="k-ctr">-</b><span>CTR médio</span></div>
<div class="kpi"><b id="k-investimento">-</b><span>investimento</span></div>
</div>

<h2>O que puxa o CTR</h2>
<p class="nota">Calculado com todos os criativos (os filtros não mudam este
gráfico). Barra clara = não dá pra afirmar que o efeito é real.</p>
<div class="grafico-rola">{lift_chart(to_intervals(efeitos), theme)}</div>

<div class="duas">
<div><h2>Por plataforma</h2><div class="rolagem">
<table id="t-plataforma">{grupo.format("Plataforma")}</table></div></div>
<div><h2>Por país</h2><div class="rolagem">
<table id="t-pais">{grupo.format("País")}</table></div></div>
</div>

<h2>Top 10 criativos por CTR</h2>
<p class="nota">Só criativos com pelo menos 1.000 impressões.</p>
<div class="rolagem"><table id="t-top"><thead><tr><th>Anúncio</th>
<th>Plataforma</th><th>País</th><th>Etiquetas</th><th>Impressões</th>
<th>CTR</th></tr></thead><tbody></tbody></table></div>
</main>
<script type="application/json" id="dados">{_dados_json(criativos)}</script>
<script>{_JS}</script>
</body></html>
"""
