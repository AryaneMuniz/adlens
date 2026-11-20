"""Gerador de criativos sintéticos.

Cria "fichas" de criativos fictícios para a demonstração do adlens.
Usar sempre a mesma semente (seed) gera sempre os mesmos criativos,
o que torna os testes e a análise reproduzíveis.
"""

import random
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class CreativeSpec:
    """A ficha de um criativo: as características que a IA vai etiquetar."""

    COLORS: ClassVar[tuple[str, ...]] = (
        "vermelho",
        "verde",
        "azul",
        "amarelo",
        "preto",
    )
    FORMATS: ClassVar[tuple[str, ...]] = ("quadrado", "vertical", "horizontal")

    creative_id: str
    has_face: bool
    has_product: bool
    has_cta: bool
    dominant_color: str
    format: str


def generate_specs(n: int, seed: int = 42) -> list[CreativeSpec]:
    """Gera n fichas de criativos de forma reproduzível."""
    rng = random.Random(seed)
    return [
        CreativeSpec(
            creative_id=f"CR{i:04d}",
            has_face=rng.random() < 0.5,
            has_product=rng.random() < 0.6,
            has_cta=rng.random() < 0.7,
            dominant_color=rng.choice(CreativeSpec.COLORS),
            format=rng.choice(CreativeSpec.FORMATS),
        )
        for i in range(1, n + 1)
    ]
