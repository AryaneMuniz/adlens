"""Desenha as imagens dos criativos sintéticos.

Cada ficha (CreativeSpec) vira um PNG: fundo na cor dominante e,
conforme a ficha, um rosto, um produto e um botão de CTA.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from adlens.synthetic import CreativeSpec, generate_specs

# Tamanho de cada formato em pixels (largura, altura)
SIZES: dict[str, tuple[int, int]] = {
    "quadrado": (540, 540),
    "vertical": (540, 960),
    "horizontal": (960, 540),
}

# Cor de fundo (R, G, B) de cada cor dominante
RGB: dict[str, tuple[int, int, int]] = {
    "vermelho": (220, 38, 38),
    "verde": (22, 163, 74),
    "azul": (37, 99, 235),
    "amarelo": (250, 204, 21),
    "preto": (24, 24, 27),
}

WHITE = (255, 255, 255)
DARK = (24, 24, 27)
SKIN = (241, 194, 160)
CAP = (120, 120, 128)


def _ink(background: tuple[int, int, int]) -> tuple[int, int, int]:
    """Escolhe texto escuro em fundo claro e texto branco em fundo escuro."""
    r, g, b = background
    return DARK if (r * 299 + g * 587 + b * 114) / 1000 > 160 else WHITE


def _draw_face(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=SKIN)
    eye = r // 7
    for dx in (-r // 3, r // 3):
        draw.ellipse(
            (cx + dx - eye, cy - r // 4 - eye, cx + dx + eye, cy - r // 4 + eye),
            fill=DARK,
        )
    draw.arc(
        (cx - r // 2, cy - r // 6, cx + r // 2, cy + r // 2),
        start=20,
        end=160,
        fill=DARK,
        width=max(3, r // 15),
    )


def _draw_product(draw: ImageDraw.ImageDraw, cx: int, cy: int, h: int) -> None:
    w = h // 2
    draw.rounded_rectangle(
        (cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2),
        radius=w // 4,
        fill=WHITE,
        outline=DARK,
        width=3,
    )
    draw.rectangle(
        (cx - w // 5, cy - h // 2 - h // 6, cx + w // 5, cy - h // 2), fill=CAP
    )
    draw.rectangle(
        (cx - w // 2 + 6, cy - h // 10, cx + w // 2 - 6, cy + h // 10),
        fill=(200, 200, 200),
    )


def render_creative(spec: CreativeSpec, path: Path) -> Path:
    """Desenha um criativo a partir da ficha e salva como PNG."""
    width, height = SIZES[spec.format]
    background = RGB[spec.dominant_color]
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    unit = min(width, height)

    # Título da "marca" no topo
    font = ImageFont.load_default(size=unit // 12)
    draw.text((unit // 20, unit // 20), "MARCA", fill=_ink(background), font=font)

    # Elementos opcionais, conforme a ficha
    if spec.has_face:
        _draw_face(draw, cx=width // 3, cy=height // 2, r=unit // 6)
    if spec.has_product:
        _draw_product(draw, cx=width * 2 // 3, cy=height // 2, h=unit // 3)
    if spec.has_cta:
        bw, bh = unit // 2, unit // 9
        x0, y0 = (width - bw) // 2, height - bh - unit // 12
        draw.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=bh // 2, fill=WHITE)
        cta_font = ImageFont.load_default(size=bh // 2)
        draw.text(
            (x0 + bw // 2, y0 + bh // 2),
            "COMPRE AGORA",
            fill=DARK,
            font=cta_font,
            anchor="mm",
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def render_all(specs: list[CreativeSpec], out_dir: Path) -> list[Path]:
    """Desenha todos os criativos numa pasta (um PNG por ficha)."""
    return [render_creative(s, out_dir / f"{s.creative_id}.png") for s in specs]


if __name__ == "__main__":
    pasta = Path("data/amostra")
    arquivos = render_all(generate_specs(n=12, seed=42), pasta)
    print(f"{len(arquivos)} criativos gerados em {pasta.resolve()}")
