"""Testes do servidor MCP."""

import asyncio

import pytest

from adlens.cli import main as cli
from adlens.server import (
    efeito_das_caracteristicas,
    gerar_relatorio,
    mcp,
    resumo_dos_dados,
)


@pytest.fixture
def projeto(tmp_path, monkeypatch):
    """Uma pasta de projeto com dados gerados, usada como pasta atual."""
    monkeypatch.chdir(tmp_path)
    cli(["gerar", "--n", "300", "--pasta", "data"])
    return tmp_path


def test_servidor_oferece_as_tres_ferramentas():
    nomes = {t.name for t in asyncio.run(mcp.list_tools())}
    assert nomes == {
        "resumo_dos_dados",
        "efeito_das_caracteristicas",
        "gerar_relatorio",
    }


def test_resumo_conta_os_criativos(projeto):
    resumo = resumo_dos_dados()
    assert resumo["criativos"] == 300
    assert resumo["etiquetas_de"] == "criativos.csv"


def test_efeito_traz_rosto_significativo(projeto):
    efeitos = {
        (e["etiqueta"], e["valor"]): e for e in efeito_das_caracteristicas(sorteios=50)
    }
    assert efeitos[("rosto", "sim")]["significativo"]


def test_gerar_relatorio_cria_o_arquivo(projeto):
    caminho = gerar_relatorio()
    assert caminho.endswith("relatorio.html")
    assert (projeto / "data" / "relatorio.html").exists()


def test_pasta_fora_do_projeto_e_bloqueada(projeto):
    with pytest.raises(ValueError):
        resumo_dos_dados(pasta="../..")


def test_efeito_diz_com_o_que_compara(projeto):
    efeitos = {
        (e["etiqueta"], e["valor"]): e for e in efeito_das_caracteristicas(sorteios=20)
    }
    assert efeitos[("rosto", "sim")]["referencia"] == "não"
    assert efeitos[("cor", "vermelho")]["referencia"] == "azul"
    assert efeitos[("formato", "vertical")]["referencia"] == "quadrado"
