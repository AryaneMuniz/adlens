"""Testes dos etiquetadores."""

import pytest

from adlens.render import render_all
from adlens.synthetic import CreativeSpec, generate_specs
from adlens.tagging import FakeTagger, PixelTagger, accuracy_by_tag, tag_all


@pytest.fixture(scope="module")
def imagens(tmp_path_factory):
    """Desenha 60 criativos uma vez e reaproveita nos testes."""
    pasta = tmp_path_factory.mktemp("imagens")
    specs = generate_specs(n=60, seed=9)
    render_all(specs, pasta)
    return specs, pasta


def test_fake_sem_erro_devolve_o_gabarito(imagens):
    specs, pasta = imagens
    etiquetas = tag_all(FakeTagger(specs), [s.creative_id for s in specs], pasta)
    assert etiquetas == specs


def test_fake_com_erro_troca_algumas_etiquetas(imagens):
    specs, pasta = imagens
    ids = [s.creative_id for s in specs]
    etiquetas = tag_all(FakeTagger(specs, error_rate=0.3, seed=1), ids, pasta)
    diferentes = sum(e != s for e, s in zip(etiquetas, specs))
    assert 0 < diferentes < len(specs)


def test_fake_com_erro_e_reproduzivel(imagens):
    specs, pasta = imagens
    ids = [s.creative_id for s in specs]
    a = tag_all(FakeTagger(specs, error_rate=0.3, seed=1), ids, pasta)
    b = tag_all(FakeTagger(specs, error_rate=0.3, seed=1), ids, pasta)
    assert a == b


def test_pixel_tagger_acerta_tudo_nas_imagens_sinteticas(imagens):
    """O PixelTagger só olha a imagem e tem que bater 100% com o gabarito."""
    specs, pasta = imagens
    etiquetas = tag_all(PixelTagger(), [s.creative_id for s in specs], pasta)
    assert etiquetas == specs


def test_precisao_por_etiqueta():
    gabarito = [
        CreativeSpec("A", True, True, True, "azul", "quadrado"),
        CreativeSpec("B", False, True, False, "preto", "vertical"),
    ]
    etiquetas = [
        CreativeSpec("A", False, True, True, "azul", "quadrado"),  # errou o rosto
        CreativeSpec("B", False, True, False, "verde", "vertical"),  # errou a cor
    ]
    precisao = accuracy_by_tag(etiquetas, gabarito)
    assert precisao["has_face"] == 0.5
    assert precisao["dominant_color"] == 0.5
    assert precisao["has_product"] == 1.0
