"""Testes do relatório HTML."""

import pytest

from adlens.confidence import LiftInterval, bootstrap_lifts
from adlens.performance import simulate_performance
from adlens.report import build_report, lift_chart, media_type, save_report
from adlens.synthetic import generate_specs


def _dados(n=200):
    specs = generate_specs(n=n, seed=5)
    rows = simulate_performance(specs, seed=5)
    return specs, rows, bootstrap_lifts(specs, rows, n_boot=30, seed=5)


def test_relatorio_tem_titulo_e_uma_linha_por_etiqueta():
    specs, rows, intervalos = _dados()
    html = build_report(intervalos, specs, rows)
    assert "adlens · relatório de criativos" in html
    assert html.count("<tr><td>") == len(intervalos)


def test_relatorio_mostra_quantos_criativos():
    specs, rows, intervalos = _dados(n=200)
    assert "<b>200</b><span>criativos</span>" in build_report(intervalos, specs, rows)


def test_grafico_tem_uma_barra_por_etiqueta():
    _, _, intervalos = _dados()
    assert lift_chart(intervalos).count("<rect") == len(intervalos)


def test_efeito_nao_significativo_fica_cinza():
    falso = LiftInterval("cor", "verde", 0.01, -0.02, 0.03)
    assert 'fill="#bdb3b5"' in lift_chart([falso])


def test_texto_e_escapado_para_nao_quebrar_o_html():
    perigoso = LiftInterval("<script>", "x", 0.1, 0.05, 0.15)
    html = lift_chart([perigoso])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_galeria_aparece_quando_ha_imagens():
    specs, rows, intervalos = _dados()
    html = build_report(intervalos, specs, rows, images=["imagens/CR0001.png"])
    assert 'src="imagens/CR0001.png"' in html


def test_salva_o_arquivo(tmp_path):
    caminho = save_report("<html></html>", tmp_path / "rel" / "relatorio.html")
    assert caminho.read_text(encoding="utf-8") == "<html></html>"


@pytest.mark.parametrize(
    ("arquivo", "tipo"),
    [("a.png", "estático"), ("a.JPG", "estático"), ("a.gif", "GIF"),
     ("a.mp4", "vídeo"), ("a.webm", "vídeo")],
)  # fmt: skip
def test_reconhece_o_tipo_do_criativo(arquivo, tipo):
    assert media_type(arquivo) == tipo


def test_video_e_gif_entram_na_galeria():
    specs, rows, intervalos = _dados()
    html = build_report(intervalos, specs, rows, images=["pecas/a.mp4", "pecas/b.gif"])
    assert '<video src="pecas/a.mp4"' in html
    assert 'data-tipo="GIF"' in html


def test_destaque_mostra_o_maior_efeito():
    specs, rows, intervalos = _dados()
    maior = max((r for r in intervalos if r.significant), key=lambda r: r.lift)
    html = build_report(intervalos, specs, rows)
    assert f'<span class="nome">{maior.tag}: {maior.value}</span>' in html
