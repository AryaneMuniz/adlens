"""Testes do hub (o site com abas publicado no GitHub Pages)."""

import json

import pytest

from adlens.cli import main as cli
from adlens.hub import ABAS, creatives_json, group_size, publish_hub
from adlens.performance import simulate_performance
from adlens.synthetic import generate_specs


@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    p = tmp_path_factory.mktemp("dados")
    cli(["gerar", "--n", "300", "--pasta", str(p), "--imagens"])
    return p


@pytest.fixture(scope="module")
def html(pasta, tmp_path_factory):
    saida = tmp_path_factory.mktemp("site")
    publish_hub(pasta, saida, boot=50)
    return (saida / "index.html").read_text(encoding="utf-8")


def test_hub_tem_todas_as_abas(html):
    for aba, _, _ in ABAS:
        assert f'id="aba-{aba}"' in html
        assert f'href="#{aba}"' in html


def test_filtro_tem_paises_e_plataformas(html):
    assert 'value="pais-BR"' in html
    assert 'value="plataforma-meta"' in html


def test_so_o_segmento_todos_comeca_visivel(html):
    assert 'data-seg="todos">' in html
    assert 'data-seg="pais-BR" hidden>' in html


def test_abas_futuras_avisam_que_sao_em_breve(html):
    assert "<small>em breve</small>" in html
    assert "Só para editores" in html


def test_tamanho_do_grupo():
    specs = generate_specs(n=80, seed=3)
    assert group_size(specs, "rosto", "sim") == sum(s.has_face for s in specs)
    vermelhos = sum(s.dominant_color == "vermelho" for s in specs)
    assert group_size(specs, "cor", "vermelho") == vermelhos


def test_dados_nao_quebram_a_pagina():
    specs = generate_specs(n=3, seed=1)
    rows = simulate_performance(specs, seed=1)
    dims = {specs[0].creative_id: {"platform": "</script>", "country": "BR"}}
    texto = creatives_json(specs, rows, dims)
    assert "</script>" not in texto
    assert json.loads(texto)[0]["plataforma"] == "</script>"


def test_comando_hub_gera_o_site_com_imagens(pasta, tmp_path):
    saida = tmp_path / "site"
    codigo = cli(["hub", "--pasta", str(pasta), "--saida", str(saida), "--boot", "50"])
    assert codigo == 0
    assert (saida / "index.html").exists()
    assert (saida / "imagens" / "CR0001.png").exists()


def test_hub_sem_dados_avisa_o_que_fazer(tmp_path, capsys):
    assert cli(["hub", "--pasta", str(tmp_path)]) == 1
    assert "adlens gerar" in capsys.readouterr().out
