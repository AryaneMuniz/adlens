"""Testes das armadilhas: provam que a análise SIMPLES erra nesses dados.

Estes testes "torcem pelo erro" de propósito: eles documentam onde o método
atual falha. Quando a regressão (#35) chegar, ela vai ganhar testes que
acertam nesses mesmos mundos, e a diferença fica registrada.
"""

import pytest

from adlens.realistic import (
    confounded,
    false_alarms,
    giant,
    noisy,
    simple_lift,
    simpson,
)


def test_confusao_rosto_parece_bom_sem_ser():
    mundo = confounded()
    assert mundo.truth["rosto"] == 0.0
    assert simple_lift(mundo, "rosto") > 0.08  # a análise simples vê efeito
    # Olhando só os criativos com CTA, o "efeito" do rosto some
    so_com_cta = simple_lift(mundo, "rosto", keep=lambda s, _: s.has_cta)
    assert so_com_cta == pytest.approx(0.0, abs=0.03)


def test_simpson_rosto_parece_ruim_sendo_bom():
    mundo = simpson()
    assert mundo.truth["rosto"] == 0.15
    assert simple_lift(mundo, "rosto") < -0.20  # o sinal sai INVERTIDO
    # Dentro de cada país, o efeito verdadeiro aparece
    for pais in ("BR", "MX"):
        dentro = simple_lift(mundo, "rosto", keep=lambda _, p, pais=pais: p == pais)
        assert dentro == pytest.approx(0.15, abs=0.05)


def test_peca_gigante_inventa_efeito():
    mundo = giant()
    assert mundo.truth["produto"] == 0.0
    assert simple_lift(mundo, "produto") > 0.25  # uma peça só puxa o grupo
    sem_gigante = simple_lift(
        mundo, "produto", keep=lambda s, _: s.creative_id != "CR0001"
    )
    assert sem_gigante == pytest.approx(0.0, abs=0.03)


def test_variacao_por_criativo_gera_alarme_falso():
    # Nenhuma etiqueta muda o CTR. Um método confiável erraria em ~1 de 20
    # análises; o simples erra bem mais, porque testa 9 etiquetas de uma vez
    analises = [false_alarms(noisy(seed=k), n_boot=100) for k in range(10)]
    com_alarme = sum(a > 0 for a in analises)
    assert com_alarme >= 2


def test_mundos_sao_reproduziveis():
    a, b = simpson(n=200, seed=3), simpson(n=200, seed=3)
    assert a.rows == b.rows and a.country == b.country
