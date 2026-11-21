"""Performance sintética com efeitos plantados.

A gente decide de propósito quanto cada característica do criativo
muda o CTR (os "efeitos plantados"). Depois, a análise do adlens tem que
redescobrir esses números sozinha: se acertar, o sistema funciona.
"""

import csv
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from adlens.synthetic import CreativeSpec, generate_specs


@dataclass(frozen=True)
class PlantedEffects:
    """O gabarito: quanto cada característica muda o CTR (em %)."""

    base_ctr: float = 0.012  # CTR de um criativo "neutro": 1,2%
    face: float = 0.15  # rosto: +15%
    product: float = 0.05  # produto: +5%
    cta: float = 0.10  # botão de CTA: +10%
    color: dict[str, float] = field(
        default_factory=lambda: {
            "vermelho": 0.08,
            "amarelo": 0.03,
            "verde": 0.0,
            "azul": 0.0,
            "preto": -0.06,
        }
    )
    format: dict[str, float] = field(
        default_factory=lambda: {"vertical": 0.07, "quadrado": 0.0, "horizontal": -0.04}
    )


@dataclass(frozen=True)
class PerformanceRow:
    """O resultado de um criativo na campanha."""

    creative_id: str
    impressions: int
    clicks: int
    spend: float

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0


def expected_ctr(spec: CreativeSpec, effects: PlantedEffects) -> float:
    """O CTR "verdadeiro" de um criativo, segundo o gabarito."""
    lift = 1.0
    if spec.has_face:
        lift *= 1 + effects.face
    if spec.has_product:
        lift *= 1 + effects.product
    if spec.has_cta:
        lift *= 1 + effects.cta
    lift *= 1 + effects.color[spec.dominant_color]
    lift *= 1 + effects.format[spec.format]
    return effects.base_ctr * lift


def sample_clicks(rng: random.Random, impressions: int, ctr: float) -> int:
    """Sorteia os cliques com o "acaso" de uma campanha de verdade."""
    mean = impressions * ctr
    std = math.sqrt(impressions * ctr * (1 - ctr))
    return max(0, min(impressions, round(rng.gauss(mean, std))))


def simulate_performance(
    specs: list[CreativeSpec],
    effects: PlantedEffects | None = None,
    seed: int = 42,
) -> list[PerformanceRow]:
    """Gera a performance de cada criativo de forma reproduzível."""
    effects = effects or PlantedEffects()
    rng = random.Random(seed)
    rows = []
    for spec in specs:
        impressions = rng.randint(20_000, 80_000)
        clicks = sample_clicks(rng, impressions, expected_ctr(spec, effects))
        cpm = rng.uniform(12.0, 18.0)  # custo por mil impressões, em R$
        spend = round(impressions / 1000 * cpm, 2)
        rows.append(PerformanceRow(spec.creative_id, impressions, clicks, spend))
    return rows


def save_csv(rows: list[PerformanceRow], path: Path) -> Path:
    """Salva a performance num CSV (abre no Excel)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["creative_id", "impressions", "clicks", "spend"])
        for r in rows:
            writer.writerow([r.creative_id, r.impressions, r.clicks, r.spend])
    return path


if __name__ == "__main__":
    specs = generate_specs(n=200, seed=42)
    caminho = save_csv(
        simulate_performance(specs, seed=42), Path("data/performance.csv")
    )
    print(f"Performance de {len(specs)} criativos salva em {caminho.resolve()}")
