"""Etiquetadores: quem "olha" o criativo e diz o que tem nele.

Todo etiquetador segue o mesmo contrato (a interface `Tagger`): recebe a
imagem e devolve as etiquetas. O resto do adlens só conhece esse contrato,
então dá pra trocar o etiquetador sem mexer em mais nada (o "D" do SOLID):

- FakeTagger: copia o gabarito, com erros de propósito se pedir. Para testes.
- PixelTagger: olha os pixels das imagens sintéticas do adlens. Sem custo.
- ClaudeTagger (em claude_tagger.py): usa a IA de visão do Claude.
"""

import random
from pathlib import Path
from typing import Protocol

from PIL import Image

from adlens.render import CAP, RGB, SKIN, WHITE
from adlens.synthetic import CreativeSpec


class Tagger(Protocol):
    """O contrato de todo etiquetador."""

    def tag(self, image_path: Path, creative_id: str) -> CreativeSpec:
        """Olha a imagem e devolve as etiquetas do criativo."""
        ...


class FakeTagger:
    """Etiquetador de mentira: devolve o gabarito, errando de propósito.

    `error_rate` simula uma IA imperfeita: com essa chance, cada etiqueta
    de sim/não sai trocada.
    """

    def __init__(
        self, answers: list[CreativeSpec], error_rate: float = 0.0, seed: int = 0
    ):
        self._answers = {s.creative_id: s for s in answers}
        self._error_rate = error_rate
        self._rng = random.Random(seed)

    def _maybe_flip(self, value: bool) -> bool:
        return not value if self._rng.random() < self._error_rate else value

    def tag(self, image_path: Path, creative_id: str) -> CreativeSpec:
        s = self._answers[creative_id]
        return CreativeSpec(
            creative_id=creative_id,
            has_face=self._maybe_flip(s.has_face),
            has_product=self._maybe_flip(s.has_product),
            has_cta=self._maybe_flip(s.has_cta),
            dominant_color=s.dominant_color,
            format=s.format,
        )


class PixelTagger:
    """Etiquetador por pixels, feito para as imagens sintéticas do adlens.

    Procura cores que só aparecem em cada elemento: a cor de pele (rosto),
    a cor da tampa (produto) e o branco na faixa de baixo (botão de CTA).
    """

    MIN_PIXELS = 50  # quantos pixels da cor contam como "tem o elemento"

    def tag(self, image_path: Path, creative_id: str) -> CreativeSpec:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            width, height = img.size
            colors = {rgb: n for n, rgb in img.getcolors(maxcolors=width * height)}
            bottom = img.crop((0, int(height * 0.78), width, height))
            bottom_colors = {
                rgb: n for n, rgb in bottom.getcolors(maxcolors=width * height)
            }
            corner = img.getpixel((width - 2, height - 2))

        return CreativeSpec(
            creative_id=creative_id,
            has_face=colors.get(SKIN, 0) >= self.MIN_PIXELS,
            has_product=colors.get(CAP, 0) >= self.MIN_PIXELS,
            has_cta=bottom_colors.get(WHITE, 0) >= self.MIN_PIXELS,
            dominant_color=_nearest_color(corner),
            format=format_of(width, height),
        )


def _nearest_color(rgb: tuple[int, int, int]) -> str:
    """O nome da cor da paleta mais parecida com o pixel."""
    return min(RGB, key=lambda name: sum((a - b) ** 2 for a, b in zip(RGB[name], rgb)))


def format_of(width: int, height: int) -> str:
    if width == height:
        return "quadrado"
    return "vertical" if height > width else "horizontal"


def tag_all(
    tagger: Tagger, creative_ids: list[str], image_dir: Path
) -> list[CreativeSpec]:
    """Etiqueta todos os criativos de uma pasta de imagens."""
    return [tagger.tag(image_dir / f"{cid}.png", cid) for cid in creative_ids]


TAG_FIELDS = ("has_face", "has_product", "has_cta", "dominant_color", "format")


def accuracy_by_tag(
    tags: list[CreativeSpec], answers: list[CreativeSpec]
) -> dict[str, float]:
    """A precisão de cada etiqueta: a fração de criativos igual ao gabarito."""
    by_id = {a.creative_id: a for a in answers}
    return {
        field: sum(
            getattr(t, field) == getattr(by_id[t.creative_id], field) for t in tags
        )
        / len(tags)
        for field in TAG_FIELDS
    }
