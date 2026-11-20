"""Testes do intervalo de confiança por bootstrap."""

import pytest

from adlens.confidence import bootstrap_lifts
from adlens.performance import simulate_performance
from adlens.synthetic import generate_specs


@pytest.fixture(scope="module")
def intervalos():
    specs = generate_specs(n=3000, seed=7)
    rows = simulate_performance(specs, seed=7)
    return {(r.tag, r.value): r for r in bootstrap_lifts(specs, rows, seed=7)}


def test_intervalo_contem_a_estimativa(intervalos):
    for r in intervalos.values():
        assert r.low <= r.lift <= r.high


def test_intervalo_do_rosto_contem_o_valor_verdadeiro(intervalos):
    rosto = intervalos[("rosto", "sim")]
    assert rosto.low <= 0.15 <= rosto.high


def test_rosto_tem_efeito_real(intervalos):
    assert intervalos[("rosto", "sim")].significant


def test_verde_nao_tem_efeito_real(intervalos):
    """No gabarito, verde é igual a azul (0%): o intervalo tem que cruzar o zero."""
    assert not intervalos[("cor", "verde")].significant


def test_mesma_semente_gera_o_mesmo_intervalo():
    specs = generate_specs(n=200, seed=3)
    rows = simulate_performance(specs, seed=3)
    a = bootstrap_lifts(specs, rows, n_boot=50, seed=1)
    b = bootstrap_lifts(specs, rows, n_boot=50, seed=1)
    assert a == b
