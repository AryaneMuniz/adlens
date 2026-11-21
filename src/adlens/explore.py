"""Explorar os dados: distribuição das etiquetas, melhores criativos e comparação.

São as perguntas que vêm DEPOIS de "qual etiqueta puxa o CTR?":

- "Quantos criativos têm cada etiqueta?" (distribuição). Grupo pequeno =
  resultado frágil; etiqueta em 95% das peças não tem com quem comparar.
- "Quais são os melhores (ou piores) criativos?" (ranking). Com um mínimo de
  impressões: um criativo com 100 impressões e 5 cliques tem CTR de 5% por
  sorte, não por mérito.
- "O efeito do rosto é igual no Brasil e no México?" (comparação de dois
  recortes, com teste da diferença).

Tudo aqui é Python puro, sem saber de onde o dado veio nem quem vai mostrar
(MCP, linha de comando, página): o servidor só chama e formata.
"""

import math
from dataclasses import dataclass

from adlens.analysis import BINARY_TAGS, CATEGORICAL_TAGS
from adlens.confidence import Interval
from adlens.metrics import Metric
from adlens.performance import PerformanceRow
from adlens.regression import Z_95, benjamini_hochberg
from adlens.synthetic import CreativeSpec

# Como ordenar o ranking: nome que a pessoa usa -> valor de cada criativo
RANK_BY = {
    "ctr": lambda r: r.ctr,
    "impressoes": lambda r: r.impressions,
    "cliques": lambda r: r.clicks,
    "investimento": lambda r: r.spend,
    "cpm": lambda r: r.spend / r.impressions * 1000 if r.impressions else math.inf,
    # sem clique, o CPC é "infinito": nunca aparece como o mais barato
    "cpc": lambda r: r.spend / r.clicks if r.clicks else math.inf,
}
# Nessas, o melhor é o MENOR (custo); nas outras, o maior
LOWER_IS_BETTER = {"cpm", "cpc"}


def tags_of(spec: CreativeSpec) -> dict[str, str]:
    """As etiquetas de um criativo com os nomes amigáveis: {"rosto": "sim", ...}."""
    tags = {
        name: "sim" if getattr(spec, col) else "não"
        for col, name in BINARY_TAGS.items()
    }
    tags |= {name: getattr(spec, col) for col, (name, _) in CATEGORICAL_TAGS.items()}
    return tags


# --- distribuição -----------------------------------------------------------


@dataclass(frozen=True)
class TagShare:
    """Quantos criativos (e quanta mídia) têm um valor de etiqueta."""

    tag: str
    value: str
    creatives: int
    share_creatives: float  # 0.25 = 25% dos criativos
    impressions: int
    share_impressions: float  # 0.25 = 25% das impressões
    ctr: float


def tag_distribution(
    specs: list[CreativeSpec], rows: list[PerformanceRow]
) -> list[TagShare]:
    """Para cada etiqueta e valor: criativos, impressões, as fatias e o CTR.

    A fatia de criativos e a de impressões podem ser bem diferentes: se 10%
    das peças levam 40% das impressões, o investimento está concentrado nelas.
    """
    by_id = {r.creative_id: r for r in rows}
    total_creatives = len(specs)
    total_impressions = sum(by_id[s.creative_id].impressions for s in specs)
    grupos: dict[tuple[str, str], list[int]] = {}  # (tag, valor) -> [n, imp, cliques]
    for spec in specs:
        row = by_id[spec.creative_id]
        for tag, value in tags_of(spec).items():
            g = grupos.setdefault((tag, value), [0, 0, 0])
            g[0] += 1
            g[1] += row.impressions
            g[2] += row.clicks

    ordem = list(BINARY_TAGS.values()) + [n for n, _ in CATEGORICAL_TAGS.values()]
    return [
        TagShare(
            tag,
            value,
            creatives=n,
            share_creatives=n / total_creatives,
            impressions=imp,
            share_impressions=imp / total_impressions if total_impressions else 0.0,
            ctr=cli / imp if imp else 0.0,
        )
        for (tag, value), (n, imp, cli) in sorted(
            grupos.items(), key=lambda item: (ordem.index(item[0][0]), item[0][1])
        )
    ]


# --- valor bruto de cada grupo, em qualquer métrica -------------------------


@dataclass(frozen=True)
class GroupValue:
    """A métrica bruta de um grupo e a do grupo de referência (sem controle)."""

    tag: str
    value: str
    reference: str
    metric_value: float  # ex.: CPC de quem tem rosto
    metric_reference: float  # ex.: CPC de quem não tem
    creatives: int  # quantos criativos no grupo


