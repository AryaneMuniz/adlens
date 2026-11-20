"""Mídia diária no formato de uma plataforma de anúncios.

Dado de mídia de verdade vem com UMA LINHA POR ANÚNCIO POR DIA, com país,
plataforma, campanha, anúncio, link da imagem e as métricas do dia. Este
módulo gera dado sintético nesse mesmo formato e sabe somar por anúncio
com SQL (DuckDB), do mesmo jeito que faria lendo uma tabela no BigQuery.

Os totais por anúncio batem exatamente com `simulate_performance`, então
os efeitos plantados continuam valendo.
"""

import csv
import random
from dataclasses import astuple, dataclass, fields
from datetime import date, timedelta
from pathlib import Path

import duckdb

from adlens.performance import PerformanceRow, PlantedEffects, simulate_performance
from adlens.synthetic import CreativeSpec

COUNTRIES = ("BR", "MX", "CO", "PE", "CL", "AR")
PLATFORMS = ("meta", "tiktok", "google", "dv360")


@dataclass(frozen=True)
class MediaRow:
    """Uma linha de mídia: um anúncio em um dia."""

    date: str  # AAAA-MM-DD
    platform: str
    account_name: str
    country: str
    campaign_name: str
    ad_id: str
    ad_name: str
    image_url: str
    creative_text: str
    format: str
    impressions: int
    clicks: int
    investment: float


MEDIA_COLUMNS = [f.name for f in fields(MediaRow)]


def _split(total: int, weights: list[float]) -> list[int]:
    """Divide um total inteiro em partes proporcionais aos pesos (soma exata)."""
    soma = sum(weights)
    brutos = [total * w / soma for w in weights]
    partes = [int(b) for b in brutos]
    # Distribui o que sobrou para quem teve a maior parte decimal
    sobra = total - sum(partes)
    ordem = sorted(
        range(len(brutos)), key=lambda i: brutos[i] - partes[i], reverse=True
    )
    for i in ordem[:sobra]:
        partes[i] += 1
    return partes


def simulate_media(
    specs: list[CreativeSpec],
    effects: PlantedEffects | None = None,
    seed: int = 42,
    days: int = 30,
    start: date = date(2026, 10, 1),
) -> list[MediaRow]:
    """Gera a mídia diária de cada criativo (uma linha por anúncio por dia)."""
    totais = simulate_performance(specs, effects, seed=seed)
    rng = random.Random(seed + 1)
    linhas: list[MediaRow] = []
    for spec, total in zip(specs, totais):
        country = rng.choice(COUNTRIES)
        platform = rng.choice(PLATFORMS)
        ativos = rng.randint(7, days)  # quantos dias o anúncio rodou
        inicio = rng.randint(0, days - ativos)
        pesos = [rng.uniform(0.5, 1.5) for _ in range(ativos)]
        impressoes = _split(total.impressions, pesos)
        cliques = _split(total.clicks, pesos)
        centavos = _split(round(total.spend * 100), pesos)
        for d in range(ativos):
            dia = start + timedelta(days=inicio + d)
            linhas.append(
                MediaRow(
                    date=dia.isoformat(),
                    platform=platform,
                    account_name=f"{country} | Marca Demo",
                    country=country,
                    campaign_name=f"{country}_{platform}_awareness_{spec.format}",
                    ad_id=spec.creative_id,
                    ad_name=f"{country}_{platform}_{spec.creative_id}",
                    image_url=f"imagens/{spec.creative_id}.png",
                    creative_text="COMPRE AGORA" if spec.has_cta else "",
                    format=spec.format,
                    impressions=impressoes[d],
                    clicks=cliques[d],
                    investment=centavos[d] / 100,
                )
            )
    return linhas


def save_media(rows: list[MediaRow], path: Path) -> Path:
    """Salva a mídia diária num CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(MEDIA_COLUMNS)
        writer.writerows(astuple(r) for r in rows)
    return path


def performance_from_media(path: Path) -> list[PerformanceRow]:
    """Soma a mídia diária por anúncio, com SQL, direto do arquivo.

    Num BigQuery de verdade seria a mesma consulta, trocando o
    read_csv(...) pelo nome da tabela.
    """
    sql = """
        SELECT
            ad_id,
            SUM(impressions)::BIGINT AS impressions,
            SUM(clicks)::BIGINT AS clicks,
            ROUND(SUM(investment), 2) AS investment
        FROM read_csv(?, header = true, types = {'ad_id': 'VARCHAR'})
        GROUP BY ad_id
        ORDER BY ad_id
    """
    resultado = duckdb.execute(sql, [str(path)]).fetchall()
    return [
        PerformanceRow(ad, int(imp), int(cli), float(inv))
        for ad, imp, cli, inv in resultado
    ]
