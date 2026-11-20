"""Salvar e ler os dados do adlens em CSV.

Separar a leitura/gravação de arquivos do resto do código deixa o núcleo
independente de "onde o dado mora". Hoje é CSV; amanhã pode ser BigQuery,
trocando só este módulo.
"""

import csv
from pathlib import Path

from adlens.media import performance_from_media
from adlens.performance import PerformanceRow
from adlens.synthetic import CreativeSpec

SPEC_COLUMNS = [
    "creative_id",
    "has_face",
    "has_product",
    "has_cta",
    "dominant_color",
    "format",
]


def save_specs(specs: list[CreativeSpec], path: Path) -> Path:
    """Salva as fichas dos criativos num CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(SPEC_COLUMNS)
        for s in specs:
            writer.writerow([getattr(s, col) for col in SPEC_COLUMNS])
    return path


def load_specs(path: Path) -> list[CreativeSpec]:
    """Lê as fichas dos criativos de um CSV."""
    with path.open(encoding="utf-8") as f:
        return [
            CreativeSpec(
                creative_id=row["creative_id"],
                has_face=row["has_face"] == "True",
                has_product=row["has_product"] == "True",
                has_cta=row["has_cta"] == "True",
                dominant_color=row["dominant_color"],
                format=row["format"],
            )
            for row in csv.DictReader(f)
        ]


def load_performance(path: Path) -> list[PerformanceRow]:
    """Lê a performance de um CSV (o mesmo formato do save_csv)."""
    with path.open(encoding="utf-8") as f:
        return [
            PerformanceRow(
                creative_id=row["creative_id"],
                impressions=int(row["impressions"]),
                clicks=int(row["clicks"]),
                spend=float(row["spend"]),
            )
            for row in csv.DictReader(f)
        ]


def load_dataset(pasta: Path) -> tuple[list[CreativeSpec], list[PerformanceRow], str]:
    """Lê as etiquetas (ou, se não houver, o gabarito) e a performance.

    Etiquetas: etiquetas.csv quando existe (o que o etiquetador viu); senão,
    criativos.csv (o gabarito). Performance: midia_diaria.csv somada por
    anúncio quando existe; senão, performance.csv. Devolve também o nome do
    arquivo de etiquetas usado.
    """
    etiquetas, gabarito = pasta / "etiquetas.csv", pasta / "criativos.csv"
    fichas = etiquetas if etiquetas.exists() else gabarito
    midia, perf = pasta / "midia_diaria.csv", pasta / "performance.csv"
    if not fichas.exists() or not (midia.exists() or perf.exists()):
        raise FileNotFoundError(
            f"Não achei os dados em {pasta.resolve()}. Rode antes: adlens gerar"
        )
    linhas = performance_from_media(midia) if midia.exists() else load_performance(perf)
    return load_specs(fichas), linhas, fichas.name
