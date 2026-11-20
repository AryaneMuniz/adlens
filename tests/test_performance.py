"""Testes da performance sintética com efeitos plantados."""

import csv
from dataclasses import replace

import pytest

from adlens.performance import (
    PlantedEffects,
    expected_ctr,
    save_csv,
    simulate_performance,
)
from adlens.synthetic import CreativeSpec, generate_specs

NEUTRO = CreativeSpec(
    creative_id="CR9999",
    has_face=False,
    has_product=False,
    has_cta=False,
    dominant_color="azul",
    format="quadrado",
)


def test_criativo_neutro_tem_o_ctr_base():
    efeitos = PlantedEffects()
    assert expected_ctr(NEUTRO, efeitos) == pytest.approx(efeitos.base_ctr)


def test_rosto_aumenta_o_ctr_em_15_por_cento():
    efeitos = PlantedEffects()
    com_rosto = replace(NEUTRO, has_face=True)
    razao = expected_ctr(com_rosto, efeitos) / expected_ctr(NEUTRO, efeitos)
    assert razao == pytest.approx(1.15)


def test_mesma_semente_gera_a_mesma_performance():
    specs = generate_specs(n=30, seed=1)
    assert simulate_performance(specs, seed=5) == simulate_performance(specs, seed=5)


def test_cliques_nunca_passam_das_impressoes():
    for linha in simulate_performance(generate_specs(n=200, seed=3), seed=3):
        assert 0 <= linha.clicks <= linha.impressions


def test_dado_simulado_carrega_o_efeito_plantado():
    """Com muitos criativos, o rosto tem que aparecer ~15% acima no CTR."""
    specs = generate_specs(n=3000, seed=11)
    linhas = simulate_performance(specs, seed=11)
    ficha = {s.creative_id: s for s in specs}

    def ctr_medio(com_rosto: bool) -> float:
        grupo = [r for r in linhas if ficha[r.creative_id].has_face == com_rosto]
        return sum(r.clicks for r in grupo) / sum(r.impressions for r in grupo)

    lift = ctr_medio(True) / ctr_medio(False) - 1
    assert lift == pytest.approx(0.15, abs=0.04)


def test_salva_csv_com_cabecalho(tmp_path):
    linhas = simulate_performance(generate_specs(n=5, seed=2), seed=2)
    caminho = save_csv(linhas, tmp_path / "perf.csv")
    with caminho.open(encoding="utf-8") as f:
        conteudo = list(csv.reader(f))
    assert conteudo[0] == ["creative_id", "impressions", "clicks", "spend"]
    assert len(conteudo) == 6
