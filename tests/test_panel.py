"""Testes da página do Hub: ela tem que funcionar só com o contrato."""

import pytest

from adlens.cli import main as cli
from adlens.panel import build_panel, latest_run, read_contract, to_intervals


@pytest.fixture(scope="module")
def export(tmp_path_factory):
    """Uma pasta com SÓ os arquivos exportados (sem os dados brutos)."""
    dados = tmp_path_factory.mktemp("dados")
    saida = tmp_path_factory.mktemp("export")
    cli(["gerar", "--n", "300", "--pasta", str(dados)])
    cli(["exportar", "--pasta", str(dados), "--saida", str(saida), "--boot", "20"])
    return saida


def test_le_as_duas_tabelas_do_contrato(export):
    criativos, efeitos = read_contract(export)
    assert len(criativos) == 300
    assert len(efeitos) == 9


def test_sem_exportar_avisa_o_que_fazer(tmp_path):
    with pytest.raises(FileNotFoundError, match="adlens exportar"):
        read_contract(tmp_path)


def test_tabela_fora_do_contrato_e_recusada(export, tmp_path):
    # Copia as tabelas, mas renomeia a coluna "lift" para "efeito"
    for nome in ("adlens_criativos.csv", "adlens_efeitos.csv"):
        texto = (export / nome).read_text(encoding="utf-8")
        (tmp_path / nome).write_text(texto.replace(",lift,", ",efeito,"), "utf-8")
    with pytest.raises(ValueError, match="fora do contrato"):
        read_contract(tmp_path)


def test_mostra_so_a_execucao_mais_recente():
    linhas = [{"run_id": "20261101T000000Z"}, {"run_id": "20261120T000000Z"}]
    assert latest_run(linhas) == [{"run_id": "20261120T000000Z"}]


def test_painel_tem_filtros_e_uma_barra_por_efeito(export):
    criativos, efeitos = read_contract(export)
    html = build_panel(criativos, efeitos)
    assert html.count("<rect") == len(efeitos)
    for pais in {c["country"] for c in criativos}:
        assert f'<option value="{pais}">' in html


def test_dados_nao_quebram_a_pagina(export):
    criativos, efeitos = read_contract(export)
    criativos[0]["ad_name"] = "</script><b>oi</b>"
    html = build_panel(criativos, efeitos)
    assert "</script><b>oi</b>" not in html


def test_comando_painel(export, tmp_path):
    saida = tmp_path / "painel.html"
    codigo = cli(["painel", "--pasta", str(export), "--saida", str(saida)])
    assert codigo == 0
    assert "adlens · painel de criativos" in saida.read_text(encoding="utf-8")


def test_efeito_real_vem_pronto_do_contrato():
    # Intervalo inteiro acima do zero, mas o contrato diz "não" (a correção
    # para muitas etiquetas foi mais exigente): a página obedece o contrato
    linha = {
        "tag": "cor",
        "value": "verde",
        "lift": "0.02",
        "ci_low": "0.001",
        "ci_high": "0.04",
        "significant": "false",
    }
    assert not to_intervals([linha])[0].significant


def test_painel_usa_a_identidade_do_adlens_e_rola_no_celular(export):
    criativos, efeitos = read_contract(export)
    html = build_panel(criativos, efeitos)
    assert "fonts.googleapis.com" in html  # fonte do tema adlens
    assert ".rolagem table{min-width:560px}" in html
    assert 'class="grafico-rola"' in html
    assert "'R$ '" in html  # investimento com moeda
