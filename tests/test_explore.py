"""Testes da exploração: distribuição, ranking e comparação de recortes."""

import pytest

from adlens.confidence import LiftInterval
from adlens.explore import compare_effects, tag_distribution, tags_of, top_creatives
from adlens.performance import PerformanceRow, simulate_performance
from adlens.synthetic import CreativeSpec, generate_specs


@pytest.fixture(scope="module")
def dados():
    specs = generate_specs(n=400, seed=9)
    return specs, simulate_performance(specs, seed=9)


def _spec(cid: str, face: bool = False) -> CreativeSpec:
    return CreativeSpec(cid, face, False, False, "azul", "quadrado")


# --- etiquetas de um criativo -----------------------------------------------


def test_tags_of_usa_os_nomes_amigaveis():
    spec = CreativeSpec("CR1", True, False, True, "vermelho", "vertical")
    assert tags_of(spec) == {
        "rosto": "sim",
        "produto": "não",
        "cta": "sim",
        "cor": "vermelho",
        "formato": "vertical",
    }


# --- distribuição -----------------------------------------------------------


def test_cada_etiqueta_soma_100_por_cento(dados):
    por_etiqueta: dict[str, float] = {}
    for d in tag_distribution(*dados):
        por_etiqueta[d.tag] = por_etiqueta.get(d.tag, 0) + d.share_creatives
    assert set(por_etiqueta) == {"rosto", "produto", "cta", "cor", "formato"}
    for soma in por_etiqueta.values():
        assert soma == pytest.approx(1.0)


def test_distribuicao_mostra_a_concentracao_de_midia():
    specs = [_spec("A", face=True), _spec("B"), _spec("C"), _spec("D")]
    rows = [
        PerformanceRow("A", 7000, 70, 1.0),  # 1 de 4 peças, 70% das impressões
        PerformanceRow("B", 1000, 10, 1.0),
        PerformanceRow("C", 1000, 10, 1.0),
        PerformanceRow("D", 1000, 10, 1.0),
    ]
    rosto = {d.value: d for d in tag_distribution(specs, rows) if d.tag == "rosto"}
    assert rosto["sim"].share_creatives == 0.25
    assert rosto["sim"].share_impressions == 0.7
    assert rosto["sim"].ctr == 0.01


# --- ranking ----------------------------------------------------------------


def test_ranking_por_ctr_vem_do_maior_para_o_menor(dados):
    ranking = top_creatives(*dados, n=5)
    assert len(ranking) == 5
    ctrs = [c.ctr for c in ranking]
    assert ctrs == sorted(ctrs, reverse=True)


def test_piores_vem_do_menor_para_o_maior(dados):
    ctrs = [c.ctr for c in top_creatives(*dados, n=5, worst=True)]
    assert ctrs == sorted(ctrs)


def test_minimo_de_impressoes_tira_o_ctr_de_sorte():
    specs = [_spec("SORTE"), _spec("BOM")]
    rows = [
        PerformanceRow("SORTE", 100, 10, 1.0),  # CTR 10% em 100 impressões
        PerformanceRow("BOM", 50_000, 1_000, 100.0),  # CTR 2% em 50 mil
    ]
    assert top_creatives(specs, rows, min_impressions=0)[0].creative_id == "SORTE"
    assert [c.creative_id for c in top_creatives(specs, rows)] == ["BOM"]


def test_ordenar_por_algo_que_nao_existe_e_erro(dados):
    with pytest.raises(ValueError, match="ctr, impressoes, cliques, investimento"):
        top_creatives(*dados, by="roas")


# --- comparação -------------------------------------------------------------


def test_efeitos_bem_diferentes_sao_marcados_como_diferentes():
    a = [LiftInterval("rosto", "sim", 0.30, 0.25, 0.35)]
    b = [LiftInterval("rosto", "sim", 0.00, -0.05, 0.05)]
    (c,) = compare_effects(a, b)
    assert c.lift_a == 0.30 and c.lift_b == 0.00
    assert c.different


def test_efeitos_parecidos_nao_sao_diferentes():
    a = [LiftInterval("rosto", "sim", 0.15, 0.05, 0.26)]
    b = [LiftInterval("rosto", "sim", 0.12, 0.02, 0.23)]
    assert not compare_effects(a, b)[0].different


def test_intervalo_largo_nao_prova_diferenca():
    # Mesma diferença de lift do primeiro teste, mas com MUITA incerteza
    a = [LiftInterval("rosto", "sim", 0.30, -0.20, 1.00)]
    b = [LiftInterval("rosto", "sim", 0.00, -0.40, 0.60)]
    assert not compare_effects(a, b)[0].different


def test_etiqueta_que_so_existe_num_recorte_fica_de_fora():
    a = [
        LiftInterval("rosto", "sim", 0.15, 0.10, 0.20),
        LiftInterval("cor", "verde", 0.05, 0.00, 0.10),
    ]
    b = [LiftInterval("rosto", "sim", 0.15, 0.10, 0.20)]
    assert [(c.tag, c.value) for c in compare_effects(a, b)] == [("rosto", "sim")]
