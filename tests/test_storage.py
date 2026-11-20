"""Testes de salvar e ler os CSVs."""

from adlens.performance import save_csv, simulate_performance
from adlens.storage import load_performance, load_specs, save_specs
from adlens.synthetic import generate_specs


def test_fichas_vao_e_voltam_iguais(tmp_path):
    specs = generate_specs(n=25, seed=4)
    caminho = save_specs(specs, tmp_path / "criativos.csv")
    assert load_specs(caminho) == specs


def test_performance_vai_e_volta_igual(tmp_path):
    linhas = simulate_performance(generate_specs(n=25, seed=4), seed=4)
    caminho = save_csv(linhas, tmp_path / "performance.csv")
    assert load_performance(caminho) == linhas
