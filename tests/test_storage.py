"""Testes de salvar e ler os CSVs."""

import pytest

from adlens.performance import save_csv, simulate_performance
from adlens.storage import load_dataset, load_performance, load_specs, save_specs
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
