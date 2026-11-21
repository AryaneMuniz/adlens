"""Testes de salvar e ler os CSVs."""

import csv

import pytest

from adlens.media import save_media, simulate_media
from adlens.performance import PerformanceRow, save_csv, simulate_performance
from adlens.storage import (
    load_dataset,
    load_performance,
    load_specs,
    parse_bool,
    save_specs,
    validate_performance,
)
from adlens.synthetic import generate_specs


def test_fichas_vao_e_voltam_iguais(tmp_path):
    specs = generate_specs(n=25, seed=4)
    caminho = save_specs(specs, tmp_path / "criativos.csv")
    assert load_specs(caminho) == specs


def test_performance_vai_e_volta_igual(tmp_path):
    linhas = simulate_performance(generate_specs(n=25, seed=4), seed=4)
    caminho = save_csv(linhas, tmp_path / "performance.csv")
    assert load_performance(caminho) == linhas


def test_load_dataset_usa_o_gabarito_se_nao_houver_etiquetas(tmp_path):
    specs = generate_specs(n=10, seed=4)
    save_specs(specs, tmp_path / "criativos.csv")
    save_csv(simulate_performance(specs, seed=4), tmp_path / "performance.csv")
    lidas, linhas, fonte = load_dataset(tmp_path)
    assert (lidas, len(linhas), fonte) == (specs, 10, "criativos.csv")


def test_load_dataset_sem_arquivos_da_erro_claro(tmp_path):
    with pytest.raises(FileNotFoundError, match="adlens gerar"):
        load_dataset(tmp_path)


def test_load_dataset_prefere_a_midia_diaria(tmp_path):
    specs = generate_specs(n=15, seed=6)
    save_specs(specs, tmp_path / "criativos.csv")
    save_media(simulate_media(specs, seed=6), tmp_path / "midia_diaria.csv")
    _, linhas, _ = load_dataset(tmp_path)
    assert linhas == simulate_performance(specs, seed=6)


# ---------- validação da entrada ----------

FICHA = [
    "creative_id",
    "has_face",
    "has_product",
    "has_cta",
    "dominant_color",
    "format",
]
PERF = ["creative_id", "impressions", "clicks", "spend"]


def _csv(caminho, linhas):
    """Grava um CSV pequeno (a primeira linha é o cabeçalho)."""
    with caminho.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(linhas)
    return caminho


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("True", True), ("true", True), ("1", True), (" sim ", True),
     ("False", False), ("false", False), ("0", False), ("", False)],
)  # fmt: skip
def test_sim_nao_aceita_os_jeitos_comuns(texto, esperado):
    assert parse_bool(texto) is esperado


def test_sim_nao_invalido_da_erro():
    with pytest.raises(ValueError, match="talvez"):
        parse_bool("talvez")


def test_cor_e_formato_ignoram_maiusculas(tmp_path):
    linha = ["CR1", "true", "false", "true", " Vermelho", "VERTICAL"]
    ficha = load_specs(_csv(tmp_path / "c.csv", [FICHA, linha]))[0]
    assert (ficha.dominant_color, ficha.format) == ("vermelho", "vertical")


def test_criativo_repetido_da_erro(tmp_path):
    linha = ["CR1", "true", "false", "true", "azul", "quadrado"]
    with pytest.raises(ValueError, match="repetido"):
        load_specs(_csv(tmp_path / "c.csv", [FICHA, linha, linha]))


def test_performance_repetida_da_erro(tmp_path):
    linhas = [PERF, ["CR1", "100", "5", "1.0"], ["CR1", "200", "9", "2.0"]]
    with pytest.raises(ValueError, match="repetido"):
        load_performance(_csv(tmp_path / "p.csv", linhas))


@pytest.mark.parametrize(
    ("impressoes", "cliques", "gasto", "mensagem"),
    [(100, 500, 1.0, "mais cliques"), (-10, 0, 1.0, "negativo"),
     (100, 5, -1.0, "negativo")],
)  # fmt: skip
def test_performance_impossivel_da_erro(impressoes, cliques, gasto, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        validate_performance([PerformanceRow("CR1", impressoes, cliques, gasto)])


def test_criativo_sem_performance_da_erro_claro(tmp_path):
    _csv(
        tmp_path / "criativos.csv",
        [
            FICHA,
            ["CR1", "true", "false", "true", "azul", "quadrado"],
            ["CR2", "false", "true", "false", "azul", "quadrado"],
        ],
    )
    _csv(tmp_path / "performance.csv", [PERF, ["CR1", "100", "5", "1.0"]])
    with pytest.raises(ValueError, match="CR2"):
        load_dataset(tmp_path)
