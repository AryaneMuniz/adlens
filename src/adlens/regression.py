"""Regressão: o efeito de cada etiqueta "com todo o resto igual".

A análise simples compara o CTR de quem tem a etiqueta com o de quem não tem.
Ela erra quando as etiquetas andam juntas (confusão), quando os países são
diferentes (Simpson), quando uma peça gigante domina a conta e quando testa
muitas etiquetas de uma vez (alarme falso). Ver `realistic.py`.

A regressão corrige as quatro coisas:

1. Olha TODAS as etiquetas ao mesmo tempo. O efeito do rosto é medido
   descontando o que o CTA já explica (resolve a confusão).
2. Inclui o país como "etiqueta de controle": compara rosto com sem-rosto
   DENTRO do mesmo país (resolve Simpson).
3. Cada criativo vale 1 voto, não importa quantas impressões teve
   (a peça gigante deixa de mandar sozinha).
4. Corrige os testes múltiplos com Benjamini-Hochberg: quanto mais etiquetas
   testadas, mais forte a prova exigida de cada uma (menos alarme falso).

Como funciona, em uma frase: para cada criativo, log(CTR) = base + soma dos
efeitos das etiquetas que ele tem + efeito do país dele. A regressão acha os
efeitos que deixam essa conta mais perto do CTR real de todos os criativos
(mínimos quadrados). Usamos log porque os efeitos multiplicam o CTR (+15% é
"vezes 1,15"); no log, multiplicar vira somar.
"""

import math
from collections import Counter
from dataclasses import dataclass

from adlens.analysis import BINARY_TAGS, CATEGORICAL_TAGS
from adlens.confidence import Interval, bootstrap_lifts
from adlens.performance import PerformanceRow, simulate_performance
from adlens.synthetic import CreativeSpec, generate_specs

Z_95 = 1.959964  # 95% da curva normal fica entre -1,96 e +1,96
METHODS = ("regressao", "simples")  # o padrão vem primeiro


@dataclass(frozen=True)
class Effect:
    """O efeito de uma etiqueta, isolado das outras, com intervalo de 95%."""

    tag: str  # ex.: "rosto"
    value: str  # ex.: "sim" ou "vermelho"
    reference: str  # ex.: "não" ou "azul"
    lift: float  # +0.15 = CTR 15% maior, com todo o resto igual
    low: float
    high: float
    p_value: float  # chance de ver um efeito desse tamanho se ele fosse zero
    p_adjusted: float  # o mesmo, corrigido para muitas etiquetas (BH)

    @property
    def significant(self) -> bool:
        """É efeito real? Sim, se o p corrigido ficou abaixo de 5%."""
        return self.p_adjusted < 0.05


@dataclass(frozen=True)
class _Column:
    """Uma coluna da regressão: vale 1 quando o criativo tem aquele valor."""

    tag: str
    value: str
    reference: str
    is_control: bool  # país: entra na conta, mas não vira resultado


def _value(spec: CreativeSpec, column: str) -> str:
    raw = getattr(spec, column)
    if isinstance(raw, bool):
        return "sim" if raw else "não"
    return raw


def _columns(specs: list[CreativeSpec], countries: list[str]) -> list[_Column]:
    """Monta as colunas que VARIAM nos dados (coluna constante não ensina nada)."""
    columns: list[_Column] = []
    for col, name in BINARY_TAGS.items():
        if len({getattr(s, col) for s in specs}) == 2:
            columns.append(_Column(name, "sim", "não", False))
    for col, (name, reference) in CATEGORICAL_TAGS.items():
        counts = Counter(getattr(s, col) for s in specs)
        if reference not in counts:  # sem a referência, usa a mais comum
            reference = counts.most_common(1)[0][0]
        for value in sorted(counts):
            if value != reference:
                columns.append(_Column(name, value, reference, False))
    counts = Counter(countries)
    reference = counts.most_common(1)[0][0]
    for value in sorted(counts):
        if value != reference:
            columns.append(_Column("país", value, reference, True))
    return columns


def _row_of(spec: CreativeSpec, country: str, columns: list[_Column]) -> list[float]:
    """A linha de um criativo: 1 (a base) e depois 1 ou 0 para cada coluna."""
    by_tag = {name: col for col, name in BINARY_TAGS.items()}
    by_tag |= {name: col for col, (name, _) in CATEGORICAL_TAGS.items()}
    row = [1.0]
    for c in columns:
        value = country if c.is_control else _value(spec, by_tag[c.tag])
        row.append(1.0 if value == c.value else 0.0)
    return row


