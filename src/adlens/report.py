"""Relatório HTML do adlens.

Gera uma página única (um arquivo .html) com os números gerais, os efeitos
em destaque, um gráfico do lift de cada etiqueta com o intervalo de
confiança, a tabela completa e uma galeria dos criativos.

A galeria já reconhece o tipo de cada criativo pelo arquivo: imagem
estática (png, jpg, webp), GIF ou vídeo (mp4, webm, mov). Assim o relatório
está pronto para quando o adlens analisar todo tipo de peça.

O visual vem de um "tema": dá pra criar temas novos sem mexer no resto
do relatório (o "O" do SOLID: aberto para extensão, fechado para alteração).
"""

from dataclasses import dataclass
from html import escape
from pathlib import Path

from adlens.confidence import Interval
from adlens.performance import PerformanceRow
from adlens.synthetic import CreativeSpec


@dataclass(frozen=True)
class Theme:
    """As cores e as fontes do relatório."""

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
    display: str = ""  # fonte dos títulos (se vazio, usa a mesma do texto)
    hero: str = ""  # fundo da abertura (se vazio, usa a cor do texto)
    surface: str = "#ffffff"  # fundo dos cartões
    glow: str = ""  # cor de brilho da abertura (se vazio, usa o destaque)


THEMES: dict[str, Theme] = {
    "adlens": Theme(
        name="adlens",
        ink="#14163A",
        muted="#5A5F7A",
        line="#E2E5EF",
        background="#F4F5FA",
        accent="#14163A",
        positive="#0E9F8E",
        negative="#E5484D",
        neutral="#C3C7D6",
        stripe="#FFB020",
        font="Manrope, 'Segoe UI', Arial, sans-serif",
        font_url=(
            "https://fonts.googleapis.com/css2?family=Sora:wght@600;700;800"
            "&family=Manrope:wght@400;600;700&display=swap"
        ),
        display="Sora, Manrope, 'Segoe UI', Arial, sans-serif",
        hero="#14163A",
        surface="#FFFFFF",
        glow="#FFB020",
    ),
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

TEMA_PADRAO = "adlens"

ESCALA = 0.25  # o gráfico vai de -25% a +25%
LARGURA = 520  # largura da área das barras, em pixels
ALTURA_LINHA = 30

# Tipo de cada criativo pela extensão do arquivo
VIDEOS = {".mp4", ".webm", ".mov"}
GIFS = {".gif"}


def _pct(valor: float) -> str:
    """0.147 -> '+14,7%' (formato brasileiro)."""
    return f"{valor:+.1%}".replace(".", ",")


def media_type(caminho: str) -> str:
    """Diz se o criativo é estático, GIF ou vídeo, pela extensão do arquivo."""
    ext = Path(caminho).suffix.lower()
    if ext in VIDEOS:
        return "vídeo"
    if ext in GIFS:
        return "GIF"
    return "estático"


def _css(t: Theme) -> str:
    """CSS simples, usado também pela página do Hub (panel.py)."""
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


def lift_chart(intervals: list[Interval], theme: Theme = THEMES["neutro"]) -> str:
    """Gráfico de barras (SVG) do lift, com o intervalo de 95% como uma linha."""
    ordenados = sorted(intervals, key=lambda r: r.lift, reverse=True)
    m = 150  # margem da esquerda, onde ficam os nomes
    altura = ALTURA_LINHA * len(ordenados) + 30
    zero = m + _x(0)
    abertura = (
        f'<svg class="grafico" viewBox="0 0 {m + LARGURA + 20} {altura}" '
        f'width="100%" role="img" aria-label="Lift de cada etiqueta no CTR">'
    )
    partes = [abertura]
    partes.append(
        f'<line x1="{zero}" y1="0" x2="{zero}" y2="{altura - 20}" '
        f'stroke="{theme.muted}"/>'
    )
    for i, r in enumerate(ordenados):
        y = i * ALTURA_LINHA + 8
        cor = theme.positive if r.lift >= 0 else theme.negative
        if not r.significant:
            cor = theme.neutral
        lado = "pos" if r.lift >= 0 else "neg"
        atraso = f'style="animation-delay:{i * 70}ms"'
        x0, x1 = sorted((zero, m + _x(r.lift)))
        nome = escape(f"{r.tag}: {r.value}")
        partes.append(
            f'<text x="{m - 8}" y="{y + 14}" text-anchor="end" font-size="13" '
            f'fill="{theme.ink}">{nome}</text>'
        )
        partes.append(
            f'<rect class="barra {lado}" {atraso} x="{x0}" y="{y + 2}" '
            f'width="{max(x1 - x0, 1)}" height="16" rx="3" fill="{cor}"/>'
        )
        partes.append(
            f'<line class="faixa-ic" {atraso} x1="{m + _x(r.low)}" y1="{y + 10}" '
            f'x2="{m + _x(r.high)}" y2="{y + 10}" stroke="{theme.ink}" '
            f'stroke-width="1.5"/>'
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


def _vars(t: Theme) -> str:
    """As cores do tema como variáveis CSS."""
    return (
        f":root{{--ink:{t.ink};--muted:{t.muted};--line:{t.line};"
        f"--bg:{t.background};--surface:{t.surface};--accent:{t.accent};"
        f"--pos:{t.positive};--neg:{t.negative};--neutral:{t.neutral};"
        f"--stripe:{t.stripe};--hero:{t.hero or t.ink};"
        f"--glow:{t.glow or t.stripe};--font:{t.font};--display:{t.display or t.font}}}"
    )


# O visual do relatório. Usa só as variáveis do tema (nenhuma cor fixa aqui).
_ESTILO = """
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);
  font-size:16px;line-height:1.5}
.hero{position:relative;overflow:hidden;background:var(--hero);color:#fff;
  padding:56px max(16px,env(safe-area-inset-right,0px)) 72px
  max(16px,env(safe-area-inset-left,0px))}
.hero-in{position:relative;max-width:1040px;margin:0 auto;display:flex;
  flex-direction:column;gap:14px;z-index:1}
.lente{position:absolute;right:-120px;top:50%;width:520px;height:520px;
  transform:translateY(-50%);opacity:.9;pointer-events:none}
.lente circle{fill:none;stroke:var(--glow);transform-origin:260px 260px}
.anel1{stroke-opacity:.55;stroke-dasharray:4 10;animation:gira 40s linear infinite}
.anel2{stroke-opacity:.35;stroke-dasharray:60 18;animation:gira 26s linear infinite reverse}
.anel3{stroke-opacity:.25;animation:pulsa 4s ease-in-out infinite}
.foco{fill:var(--glow)!important;stroke:none!important;animation:pulsa 2.4s ease-in-out infinite}
.marca{display:flex;align-items:center;gap:10px;font-family:var(--display);
  font-weight:800;letter-spacing:.5px;font-size:18px}
.marca i{width:14px;height:14px;border-radius:50%;background:var(--glow);
  box-shadow:0 0 0 5px color-mix(in srgb,var(--glow) 30%,transparent)}
.hero h1{font-family:var(--display);font-size:clamp(34px,6vw,64px);line-height:1.03;
  letter-spacing:-1.5px;margin:6px 0 0;max-width:15ch;text-wrap:balance}
.hero h1 em{font-style:normal;color:var(--glow)}
.hero p{margin:0;max-width:56ch;color:rgba(255,255,255,.78);font-size:18px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.chip{font-size:13px;font-weight:700;letter-spacing:.4px;padding:6px 12px;border-radius:999px;
  background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18)}
main{max-width:1040px;margin:-40px auto 0;padding:0 max(16px,env(safe-area-inset-right,0px))
  64px max(16px,env(safe-area-inset-left,0px));display:flex;flex-direction:column;gap:40px;
  position:relative;z-index:2}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:20px 22px;
  box-shadow:0 12px 32px -18px rgba(20,22,58,.35)}
.kpi b{display:block;font-family:var(--display);font-size:30px;letter-spacing:-.5px;
  font-variant-numeric:tabular-nums}
.kpi span{color:var(--muted);font-size:14px;font-weight:600}
h2{font-family:var(--display);font-size:clamp(22px,3.4vw,30px);letter-spacing:-.5px;margin:0}
.secao{display:flex;flex-direction:column;gap:16px}
.secao>header{display:flex;flex-direction:column;gap:6px}
.secao>header p{margin:0;color:var(--muted);max-width:68ch}
.destaques{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.destaque{position:relative;overflow:hidden;background:var(--surface);border:1px solid var(--line);
  border-radius:20px;padding:22px;display:flex;flex-direction:column;gap:4px}
.destaque::before{content:"";position:absolute;inset:0 auto 0 0;width:6px;background:var(--pos)}
.destaque.neg::before{background:var(--neg)}
.destaque .valor{font-family:var(--display);font-size:40px;font-weight:800;letter-spacing:-1px;
  color:var(--pos);line-height:1.1}
.destaque.neg .valor{color:var(--neg)}
.destaque .nome{font-weight:700;font-size:17px}
.destaque .ic{color:var(--muted);font-size:14px}
.cartao{background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:20px}
.grafico{display:block}
.legenda{display:flex;flex-wrap:wrap;gap:16px;font-size:14px;color:var(--muted)}
.legenda span{display:inline-flex;align-items:center;gap:6px}
.legenda i{width:14px;height:10px;border-radius:3px;display:inline-block}
.rolagem{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:15px;min-width:520px}
th{text-align:left;font-size:12px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);
  padding:10px 12px;border-bottom:2px solid var(--line)}
td{padding:11px 12px;border-bottom:1px solid var(--line)}
tbody tr:hover{background:color-mix(in srgb,var(--glow) 8%,transparent)}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.selo{display:inline-block;font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px}
.selo.sim{background:color-mix(in srgb,var(--pos) 15%,transparent);color:var(--pos)}
.selo.nao{background:color-mix(in srgb,var(--neutral) 35%,transparent);color:var(--muted)}
.galeria{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.peca{position:relative;margin:0;border-radius:16px;overflow:hidden;background:var(--surface);
  border:1px solid var(--line);aspect-ratio:1/1;max-width:100%}
.peca img,.peca video{width:100%;height:100%;object-fit:cover;display:block}
.peca figcaption{position:absolute;left:8px;top:8px;font-size:11px;font-weight:800;
  letter-spacing:.6px;text-transform:uppercase;padding:4px 9px;border-radius:999px;
  background:var(--hero);color:#fff}
.peca[data-tipo="vídeo"] figcaption{background:var(--neg)}
.peca[data-tipo="GIF"] figcaption{background:var(--pos)}
.como{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.como div{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:16px 18px}
.como b{display:block;font-family:var(--display);margin-bottom:4px}
.como p{margin:0;color:var(--muted);font-size:15px}
footer{color:var(--muted);font-size:13px;text-align:center;padding-bottom:24px}
.entra{animation:sobe .7s cubic-bezier(.2,.8,.2,1) both;animation-delay:calc(var(--i,0)*90ms)}
.barra{transform-box:fill-box;animation:cresce .9s cubic-bezier(.2,.8,.2,1) both}
.barra.pos{transform-origin:left center}
.barra.neg{transform-origin:right center}
.faixa-ic{animation:aparece .6s .5s both}
@keyframes sobe{from{opacity:0;transform:translateY(18px)}}
@keyframes cresce{from{transform:scaleX(0)}}
@keyframes aparece{from{opacity:0}}
@keyframes gira{to{transform:rotate(360deg)}}
@keyframes pulsa{50%{opacity:.35}}
@media (max-width:640px){.lente{right:-260px;opacity:.5}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""

# Faz os números dos cartões "contarem" até o valor final
_JS = """
(function(){
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.querySelectorAll('.kpi b').forEach(function(el){
    var txt = el.textContent, m = txt.match(/[0-9][0-9.,]*/);
    if (!m) return;
    var bruto = m[0], dec = (bruto.split(',')[1] || '').length;
    var alvo = parseFloat(bruto.replace(/\\./g, '').replace(',', '.'));
    var ini = null, dur = 1200;
    function passo(t){
      if (ini === null) ini = t;
      var p = Math.min(1, (t - ini) / dur); p = 1 - Math.pow(1 - p, 3);
      el.textContent = txt.replace(bruto, (alvo * p).toLocaleString('pt-BR',
        {minimumFractionDigits: dec, maximumFractionDigits: dec}));
      if (p < 1) requestAnimationFrame(passo); else el.textContent = txt;
    }
    requestAnimationFrame(passo);
  });
})();
"""


def _destaques(intervals: list[Interval]) -> str:
    """Os 3 maiores efeitos positivos e o maior negativo, entre os significativos."""
    reais = [r for r in intervals if r.significant]
    positivos = sorted((r for r in reais if r.lift > 0), key=lambda r: -r.lift)[:3]
    negativos = sorted((r for r in reais if r.lift < 0), key=lambda r: r.lift)[:1]
    if not positivos and not negativos:
        return '<p class="ic">Nenhum efeito deu pra afirmar com 95% de confiança.</p>'
    cartoes = []
    for i, r in enumerate(positivos + negativos):
        classe = "destaque neg" if r.lift < 0 else "destaque"
        cartoes.append(
            f'<div class="{classe} entra" style="--i:{i}">'
            f'<span class="valor">{_pct(r.lift)}</span>'
            f'<span class="nome">{escape(r.tag)}: {escape(r.value)}</span>'
            f'<span class="ic">intervalo de {_pct(r.low)} a {_pct(r.high)}</span>'
            "</div>"
        )
    return f'<div class="destaques">{"".join(cartoes)}</div>'


def _galeria(images: list[str]) -> str:
    """Galeria dos criativos, com o tipo de cada peça (estático, GIF ou vídeo)."""
    pecas = []
    for i, src in enumerate(images):
        tipo = media_type(src)
        if tipo == "vídeo":
            midia = (
                f'<video src="{escape(src)}" muted loop autoplay playsinline '
                f'aria-label="criativo em vídeo"></video>'
            )
        else:
            midia = f'<img src="{escape(src)}" alt="criativo {escape(tipo)}">'
        pecas.append(
            f'<figure class="peca entra" data-tipo="{tipo}" style="--i:{i}">'
            f"{midia}<figcaption>{tipo}</figcaption></figure>"
        )
    return f'<div class="galeria">{"".join(pecas)}</div>'


def _chips_de_tipo(images: list[str]) -> str:
    """Quantos criativos de cada tipo aparecem na galeria."""
    contagem: dict[str, int] = {}
    for src in images:
        tipo = media_type(src)
        contagem[tipo] = contagem.get(tipo, 0) + 1
    return "".join(
        f'<span class="chip">{n} {tipo}{"s" if n > 1 and tipo != "GIF" else ""}</span>'
        for tipo, n in contagem.items()
    )


def build_report(
    intervals: list[Interval],
    specs: list[CreativeSpec],
    rows: list[PerformanceRow],
    images: list[str] | None = None,
    theme: Theme = THEMES[TEMA_PADRAO],
) -> str:
    """Monta o HTML completo do relatório."""
    images = images or []
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
        f'<div class="kpi entra" style="--i:{i}"><b>{v}</b><span>{t}</span></div>'
        for i, (v, t) in enumerate(kpis)
    )

    linhas = "".join(
        f"<tr><td>{escape(r.tag)}</td><td>{escape(r.value)}</td>"
        f'<td class="num">{_pct(r.lift)}</td>'
        f'<td class="num">{_pct(r.low)} a {_pct(r.high)}</td>'
        f'<td><span class="selo {"sim" if r.significant else "nao"}">'
        f"{'sim' if r.significant else 'não'}</span></td></tr>"
        for r in sorted(intervals, key=lambda r: r.lift, reverse=True)
    )

    galeria = ""
    if images:
        galeria = (
            '<section class="secao"><header><h2>Criativos analisados</h2>'
            "<p>Cada peça mostra o tipo: estático, GIF ou vídeo.</p></header>"
            f"{_galeria(images)}</section>"
        )

    fonte = f'<link rel="stylesheet" href="{theme.font_url}">' if theme.font_url else ""
    t = theme

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>adlens · relatório de criativos</title>{fonte}
<style>{_vars(t)}{_ESTILO}</style></head>
<body>
<header class="hero">
<svg class="lente" viewBox="0 0 520 520" aria-hidden="true">
<circle class="anel1" cx="260" cy="260" r="240" stroke-width="2"/>
<circle class="anel2" cx="260" cy="260" r="180" stroke-width="10"/>
<circle class="anel3" cx="260" cy="260" r="120" stroke-width="2"/>
<circle class="anel1" cx="260" cy="260" r="70" stroke-width="2"/>
<circle class="foco" cx="260" cy="260" r="14"/>
</svg>
<div class="hero-in">
<div class="marca entra"><i></i>adlens</div>
<h1 class="entra" style="--i:1">O que faz um criativo <em>performar</em></h1>
<p class="entra" style="--i:2">Quanto cada característica muda o CTR, e o quanto dá
pra confiar em cada resposta.</p>
<div class="chips entra" style="--i:3"><span class="chip">intervalo de 95%</span>
{_chips_de_tipo(images)}</div>
</div>
</header>
<main>
<div class="kpis">{kpis_html}</div>

<section class="secao"><header><h2>Em destaque</h2>
<p>Os maiores efeitos que dá pra afirmar com 95% de confiança.</p></header>
{_destaques(intervals)}</section>

<section class="secao"><header><h2>Lift de cada etiqueta</h2>
<p>Barra = quanto o CTR muda com a característica. Linha = intervalo de 95%.</p>
</header>
<div class="cartao">{lift_chart(intervals, t)}
<div class="legenda"><span><i style="background:{t.positive}"></i>aumenta o CTR</span>
<span><i style="background:{t.negative}"></i>diminui o CTR</span>
<span><i style="background:{t.neutral}"></i>não dá pra afirmar</span></div></div>
</section>

<section class="secao"><header><h2>Tabela completa</h2></header>
<div class="cartao rolagem"><table><thead><tr><th>Etiqueta</th><th>Valor</th>
<th>Lift</th><th>Intervalo de 95%</th><th>Efeito real?</th></tr></thead>
<tbody>{linhas}</tbody></table></div></section>

{galeria}

<section class="secao"><header><h2>Como ler</h2></header>
<div class="como">
<div><b>Lift</b><p>Quanto o CTR muda com a característica, com todo o resto igual
(mesmas outras etiquetas, mesmo país). +15% = CTR 15% maior.</p></div>
<div><b>Intervalo de 95%</b><p>A faixa onde o efeito real provavelmente está.
Se cruza o zero, pode ser ruído.</p></div>
<div><b>Efeito real?</b><p>“Sim” só com prova forte: como várias etiquetas são
testadas juntas, a exigência é maior que a do intervalo sozinho.</p></div>
</div></section>
</main>
<footer>Gerado pelo adlens</footer>
<script>{_JS}</script>
</body></html>
"""


def save_report(html: str, path: Path) -> Path:
    """Salva o relatório num arquivo .html."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
