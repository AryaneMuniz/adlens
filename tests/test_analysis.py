"""Testes da análise: ela tem que redescobrir os efeitos plantados."""

import pytest

from adlens.analysis import analyze, build_database
from adlens.performance import simulate_performance
from adlens.synthetic import generate_specs


@pytest.fixture(scope="module")
def resultados():
    """Roda a análise uma vez em 3.000 criativos e reaproveita nos testes."""
    specs = generate_specs(n=3000, seed=2026)
    con = build_database(specs, simulate_performance(specs, seed=2026))
    return {(r.tag, r.value): r for r in analyze(con)}


def test_banco_tem_as_duas_tabelas():
    specs = generate_specs(n=10, seed=1)
    con = build_database(specs, simulate_performance(specs, seed=1))
    assert con.execute("SELECT COUNT(*) FROM criativos").fetchone()[0] == 10
    assert con.execute("SELECT COUNT(*) FROM performance").fetchone()[0] == 10


# O gabarito plantado em PlantedEffects. A análise não vê esses números:
# ela só olha etiquetas e cliques, e tem que chegar perto deles.
GABARITO = [
    ("rosto", "sim", 0.15),
    ("produto", "sim", 0.05),
    ("cta", "sim", 0.10),
    ("cor", "vermelho", 0.08),
    ("cor", "preto", -0.06),
    ("formato", "vertical", 0.07),
    ("formato", "horizontal", -0.04),
]


@pytest.mark.parametrize(("tag", "valor", "efeito"), GABARITO)
def test_redescobre_o_efeito_plantado(resultados, tag, valor, efeito):
    assert resultados[(tag, valor)].lift == pytest.approx(efeito, abs=0.03)
