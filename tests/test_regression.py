"""Testes da regressão: ela acerta onde a análise simples erra.

Os mesmos quatro mundos de `test_realistic.py`. Lá, os testes provam que a
análise simples erra; aqui, que a regressão acerta o gabarito.
"""

import pytest

from adlens.performance import simulate_performance
from adlens.realistic import confounded, giant, noisy, simpson
from adlens.regression import benjamini_hochberg, fit_effects
from adlens.synthetic import CreativeSpec, generate_specs


def _efeitos(mundo):
    """Os efeitos da regressão por etiqueta (só as de sim/não)."""
    resultado = fit_effects(mundo.specs, mundo.rows, mundo.country)
    return {e.tag: e for e in resultado if e.value == "sim"}


def test_confusao_rosto_volta_para_zero():
    efeitos = _efeitos(confounded())
    assert efeitos["rosto"].lift == pytest.approx(0.0, abs=0.01)
    assert not efeitos["rosto"].significant
    assert efeitos["cta"].lift == pytest.approx(0.20, abs=0.02)  # o CTA leva o mérito


def test_simpson_rosto_volta_a_ser_positivo():
    efeitos = _efeitos(simpson())
    assert efeitos["rosto"].lift == pytest.approx(0.15, abs=0.02)
    assert efeitos["rosto"].significant
    assert efeitos["rosto"].low > 0  # o intervalo inteiro do lado positivo


def test_peca_gigante_nao_manda_sozinha():
    efeitos = _efeitos(giant())
    assert efeitos["produto"].lift == pytest.approx(0.0, abs=0.03)
    assert not efeitos["produto"].significant


def test_variacao_por_criativo_quase_nao_gera_alarme():
    # A análise simples acusa efeito falso em várias análises (test_realistic);
    # a regressão, com a correção BH, em quase nenhuma
    analises = [noisy(seed=k) for k in range(20)]
    com_alarme = sum(
        any(e.significant for e in fit_effects(m.specs, m.rows, m.country))
        for m in analises
    )
    assert com_alarme <= 2


def test_dados_boazinhos_recupera_o_gabarito():
    specs = generate_specs(n=3000, seed=42)
    efeitos = {
        (e.tag, e.value): e for e in fit_effects(specs, simulate_performance(specs))
    }
    assert efeitos[("rosto", "sim")].lift == pytest.approx(0.15, abs=0.02)
    assert efeitos[("cor", "preto")].lift == pytest.approx(-0.06, abs=0.02)
    assert efeitos[("cor", "vermelho")].reference == "azul"
    assert not efeitos[("cor", "verde")].significant  # verde não faz nada


def test_pais_controla_mas_nao_vira_resultado():
    mundo = simpson()
    assert "país" not in {
        e.tag for e in fit_effects(mundo.specs, mundo.rows, mundo.country)
    }


def test_etiqueta_que_nao_varia_fica_de_fora():
    # Nos mundos da Aula 25 todo criativo é azul e quadrado: não há o que comparar
    tags = {e.tag for e in fit_effects(confounded().specs, confounded().rows)}
    assert tags == {"rosto", "produto", "cta"}


def test_etiquetas_sempre_juntas_dao_erro_claro():
    # Rosto e CTA aparecem sempre juntos: impossível separar um do outro
    specs = [
        CreativeSpec(
            f"CR{i:04d}", i % 2 == 0, i % 3 == 0, i % 2 == 0, "azul", "quadrado"
        )
        for i in range(1, 61)
    ]
    with pytest.raises(ValueError, match="andam sempre juntas"):
        fit_effects(specs, simulate_performance(specs))


def test_poucos_criativos_da_erro_claro():
    specs = generate_specs(n=5, seed=1)
    with pytest.raises(ValueError, match="Poucos criativos"):
        fit_effects(specs, simulate_performance(specs))


def test_benjamini_hochberg_conta_feita_a_mao():
    # m = 4 testes. Ordenados: 0,01 (x4/1) 0,02 (x4/2) 0,03 (x4/3) 0,50 (x4/4)
    # = 0,04  0,04  0,04  0,50 (e nenhum corrigido fica menor que o anterior)
    assert benjamini_hochberg([0.03, 0.50, 0.01, 0.02]) == pytest.approx(
        [0.04, 0.50, 0.04, 0.04]
    )


def test_benjamini_hochberg_nunca_diminui_o_p():
    pvalores = [0.001, 0.2, 0.04, 0.9, 0.03]
    for original, corrigido in zip(pvalores, benjamini_hochberg(pvalores)):
        assert corrigido >= original