def group_values(
    specs: list[CreativeSpec], rows: list[PerformanceRow], metric: Metric
) -> dict[tuple[str, str], GroupValue]:
    """A métrica de cada grupo (soma de cima / soma de baixo), com a referência.

    É o "lado bruto" da comparação, para mostrar junto do lift. Grupo sem a
    referência no recorte fica de fora.
    """
    by_id = {r.creative_id: r for r in rows}
    somas: dict[tuple[str, str], list[float]] = {}  # (tag, valor) -> [cima, baixo, n]
    for spec in specs:
        row = by_id[spec.creative_id]
        for tag, value in tags_of(spec).items():
            g = somas.setdefault((tag, value), [0.0, 0.0, 0])
            g[0] += getattr(row, metric.numerator)
            g[1] += getattr(row, metric.denominator)
            g[2] += 1

    referencias = {name: "não" for name in BINARY_TAGS.values()}
    referencias |= {name: ref for name, ref in CATEGORICAL_TAGS.values()}
    resultado = {}
    for (tag, value), (cima, baixo, n) in somas.items():
        referencia = referencias[tag]
        if value == referencia or (tag, referencia) not in somas:
            continue
        ref_cima, ref_baixo, _ = somas[(tag, referencia)]
        resultado[(tag, value)] = GroupValue(
            tag,
            value,
            referencia,
            metric.ratio(cima, baixo),
            metric.ratio(ref_cima, ref_baixo),
            int(n),
        )
    return resultado


# --- ranking ----------------------------------------------------------------


@dataclass(frozen=True)
class RankedCreative:
    """Um criativo no ranking, com as etiquetas e os números."""

    creative_id: str
    tags: dict[str, str]
    impressions: int
    clicks: int
    ctr: float
    spend: float

    @property
    def cpm(self) -> float:
        return self.spend / self.impressions * 1000 if self.impressions else 0.0

    @property
    def cpc(self) -> float:
        return self.spend / self.clicks if self.clicks else 0.0


def top_creatives(
    specs: list[CreativeSpec],
    rows: list[PerformanceRow],
    by: str = "ctr",
    n: int = 10,
    min_impressions: int = 1000,
    worst: bool = False,
) -> list[RankedCreative]:
    """Os N melhores (ou, com `worst`, os N piores) criativos por uma métrica.

    "Melhor" depende da métrica: no CTR é o maior; no CPM e no CPC é o menor
    (mais barato). Só entra quem tem pelo menos `min_impressions` impressões:
    com pouca entrega, o número é sorte. Empate desempata pelo creative_id
    (resultado sempre igual para os mesmos dados).
    """
    if by not in RANK_BY:
        raise ValueError(f"Ordenar por {by!r}? Use um de: {', '.join(RANK_BY)}")
    by_id = {r.creative_id: r for r in rows}
    valor = RANK_BY[by]
    maior_primeiro = (by not in LOWER_IS_BETTER) != worst
    candidatos = [
        (s, by_id[s.creative_id])
        for s in specs
        if by_id[s.creative_id].impressions >= min_impressions
    ]
    candidatos.sort(key=lambda par: par[0].creative_id)  # desempate estável
    candidatos.sort(key=lambda par: valor(par[1]), reverse=maior_primeiro)
    return [
        RankedCreative(
            s.creative_id, tags_of(s), r.impressions, r.clicks, r.ctr, r.spend
        )
        for s, r in candidatos[:n]
    ]


# --- comparação de dois recortes --------------------------------------------


@dataclass(frozen=True)
class Comparison:
    """O efeito de uma etiqueta em dois recortes e se a diferença é real."""

    tag: str
    value: str
    lift_a: float
    lift_b: float
    p_value: float  # chance de ver essa diferença se os efeitos fossem iguais
    p_adjusted: float  # o mesmo, corrigido para muitas etiquetas (BH)

    @property
    def different(self) -> bool:
        """Os efeitos são diferentes de verdade? Sim, se o p corrigido < 5%."""
        return self.p_adjusted < 0.05


def _log_and_se(effect: Interval) -> tuple[float, float]:
    """O efeito em log e o erro padrão, recuperado do intervalo de 95%.

    O intervalo é log(1+lift) ± 1,96 x erro padrão; então o erro padrão é a
    largura do intervalo (em log) dividida por 2 x 1,96.
    """
    centro = math.log1p(effect.lift)
    se = (math.log1p(effect.high) - math.log1p(effect.low)) / (2 * Z_95)
    return centro, se


def compare_effects(a: list[Interval], b: list[Interval]) -> list[Comparison]:
    """Compara o efeito de cada etiqueta entre dois recortes (A e B).

    Para cada etiqueta que aparece nos dois: a diferença em log dividida pelo
    erro padrão combinado vira um z; o z vira um p-valor; e os p-valores
    passam pela correção de Benjamini-Hochberg (comparar 9 etiquetas de uma
    vez é fazer 9 testes).

    É uma aproximação: supõe que os dois recortes são independentes. Vale bem
    para países ou plataformas diferentes (cada criativo está em um só). Para
    dois períodos, o mesmo criativo pode estar nos dois e a conta fica
    otimista.
    """
    em_b = {(e.tag, e.value): e for e in b}
    pares = [(ea, em_b[(ea.tag, ea.value)]) for ea in a if (ea.tag, ea.value) in em_b]
    p_values = []
    for ea, eb in pares:
        (la, sa), (lb, sb) = _log_and_se(ea), _log_and_se(eb)
        z = (la - lb) / math.sqrt(sa * sa + sb * sb) if sa or sb else 0.0
        p_values.append(math.erfc(abs(z) / math.sqrt(2)))
    ajustados = benjamini_hochberg(p_values) if p_values else []
    return [
        Comparison(ea.tag, ea.value, ea.lift, eb.lift, p, p_adj)
        for (ea, eb), p, p_adj in zip(pares, p_values, ajustados)
    ]
