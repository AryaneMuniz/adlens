"""Testes do servidor MCP."""

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from adlens import server
from adlens.cli import main as cli
from adlens.server import (
    efeito_das_caracteristicas,
    gerar_relatorio,
    mcp,
    resumo_dos_dados,
)
from adlens.storage import load_specs


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
    with pytest.raises(ToolError):
        resumo_dos_dados(pasta="../..")


def test_efeito_diz_com_o_que_compara(projeto):
    efeitos = {
        (e["etiqueta"], e["valor"]): e for e in efeito_das_caracteristicas(sorteios=50)
    }
    assert efeitos[("rosto", "sim")]["referencia"] == "não"
    assert efeitos[("cor", "vermelho")]["referencia"] == "azul"
    assert efeitos[("formato", "vertical")]["referencia"] == "quadrado"


@pytest.mark.parametrize("sorteios", [0, 10, 5000])
def test_sorteios_fora_do_limite_da_erro(projeto, sorteios):
    with pytest.raises(ToolError, match="entre 50 e 2000"):
        efeito_das_caracteristicas(sorteios=sorteios)


def test_efeito_traz_ctrs_e_tamanho_do_grupo(projeto):
    efeitos = {
        (e["etiqueta"], e["valor"]): e for e in efeito_das_caracteristicas(sorteios=50)
    }
    rosto = efeitos[("rosto", "sim")]
    specs = load_specs(projeto / "data" / "criativos.csv")
    assert rosto["criativos"] == sum(s.has_face for s in specs)
    # O lift é exatamente a conta entre os dois CTRs
    lift = rosto["ctr_grupo"] / rosto["ctr_referencia"] - 1
    assert lift == pytest.approx(rosto["lift"], abs=0.001)


def test_pasta_sem_dados_explica_o_motivo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ToolError, match="adlens gerar"):
        asyncio.run(mcp.call_tool("resumo_dos_dados", {"pasta": "data"}))


def test_ferramentas_de_consulta_sao_somente_leitura():
    marcas = {t.name: t.annotations for t in asyncio.run(mcp.list_tools())}
    assert marcas["resumo_dos_dados"].read_only_hint is True
    assert marcas["efeito_das_caracteristicas"].read_only_hint is True
    assert marcas["gerar_relatorio"].read_only_hint is False
    assert marcas["gerar_relatorio"].destructive_hint is False


def test_cache_nao_refaz_a_analise_sem_os_dados_mudarem(projeto, monkeypatch):
    chamadas = []
    original = server.bootstrap_lifts

    def contando(*args, **kwargs):
        chamadas.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(server, "bootstrap_lifts", contando)
    server._cache.clear()
    primeira = efeito_das_caracteristicas(sorteios=50)
    segunda = efeito_das_caracteristicas(sorteios=50)
    assert primeira == segunda
    assert len(chamadas) == 1

    # Dados novos: a análise tem de ser refeita
    cli(["gerar", "--n", "200", "--seed", "7", "--pasta", "data"])
    efeito_das_caracteristicas(sorteios=50)
    assert len(chamadas) == 2
