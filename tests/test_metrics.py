"""Testes das métricas além do CTR (CPM e CPC)."""

import pytest

from adlens.cli import main as cli
from adlens.confidence import LiftInterval
from adlens.metrics import METRICS, get_metric, is_good
from adlens.performance import PerformanceRow, PlantedEffects, simulate_performance
from adlens.regression import compute_effects
from adlens.report import THEMES, _destaques, build_report, lift_chart
from adlens.synthetic import generate_specs

CTR, CPM, CPC = METRICS["ctr"], METRICS["cpm"], METRICS["cpc"]


@pytest.fixture(scope="module")
def dados():
    specs = generate_specs(n=3000, seed=42)
    return specs, simulate_performance(specs, seed=42)


# --- a métrica em si ---------------------------------------------------------


def test_as_tres_metricas_de_um_criativo():
    row = PerformanceRow("CR1", impressions=10_000, clicks=200, spend=150.0)
    assert CTR.of(row) == 0.02  # 200 / 10.000
    assert CPM.of(row) == 15.0  # R$ 150 por 10 mil = R$ 15 por mil
    assert CPC.of(row) == 0.75  # R$ 150 / 200 cliques


def test_criativo_sem_clique_nao_quebra_o_cpc():
    row = PerformanceRow("CR1", impressions=10_000, clicks=0, spend=150.0)
    assert CPC.of(row) == 0.0  # sem divisão por zero
    # +1 centavo em cima e +0,5 clique embaixo: 150,01 / 0,5 = 300,02 (finito)
    assert CPC.smoothed(row) == pytest.approx(300.02)


def test_nome_aceita_maiusculas_e_erro_lista_as_opcoes():
    assert get_metric(" CPC ") is CPC
    with pytest.raises(ValueError, match="ctr, cpm, cpc"):
        get_metric("roas")


def test_bom_depende_do_sentido():
    assert is_good(+0.10, CTR)  # CTR subiu: bom
    assert not is_good(+0.10, CPC)  # CPC subiu: ficou mais caro
    assert is_good(-0.10, CPM)  # CPM caiu: ficou mais barato


# --- a análise recupera o gabarito -------------------------------------------


def _efeitos(dados, metrica, metodo="regressao"):
    specs, rows = dados
    return {
        (e.tag, e.value): e
        for e in compute_effects(specs, rows, None, metodo, 100, metrica)
    }


def test_cpm_acha_so_o_formato(dados):
    gabarito = PlantedEffects().cpm_format
    efeitos = _efeitos(dados, CPM)
    assert efeitos[("formato", "vertical")].lift == pytest.approx(
        gabarito["vertical"], abs=0.02
    )
    assert efeitos[("formato", "horizontal")].lift == pytest.approx(
        gabarito["horizontal"], abs=0.02
    )
    # Nenhuma outra etiqueta mexe no CPM: nenhuma pode sair "real"
    falsos = [k for k, e in efeitos.items() if k[0] != "formato" and e.significant]
    assert falsos == []


@pytest.mark.parametrize("metodo", ["regressao", "simples"])
def test_cpc_e_o_espelho_do_ctr_com_o_cpm(dados, metodo):
    # CPC = CPM / (1000 x CTR): se o CTR sobe 15%, o CPC cai para 1/1,15
    efeitos = _efeitos(dados, CPC, metodo)
    assert efeitos[("rosto", "sim")].lift == pytest.approx(1 / 1.15 - 1, abs=0.02)
    # vertical: CTR +7% e CPM -10% -> CPC 0,90 / 1,07
    assert efeitos[("formato", "vertical")].lift == pytest.approx(
        0.90 / 1.07 - 1, abs=0.02
    )


def test_ctr_continua_igual_com_o_efeito_de_cpm_plantado(dados):
    # O CPM plantado mexe só no investimento: o CTR não pode mudar
    efeitos = _efeitos(dados, CTR)
    assert efeitos[("rosto", "sim")].lift == pytest.approx(0.15, abs=0.02)


# --- relatório: a cor diz "bom", não "positivo" ------------------------------


def test_no_cpc_barra_negativa_real_fica_verde():
    t = THEMES["neutro"]
    queda = [LiftInterval("rosto", "sim", -0.13, -0.15, -0.11)]
    assert t.positive in lift_chart(queda, t, CPC)
    assert t.negative not in lift_chart(queda, t, CPC)
    assert t.negative in lift_chart(queda, t, CTR)


def test_destaque_do_cpc_poe_a_queda_como_boa():
    efeitos = [
        LiftInterval("rosto", "sim", -0.13, -0.15, -0.11),
        LiftInterval("cor", "preto", 0.07, 0.04, 0.09),
    ]
    html = _destaques(efeitos, CPC)
    # A queda vem primeiro, como destaque bom; o aumento vem como ruim
    assert html.index("rosto") < html.index("preto")
    assert 'class="destaque neg entra" style="--i:1"' in html


def test_relatorio_do_cpc_fala_de_cpc_e_mostra_o_custo_medio(dados):
    specs, rows = dados
    efeitos = list(_efeitos((specs[:300], rows[:300]), CPC).values())
    html = build_report(efeitos, specs[:300], rows[:300], metric=CPC)
    assert "Quanto cada característica muda o CPC" in html
    assert "CPC: menor é melhor" in html
    assert "CPC médio" in html


# --- linha de comando --------------------------------------------------------


def test_analisar_com_metrica_mostra_o_sentido(tmp_path, capsys):
    cli(["gerar", "--n", "400", "--pasta", str(tmp_path)])
    capsys.readouterr()
    assert cli(["analisar", "--pasta", str(tmp_path), "--metrica", "cpc"]) == 0
    saida = capsys.readouterr().out
    assert "Métrica: CPC (menor é melhor)" in saida
    linha_rosto = next(
        linha for linha in saida.splitlines() if linha.startswith("rosto")
    )
    assert linha_rosto.endswith("melhora")
