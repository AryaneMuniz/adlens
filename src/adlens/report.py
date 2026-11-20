"""Relatório HTML do adlens.

Gera uma página única (um arquivo .html) com o resumo dos dados, um gráfico
do lift de cada etiqueta com o intervalo de confiança, a tabela completa e,
se existirem, alguns criativos de exemplo.

O visual vem de um "tema": dá pra criar temas novos sem mexer no resto
do relatório (o "O" do SOLID: aberto para extensão, fechado para alteração).
"""

from dataclasses import dataclass
from html import escape
from pathlib import Path

from adlens.confidence import LiftInterval
from adlens.performance import PerformanceRow
from adlens.synthetic import CreativeSpec


@dataclass(frozen=True)
class Theme:
    """As cores e a fonte do relatório."""

    name: str
    ink: str  # cor do texto
    muted: str  # texto secundário
    line: str  # bordas
    background: str
    accent: str  # títulos e destaques
    positive: str  # barra de efeito positivo
    negative: str  # barra de efeito negativo
    neutral: str  # barra de efeito não significativo
    stripe: str  # faixa colorida no topo
    font: str
    font_url: str = ""  # Google Fonts (opcional)


THEMES: dict[str, Theme] = {
    "neutro": Theme(
        name="neutro",
        ink="#1d1416",
        muted="#6b5a5d",
        line="#ead8db",
        background="#ffffff",
        accent="#1d1416",
        positive="#1a7f37",
        negative="#C21A31",
        neutral="#bdb3b5",
        stripe="#C21A31",
        font="Segoe UI, Arial, sans-serif",
    ),
}

ESCALA = 0.25  # o gráfico vai de -25% a +25%
LARGURA = 520  # largura da área das barras, em pixels
ALTURA_LINHA = 30


def _css(t: Theme) -> str:
    return f"""
body{{font-family:{t.font};margin:0;background:{t.background};color:{t.ink}}}
.faixa{{height:6px;background:{t.stripe}}}
main{{max-width:920px;margin:28px auto;padding:0 16px}}
h1{{margin:0;color:{t.accent}}}.sub{{color:{t.muted};margin:4px 0 24px}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:28px}}
.kpi{{background:#fff;border:1px solid {t.line};border-radius:12px;
      padding:12px 16px;min-width:150px}}
.kpi b{{display:block;font-size:22px;color:{t.accent}}}
.kpi span{{color:{t.muted};font-size:13px}}
h2{{margin:28px 0 8px;color:{t.accent}}}.nota{{color:{t.muted};font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:14px;background:#fff}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid {t.line}}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}
.sim{{color:{t.positive};font-weight:600}}.nao{{color:{t.muted}}}
.galeria{{display:flex;flex-wrap:wrap;gap:10px}}
.galeria img{{height:120px;border-radius:8px;border:1px solid {t.line}}}
"""


def _x(valor: float) -> float:
    """Converte um lift (ex.: 0.15) na posição em pixels do gráfico."""
    valor = max(-ESCALA, min(ESCALA, valor))
    return LARGURA / 2 + valor / ESCALA * (LARGURA / 2)


