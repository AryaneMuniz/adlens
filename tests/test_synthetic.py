"""Testes do gerador de criativos sintéticos."""

from adlens.synthetic import CreativeSpec, generate_specs


def test_gera_a_quantidade_pedida():
    specs = generate_specs(n=50, seed=42)
    assert len(specs) == 50


def test_mesma_semente_gera_os_mesmos_criativos():
    assert generate_specs(n=20, seed=7) == generate_specs(n=20, seed=7)


def test_sementes_diferentes_geram_criativos_diferentes():
    assert generate_specs(n=20, seed=1) != generate_specs(n=20, seed=2)


def test_ids_sao_unicos_e_padronizados():
    specs = generate_specs(n=30, seed=42)
    ids = [s.creative_id for s in specs]
    assert len(set(ids)) == 30
    assert ids[0] == "CR0001"


def test_valores_estao_dentro_do_permitido():
    for s in generate_specs(n=100, seed=42):
        assert isinstance(s, CreativeSpec)
        assert s.dominant_color in CreativeSpec.COLORS
        assert s.format in CreativeSpec.FORMATS
