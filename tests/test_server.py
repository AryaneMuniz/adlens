"""Testes do servidor MCP."""

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from adlens import server
from adlens.cli import main as cli
from adlens.server import (
    comparar,
    distribuicao_das_etiquetas,
    efeito_das_caracteristicas,
    gerar_relatorio,
    mcp,
    resumo_dos_dados,
    top_criativos,
)
from adlens.storage import load_specs


@pytest.fixture
def projeto(tmp_path, monkeypatch):
    """Uma pasta de projeto com dados gerados, usada como pasta atual."""
    monkeypatch.chdir(tmp_path)
    cli(["gerar", "--n", "300", "--pasta", "data"])
    return tmp_path


def test_servidor_oferece_as_seis_ferramentas():
    nomes = {t.name for t in asyncio.run(mcp.list_tools())}
    assert nomes == {
        "resumo_dos_dados",
        "efeito_das_caracteristicas",
        "gerar_relatorio",
        "distribuicao_das_etiquetas",
        "top_criativos",
        "comparar",
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


@pytest.mark.parametrize("metrica", ["ctr", "cpm", "cpc"])
def test_efeito_traz_valores_e_tamanho_do_grupo(projeto, metrica):
    efeitos = {
        (e["etiqueta"], e["valor"]): e
        for e in efeito_das_caracteristicas(
            metodo="simples", sorteios=50, metrica=metrica
        )
    }
    rosto = efeitos[("rosto", "sim")]
    specs = load_specs(projeto / "data" / "criativos.csv")
    assert rosto["criativos"] == sum(s.has_face for s in specs)
    assert rosto["metrica"] == metrica
    # No simples, o lift é exatamente a conta entre os dois valores brutos
    lift = rosto["valor_grupo"] / rosto["valor_referencia"] - 1
    assert lift == pytest.approx(rosto["lift"], abs=0.001)


def test_regressao_e_o_padrao_e_fica_mais_perto_do_gabarito(projeto):
    efeitos = {(e["etiqueta"], e["valor"]): e for e in efeito_das_caracteristicas()}
    rosto = efeitos[("rosto", "sim")]
    assert rosto["metodo"] == "regressao"
    # A conta bruta mistura o rosto com as outras etiquetas; a regressão isola
    bruto = rosto["valor_grupo"] / rosto["valor_referencia"] - 1
    assert abs(rosto["lift"] - 0.15) < abs(bruto - 0.15)


def test_no_cpc_cair_e_bom(projeto):
    efeitos = {
        (e["etiqueta"], e["valor"]): e
        for e in efeito_das_caracteristicas(metrica="cpc")
    }
    rosto = efeitos[("rosto", "sim")]
    assert rosto["lift"] < 0  # rosto traz mais clique pelo mesmo preço
    assert rosto["bom"] is True


def test_metrica_desconhecida_explica_as_opcoes(projeto):
    with pytest.raises(ToolError, match="ctr, cpm, cpc"):
        efeito_das_caracteristicas(metrica="roas")


def test_metodo_desconhecido_da_erro(projeto):
    with pytest.raises(ToolError, match="metodo"):
        efeito_das_caracteristicas(metodo="chute")


def test_pasta_sem_dados_explica_o_motivo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ToolError, match="adlens gerar"):
        asyncio.run(mcp.call_tool("resumo_dos_dados", {"pasta": "data"}))


def test_ferramentas_de_consulta_sao_somente_leitura():
    marcas = {t.name: t.annotations for t in asyncio.run(mcp.list_tools())}
    assert marcas["resumo_dos_dados"].read_only_hint is True
    assert marcas["efeito_das_caracteristicas"].read_only_hint is True
    for nova in ("distribuicao_das_etiquetas", "top_criativos", "comparar"):
        assert marcas[nova].read_only_hint is True
    assert marcas["gerar_relatorio"].read_only_hint is False
    assert marcas["gerar_relatorio"].destructive_hint is False


def test_cache_nao_refaz_a_analise_sem_os_dados_mudarem(projeto, monkeypatch):
    chamadas = []
    original = server.compute_effects

    def contando(*args, **kwargs):
        chamadas.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(server, "compute_effects", contando)
    server._cache.clear()
    primeira = efeito_das_caracteristicas(sorteios=50)
    segunda = efeito_das_caracteristicas(sorteios=50)
    assert primeira == segunda
    assert len(chamadas) == 1

    # Dados novos: a análise tem de ser refeita
    cli(["gerar", "--n", "200", "--seed", "7", "--pasta", "data"])
    efeito_das_caracteristicas(sorteios=50)
    assert len(chamadas) == 2