def lift_chart(intervals: list[LiftInterval], theme: Theme = THEMES["neutro"]) -> str:
    """Gráfico de barras (SVG) do lift, com o intervalo de 95% como uma linha."""
    ordenados = sorted(intervals, key=lambda r: r.lift, reverse=True)
    m = 150  # margem da esquerda, onde ficam os nomes
    altura = ALTURA_LINHA * len(ordenados) + 30
    zero = m + _x(0)
    partes = [
        f'<svg viewBox="0 0 {m + LARGURA + 20} {altura}" width="100%" role="img">'
    ]
    partes.append(
        f'<line x1="{zero}" y1="0" x2="{zero}" y2="{altura - 20}" '
        f'stroke="{theme.muted}"/>'
    )
    for i, r in enumerate(ordenados):
        y = i * ALTURA_LINHA + 8
        cor = theme.positive if r.lift >= 0 else theme.negative
        if not r.significant:
            cor = theme.neutral
        x0, x1 = sorted((zero, m + _x(r.lift)))
        nome = escape(f"{r.tag}: {r.value}")
        partes.append(
            f'<text x="{m - 8}" y="{y + 14}" text-anchor="end" font-size="13" '
            f'fill="{theme.ink}">{nome}</text>'
        )
        partes.append(
            f'<rect x="{x0}" y="{y + 2}" width="{max(x1 - x0, 1)}" height="16" '
            f'rx="3" fill="{cor}"/>'
        )
        partes.append(
            f'<line x1="{m + _x(r.low)}" y1="{y + 10}" x2="{m + _x(r.high)}" '
            f'y2="{y + 10}" stroke="{theme.ink}" stroke-width="1.5"/>'
        )
        # O número fica do lado de fora: à direita se for positivo, à esquerda se não
        if r.lift >= 0:
            x_txt, ancora = m + _x(r.high) + 6, "start"
        else:
            x_txt, ancora = m + _x(r.low) - 6, "end"
        partes.append(
            f'<text x="{x_txt}" y="{y + 14}" text-anchor="{ancora}" font-size="12" '
            f'fill="{theme.muted}">{r.lift:+.1%}</text>'
        )
    for v in (-0.2, -0.1, 0.1, 0.2):
        partes.append(
            f'<text x="{m + _x(v)}" y="{altura - 4}" text-anchor="middle" '
            f'font-size="11" fill="{theme.muted}">{v:+.0%}</text>'
        )
    partes.append("</svg>")
    return "\n".join(partes)


def build_report(
    intervals: list[LiftInterval],
    specs: list[CreativeSpec],
    rows: list[PerformanceRow],
    images: list[str] | None = None,
    theme: Theme = THEMES["neutro"],
) -> str:
    """Monta o HTML completo do relatório."""
    impressoes = sum(r.impressions for r in rows)
    cliques = sum(r.clicks for r in rows)
    investimento = sum(r.spend for r in rows)
    ctr = cliques / impressoes if impressoes else 0.0

    kpis = [
        (f"{len(specs):,}".replace(",", "."), "criativos"),
        (f"{impressoes:,}".replace(",", "."), "impressões"),
        (f"{ctr:.2%}".replace(".", ","), "CTR médio"),
        (f"R$ {investimento:,.0f}".replace(",", "."), "investimento"),
    ]
    kpis_html = "".join(
        f'<div class="kpi"><b>{v}</b><span>{t}</span></div>' for v, t in kpis
    )

    linhas = "".join(
        f"<tr><td>{escape(r.tag)}</td><td>{escape(r.value)}</td>"
        f'<td class="num">{r.lift:+.1%}</td>'
        f'<td class="num">{r.low:+.1%} a {r.high:+.1%}</td>'
        f'<td class="{"sim" if r.significant else "nao"}">'
        f"{'sim' if r.significant else 'não'}</td></tr>"
        for r in sorted(intervals, key=lambda r: r.lift, reverse=True)
    )

    galeria = ""
    if images:
        imgs = "".join(f'<img src="{escape(src)}" alt="criativo">' for src in images)
        galeria = f'<h2>Criativos de exemplo</h2><div class="galeria">{imgs}</div>'

    fonte = f'<link rel="stylesheet" href="{theme.font_url}">' if theme.font_url else ""

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>adlens · relatório</title>{fonte}<style>{_css(theme)}</style></head>
<body><div class="faixa"></div><main>
<h1>adlens · relatório de criativos</h1>
<p class="sub">Quais características dos criativos puxam o CTR</p>
<div class="kpis">{kpis_html}</div>
<h2>Lift de cada etiqueta</h2>
<p class="nota">Barra = quanto o CTR muda com a característica. Linha =
intervalo de 95%. Barra clara = não dá pra afirmar que o efeito é real.</p>
{lift_chart(intervals, theme)}
<h2>Tabela completa</h2>
<table><tr><th>Etiqueta</th><th>Valor</th><th>Lift</th>
<th>Intervalo de 95%</th><th>Real?</th></tr>{linhas}</table>
{galeria}
</main></body></html>
"""


def save_report(html: str, path: Path) -> Path:
    """Salva o relatório num arquivo .html."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
