"""Testes do contrato de dados: o formato das tabelas não pode mudar sem querer."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adlens.cli import main as cli
from adlens.export import (
    CRIATIVOS_SCHEMA,
    EFEITOS_SCHEMA,
    build_exports,
    export_all,
    seguro_para_excel,
    write_table,
)

# O contrato combinado com quem consome as tabelas (Dataviz / BigQuery).
# Se alguém mudar uma coluna, este teste quebra e avisa.
CONTRATO_CRIATIVOS = [
    "run_id", "ad_id", "ad_name", "platform", "country", "campaign_name",
    "image_url", "has_face", "has_product", "has_cta", "dominant_color",
    "format", "impressions", "clicks", "investment", "ctr", "tag_source",
]  # fmt: skip
CONTRATO_EFEITOS = [
    "run_id", "run_at", "tag", "value", "reference", "lift",
    "ci_low", "ci_high", "significant", "creatives", "method",
]  # fmt: skip


@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    p = tmp_path_factory.mktemp("dados")
    cli(["gerar", "--n", "300", "--pasta", str(p)])
    return p


def _ler(caminho):
    with caminho.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_colunas_seguem_o_contrato():
    assert [c for c, _, _ in CRIATIVOS_SCHEMA] == CONTRATO_CRIATIVOS
    assert [c for c, _, _ in EFEITOS_SCHEMA] == CONTRATO_EFEITOS


def test_uma_linha_por_anuncio_e_uma_por_etiqueta(pasta):
    criativos, efeitos = build_exports(pasta, boot=20)
    assert len({c["ad_id"] for c in criativos}) == len(criativos) == 300
    assert len(efeitos) == 9  # 3 sim/não + 4 cores + 2 formatos


def test_criativos_trazem_as_dimensoes_da_midia(pasta):
    criativos, _ = build_exports(pasta, boot=20)
    primeiro = criativos[0]
    assert primeiro["platform"] and primeiro["country"] and primeiro["image_url"]


def test_mesma_execucao_tem_o_mesmo_run_id(pasta):
    quando = datetime(2026, 11, 20, 18, 30, tzinfo=UTC)
    criativos, efeitos = build_exports(pasta, boot=20, run_at=quando)
    ids = {r["run_id"] for r in criativos + efeitos}
    assert ids == {"20261120T183000Z"}


def test_arquivos_gerados_seguem_o_contrato(pasta, tmp_path):
    export_all(pasta, tmp_path, boot=20)
    criativos = _ler(tmp_path / "adlens_criativos.csv")
    efeitos = _ler(tmp_path / "adlens_efeitos.csv")
    assert list(criativos[0]) == CONTRATO_CRIATIVOS
    assert list(efeitos[0]) == CONTRATO_EFEITOS
    assert criativos[0]["has_face"] in {"true", "false"}
    int(criativos[0]["impressions"])  # tem que ser número inteiro


def test_schema_json_no_formato_do_bigquery(pasta, tmp_path):
    export_all(pasta, tmp_path, boot=20)
    schema = json.loads(
        (tmp_path / "schema_adlens_efeitos.json").read_text(encoding="utf-8")
    )
    assert [c["name"] for c in schema] == CONTRATO_EFEITOS
    assert {c["type"] for c in schema} <= {
        "STRING",
        "INT64",
        "FLOAT64",
        "BOOL",
        "TIMESTAMP",
    }


def test_comando_exportar(pasta, tmp_path):
    codigo = cli(
        ["exportar", "--pasta", str(pasta), "--saida", str(tmp_path), "--boot", "20"]
    )
    assert codigo == 0
    assert (tmp_path / "adlens_efeitos.csv").exists()


def test_documentacao_cita_todas_as_colunas():
    doc = Path(__file__).parents[1] / "docs" / "contrato-de-dados.md"
    texto = doc.read_text(encoding="utf-8")
    for coluna, _, _ in CRIATIVOS_SCHEMA + EFEITOS_SCHEMA:
        assert f"`{coluna}`" in texto, f"coluna sem documentação: {coluna}"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ('=HYPERLINK("x","clique")', '\'=HYPERLINK("x","clique")'),
        ("+55 11 9999", "'+55 11 9999"),
        ("-promo", "'-promo"),
        ("@sum(A1)", "'@sum(A1)"),
        ("Natal 2026", "Natal 2026"),  # texto normal não muda
        ("", ""),
    ],
)
def test_texto_que_parece_formula_e_desarmado(texto, esperado):
    assert seguro_para_excel(texto) == esperado


def test_csv_desarma_texto_mas_nao_mexe_em_numero(tmp_path):
    schema = [("ad_name", "STRING", ""), ("lift", "FLOAT64", "")]
    linhas = [{"ad_name": "=1+1", "lift": -0.05}]
    caminho = write_table(linhas, schema, tmp_path / "t.csv")
    with caminho.open(encoding="utf-8", newline="") as f:
        linha = next(csv.DictReader(f))
    assert linha == {"ad_name": "'=1+1", "lift": "-0.05"}


def test_efeitos_dizem_qual_metodo_calculou(pasta):
    _, efeitos = build_exports(pasta)
    assert {e["method"] for e in efeitos} == {"regressao"}
    _, efeitos = build_exports(pasta, boot=20, method="simples")
    assert {e["method"] for e in efeitos} == {"simples"}
