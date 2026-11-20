"""Testes da mídia diária no formato de plataforma."""

from adlens.media import (
    MEDIA_COLUMNS,
    _split,
    performance_from_media,
    save_media,
    simulate_media,
)
from adlens.performance import simulate_performance
from adlens.synthetic import generate_specs


def test_split_divide_sem_perder_nada():
    partes = _split(1000, [1.0, 2.0, 1.5])
    assert sum(partes) == 1000
    assert partes[1] > partes[0]


def test_uma_linha_por_anuncio_por_dia():
    linhas = simulate_media(generate_specs(n=20, seed=1), seed=1)
    chaves = [(r.ad_id, r.date) for r in linhas]
    assert len(chaves) == len(set(chaves))
    assert len(linhas) > 20


def test_somar_por_anuncio_bate_com_a_performance(tmp_path):
    """Somando os dias, cada anúncio tem que ter exatamente os totais de antes."""
    specs = generate_specs(n=40, seed=3)
    caminho = save_media(simulate_media(specs, seed=3), tmp_path / "midia.csv")
    assert performance_from_media(caminho) == simulate_performance(specs, seed=3)


def test_csv_tem_as_colunas_do_formato(tmp_path):
    caminho = save_media(
        simulate_media(generate_specs(n=3, seed=2), seed=2), tmp_path / "m.csv"
    )
    cabecalho = caminho.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert cabecalho == MEDIA_COLUMNS
    assert {"date", "campaign_name", "ad_id", "image_url", "impressions"} <= set(
        cabecalho
    )


def test_mesma_semente_gera_a_mesma_midia():
    specs = generate_specs(n=10, seed=5)
    assert simulate_media(specs, seed=5) == simulate_media(specs, seed=5)