def _invert(matrix: list[list[float]]) -> list[list[float]]:
    """Inverte uma matriz quadrada (eliminação de Gauss-Jordan)."""
    n = len(matrix)
    a = [
        row[:] + [1.0 if i == j else 0.0 for j in range(n)]
        for i, row in enumerate(matrix)
    ]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError(
                "Duas etiquetas andam sempre juntas: impossível separar o efeito "
                "de cada uma. Precisa de criativos que tenham uma sem a outra."
            )
        a[col], a[pivot] = a[pivot], a[col]
        p = a[col][col]
        a[col] = [x / p for x in a[col]]
        for r in range(n):
            if r != col and a[r][col]:
                f = a[r][col]
                a[r] = [x - f * y for x, y in zip(a[r], a[col])]
    return [row[n:] for row in a]


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Corrige os p-valores para muitos testes de uma vez (Benjamini-Hochberg).

    Ordena do menor para o maior; o k-ésimo menor é multiplicado por m/k
    (m = número de testes). Assim, o menor p precisa ser bem pequeno para
    continuar abaixo de 5%, e os seguintes precisam um pouco menos.
    Devolve na mesma ordem da entrada.
    """
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    smallest = 1.0
    for rank in range(m, 0, -1):  # do maior para o menor
        i = order[rank - 1]
        smallest = min(smallest, p_values[i] * m / rank)
        adjusted[i] = smallest
    return adjusted


def fit_effects(
    specs: list[CreativeSpec],
    rows: list[PerformanceRow],
    country: dict[str, str] | None = None,
) -> list[Effect]:
    """Efeito de cada etiqueta, isolado das outras e do país."""
    by_id = {r.creative_id: r for r in rows}
    countries = [(country or {}).get(s.creative_id, "?") for s in specs]
    columns = _columns(specs, countries)
    if len(specs) <= len(columns) + 1:
        raise ValueError(
            f"Poucos criativos ({len(specs)}) para {len(columns) + 1} efeitos."
        )

    x = [_row_of(s, c, columns) for s, c in zip(specs, countries)]
    # +0,5 clique e +1 impressão: evita log(0) num criativo sem nenhum clique
    y = [
        math.log(
            (by_id[s.creative_id].clicks + 0.5) / (by_id[s.creative_id].impressions + 1)
        )
        for s in specs
    ]

    # Mínimos quadrados: beta = (XᵀX)⁻¹ Xᵀy
    k = len(columns) + 1
    xtx = [[sum(r[i] * r[j] for r in x) for j in range(k)] for i in range(k)]
    xty = [sum(r[i] * yi for r, yi in zip(x, y)) for i in range(k)]
    inverse = _invert(xtx)
    beta = [sum(inverse[i][j] * xty[j] for j in range(k)) for i in range(k)]

    # O quanto os criativos "fogem" da conta = a incerteza de cada efeito
    residuals = [yi - sum(b * v for b, v in zip(beta, r)) for r, yi in zip(x, y)]
    variance = sum(e * e for e in residuals) / (len(specs) - k)

    found = []
    for i, c in enumerate(columns, start=1):
        if c.is_control:
            continue
        se = math.sqrt(variance * inverse[i][i])
        z = beta[i] / se
        p = math.erfc(abs(z) / math.sqrt(2))  # bicaudal, curva normal
        found.append((c, beta[i], se, p))

    adjusted = benjamini_hochberg([p for *_, p in found])
    return [
        Effect(
            c.tag,
            c.value,
            c.reference,
            lift=math.exp(b) - 1,
            low=math.exp(b - Z_95 * se) - 1,
            high=math.exp(b + Z_95 * se) - 1,
            p_value=p,
            p_adjusted=p_adj,
        )
        for (c, b, se, p), p_adj in zip(found, adjusted)
    ]


def compute_effects(
    specs: list[CreativeSpec],
    rows: list[PerformanceRow],
    country: dict[str, str] | None = None,
    method: str = "regressao",
    n_boot: int = 200,
) -> list[Interval]:
    """O efeito de cada etiqueta pelo método escolhido. Todas as telas usam esta.

    - "regressao" (padrão): isola cada etiqueta, controla o país, dá peso
      igual a cada criativo e corrige para muitos testes. `n_boot` não é usado.
    - "simples": a comparação de grupos com bootstrap (`n_boot` sorteios).
      Fica para comparar e para ensinar onde ela erra (ver realistic.py).
    """
    if method == "regressao":
        return list(fit_effects(specs, rows, country))
    if method == "simples":
        return list(bootstrap_lifts(specs, rows, n_boot=n_boot))
    raise ValueError(f"Método desconhecido: {method}. Use um de: {', '.join(METHODS)}")


if __name__ == "__main__":
    specs = generate_specs(n=3000, seed=42)
    rows = simulate_performance(specs, seed=42)
    print(f"{'etiqueta':<10}{'valor':<12}{'lift':>8}   intervalo de 95%     real?")
    for e in fit_effects(specs, rows):
        faixa = f"[{e.low:+.1%} a {e.high:+.1%}]"
        print(
            f"{e.tag:<10}{e.value:<12}{e.lift:>+8.1%}   {faixa:<20} "
            f"{'sim' if e.significant else 'não'}"
        )
