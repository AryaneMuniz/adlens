"""Testes do desenho dos criativos."""

from dataclasses import replace

from PIL import Image

from adlens.render import RGB, SIZES, render_all, render_creative
from adlens.synthetic import CreativeSpec, generate_specs

BASE = CreativeSpec(
    creative_id="CR9999",
    has_face=True,
    has_product=True,
    has_cta=True,
    dominant_color="azul",
    format="quadrado",
)


def _spec(**mudancas) -> CreativeSpec:
    """Uma ficha de exemplo, com o que o teste quiser mudar."""
    return replace(BASE, **mudancas)


def test_cria_o_arquivo_png(tmp_path):
    caminho = render_creative(_spec(), tmp_path / "cr.png")
    assert caminho.exists()


def test_tamanho_segue_o_formato(tmp_path):
    for formato, tamanho in SIZES.items():
        caminho = render_creative(_spec(format=formato), tmp_path / f"{formato}.png")
        assert Image.open(caminho).size == tamanho


def test_fundo_tem_a_cor_dominante(tmp_path):
    caminho = render_creative(_spec(dominant_color="vermelho"), tmp_path / "cr.png")
    with Image.open(caminho) as img:
        canto_inferior_direito = img.getpixel((img.width - 2, img.height - 2))
    assert canto_inferior_direito == RGB["vermelho"]


def test_gera_um_arquivo_por_ficha(tmp_path):
    specs = generate_specs(n=6, seed=1)
    arquivos = render_all(specs, tmp_path)
    assert [a.name for a in arquivos] == [f"{s.creative_id}.png" for s in specs]
