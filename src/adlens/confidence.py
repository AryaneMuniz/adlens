"""Intervalo de confiança do lift, por bootstrap.

O lift calculado com os criativos que temos é uma estimativa: com outros
criativos, daria um número um pouco diferente. O bootstrap mede esse
"quanto poderia variar" sorteando, muitas vezes, novas amostras dos próprios
criativos (com reposição) e recalculando o lift em cada uma.
"""

import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from adlens.analysis import BINARY_TAGS, CATEGORICAL_TAGS
from adlens.metrics import METRICS, Metric
from adlens.performance import PerformanceRow, simulate_performance
from adlens.synthetic import CreativeSpec, generate_specs


class Interval(Protocol):
    """O que toda tela do adlens precisa de um resultado: o "molde" comum.

    O bootstrap (LiftInterval), a regressão (Effect) e a linha lida do
    contrato servem todos, porque têm esses campos. Quem desenha o gráfico
    não precisa saber qual conta gerou o número (o "L" e o "D" do SOLID).
    """

    @property
    def tag(self) -> str: ...
    @property
    def value(self) -> str: ...
    @property
    def lift(self) -> float: ...
    @property
    def low(self) -> float: ...
    @property
    def high(self) -> float: ...
    @property
    def significant(self) -> bool: ...


@dataclass(frozen=True)
class LiftInterval:
    """O lift de uma etiqueta com o intervalo de confiança de 95%."""

    tag: str
    value: str
    lift: float
    low: float
    high: float

    @property
    def significant(self) -> bool:
        """O efeito é real? Sim, se o intervalo inteiro fica de um lado do zero."""
        return self.low > 0 or self.high < 0


def _groups(spec: CreativeSpec) -> list[tuple[str, str]]:
    """Os grupos (etiqueta, valor) a que um criativo pertence."""
    groups = [
        (name, "sim" if getattr(spec, col) else "não")
        for col, name in BINARY_TAGS.items()
    ]
    groups += [
        (name, getattr(spec, col)) for col, (name, _) in CATEGORICAL_TAGS.items()
    ]
    return groups


def _lifts(
    sample: list[tuple[CreativeSpec, PerformanceRow]], metric: Metric = METRICS["ctr"]
) -> dict:
    """Calcula o lift de todas as etiquetas numa amostra de criativos.

    Soma o que vai em cima e o que vai embaixo da divisão da métrica por
    grupo (no CTR: cliques e impressões) e divide no fim.
    """
    clicks: dict = defaultdict(float)  # o de cima da divisão
    impressions: dict = defaultdict(float)  # o de baixo
    for spec, row in sample:
        for group in _groups(spec):
            clicks[group] += getattr(row, metric.numerator)
            impressions[group] += getattr(row, metric.denominator)

    def ctr(group):
        return clicks[group] / impressions[group] if impressions[group] else None

    lifts = {}
    for name in BINARY_TAGS.values():
        yes, no = ctr((name, "sim")), ctr((name, "não"))
        if yes and no:
            lifts[(name, "sim")] = yes / no - 1
    for name, reference in CATEGORICAL_TAGS.values():
        ref = ctr((name, reference))
        for tag, value in clicks:
            if tag == name and value != reference and ref and ctr((tag, value)):
                lifts[(tag, value)] = ctr((tag, value)) / ref - 1
    return lifts


def bootstrap_lifts(
    specs: list[CreativeSpec],
    rows: list[PerformanceRow],
    n_boot: int = 300,
    seed: int = 0,
    metric: Metric = METRICS["ctr"],
) -> list[LiftInterval]:
    """Lift de cada etiqueta com intervalo de confiança de 95% (bootstrap)."""
    by_id = {r.creative_id: r for r in rows}
    data = [(s, by_id[s.creative_id]) for s in specs]
    point = _lifts(data, metric)

    rng = random.Random(seed)
    samples: dict = defaultdict(list)
    for _ in range(n_boot):
        resample = rng.choices(data, k=len(data))  # sorteio com reposição
        for key, lift in _lifts(resample, metric).items():
            samples[key].append(lift)

    results = []
    for key, lift in point.items():
        values = sorted(samples[key])
        low = values[int(0.025 * (len(values) - 1))]
        high = values[int(0.975 * (len(values) - 1))]
        results.append(LiftInterval(key[0], key[1], lift, low, high))
    return sorted(results, key=lambda r: (r.tag, r.value))


if __name__ == "__main__":
    specs = generate_specs(n=3000, seed=42)
    rows = simulate_performance(specs, seed=42)
    print(f"{'etiqueta':<10}{'valor':<12}{'lift':>8}   intervalo de 95%     real?")
    for r in bootstrap_lifts(specs, rows):
        faixa = f"[{r.low:+.1%} a {r.high:+.1%}]"
        print(
            f"{r.tag:<10}{r.value:<12}{r.lift:>+8.1%}   {faixa:<20} "
            f"{'sim' if r.significant else 'não'}"
        )