def test_resumo_lista_o_que_da_para_filtrar(projeto):
    resumo = resumo_dos_dados()
    assert resumo["recorte"] == "todos os dados"
    assert "BR" in resumo["disponivel"]["paises"]
    assert "meta" in resumo["disponivel"]["plataformas"]


def test_resumo_com_filtro_conta_so_o_recorte(projeto):
    total = resumo_dos_dados()["criativos"]
    so_br = resumo_dos_dados(pais="BR,MX")
    assert 0 < so_br["criativos"] < total
    assert so_br["recorte"] == "país BR, MX"


def test_efeito_com_filtro_traz_o_recorte(projeto):
    efeitos = efeito_das_caracteristicas(plataforma="meta,tiktok,google")
    assert efeitos
    assert {e["recorte"] for e in efeitos} == {"plataforma meta, tiktok, google"}


def test_filtro_errado_explica_para_o_agente(projeto):
    with pytest.raises(ToolError, match="AAAA-MM-DD"):
        efeito_das_caracteristicas(data_inicio="ontem")
    with pytest.raises(ToolError, match="Disponíveis"):
        resumo_dos_dados(pais="XX")


# --- ferramentas da Aula 29 (#33) -------------------------------------------


def test_distribuicao_conta_todos_os_criativos_em_cada_etiqueta(projeto):
    linhas = distribuicao_das_etiquetas()
    rosto = [linha for linha in linhas if linha["etiqueta"] == "rosto"]
    assert sum(linha["criativos"] for linha in rosto) == 300
    assert {linha["valor"] for linha in rosto} == {"sim", "não"}


def test_distribuicao_aceita_filtro(projeto):
    linhas = distribuicao_das_etiquetas(pais="BR,MX")
    rosto = [linha for linha in linhas if linha["etiqueta"] == "rosto"]
    assert 0 < sum(linha["criativos"] for linha in rosto) < 300
    assert linhas[0]["recorte"] == "país BR, MX"


def test_top_criativos_traz_etiquetas_e_vem_ordenado(projeto):
    ranking = top_criativos(quantidade=5)
    assert [r["posicao"] for r in ranking] == [1, 2, 3, 4, 5]
    ctrs = [r["ctr"] for r in ranking]
    assert ctrs == sorted(ctrs, reverse=True)
    assert set(ranking[0]["etiquetas"]) == {"rosto", "produto", "cta", "cor", "formato"}


def test_top_criativos_valida_os_parametros(projeto):
    with pytest.raises(ToolError, match="ordenar_por"):
        top_criativos(ordenar_por="roas")
    with pytest.raises(ToolError, match="entre 1 e 50"):
        top_criativos(quantidade=500)
    with pytest.raises(ToolError, match="Diminua o minimo_impressoes"):
        top_criativos(minimo_impressoes=10_000_000)


def test_comparar_paises_sem_diferenca_plantada_nao_acusa_diferenca(projeto):
    # No dado sintético, o efeito de cada etiqueta é o mesmo em todo país
    resultado = comparar(a_plataforma="meta,google", b_plataforma="tiktok,dv360")
    assert resultado["criativos_em_comum"] == 0
    assert "aviso" not in resultado
    assert resultado["etiquetas"]
    assert not any(e["diferente"] for e in resultado["etiquetas"])


def test_comparar_periodos_avisa_sobre_criativos_em_comum(projeto):
    resultado = comparar(a_data_fim="2026-10-15", b_data_inicio="2026-10-16")
    assert resultado["criativos_em_comum"] > 0
    assert "otimista" in resultado["aviso"]


def test_comparar_recortes_iguais_e_erro(projeto):
    with pytest.raises(ToolError, match="são iguais"):
        comparar(a_pais="BR", b_pais="br")


def test_top_criativos_por_cpc_vem_do_mais_barato(projeto):
    ranking = top_criativos(ordenar_por="cpc", quantidade=5)
    cpcs = [r["cpc"] for r in ranking]
    assert cpcs == sorted(cpcs)
    assert ranking[0]["cpm"] > 0


def test_erro_de_filtro_nao_culpa_os_dados(projeto):
    with pytest.raises(ToolError) as erro:
        resumo_dos_dados(pais="BRA")
    assert str(erro.value).startswith("Filtro inválido")
