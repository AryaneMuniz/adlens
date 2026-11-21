"""Salvar e ler os dados do adlens em CSV.

Separar a leitura/gravação de arquivos do resto do código deixa o núcleo
independente de "onde o dado mora". Hoje é CSV; amanhã pode ser BigQuery,
trocando só este módulo.

Este módulo também é a "porta de entrada" do dado: tudo que chega passa
por validações aqui, para que dado errado pare com uma mensagem clara em
vez de virar um resultado errado lá na frente.
"""

import csv
from collections import Counter
from pathlib import Path

from adlens.filters import MIN_CREATIVES, Filter, FilterError
from adlens.media import available_values, performance_from_media
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

# Jeitos de escrever sim/não que aceitamos (o BigQuery exporta "true")
VERDADEIRO = {"true", "1", "sim"}
FALSO = {"false", "0", "não", "nao", ""}


def parse_bool(texto: str) -> bool:
    """Lê um sim/não do jeito que vier: True, true, 1, sim..."""
    valor = texto.strip().lower()
    if valor in VERDADEIRO:
        return True
    if valor in FALSO:
        return False
    raise ValueError(f"Valor de sim/não inválido: {texto!r}")


def _sem_repetidos(ids: list[str], origem: str) -> None:
    """Para com erro se algum creative_id aparecer mais de uma vez."""
    repetidos = sorted(i for i, n in Counter(ids).items() if n > 1)
    if repetidos:
        raise ValueError(
            f"creative_id repetido em {origem}: {', '.join(repetidos[:5])}"
        )


def validate_performance(rows: list[PerformanceRow]) -> None:
    """Para com erro se houver número impossível na performance."""
    problemas = []
    for r in rows:
        if r.impressions < 0 or r.clicks < 0 or r.spend < 0:
            problemas.append(f"{r.creative_id} tem número negativo")
        elif r.clicks > r.impressions:
            problemas.append(f"{r.creative_id} tem mais cliques que impressões")
    if problemas:
        raise ValueError("Performance impossível: " + "; ".join(problemas[:5]))


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
    """Lê as fichas dos criativos de um CSV (cor e formato em minúsculas)."""
    with path.open(encoding="utf-8") as f:
        specs = [
            CreativeSpec(
                creative_id=row["creative_id"],
                has_face=parse_bool(row["has_face"]),
                has_product=parse_bool(row["has_product"]),
                has_cta=parse_bool(row["has_cta"]),
                dominant_color=row["dominant_color"].strip().lower(),
                format=row["format"].strip().lower(),
            )
            for row in csv.DictReader(f)
        ]
    _sem_repetidos([s.creative_id for s in specs], path.name)
    return specs


def load_performance(path: Path) -> list[PerformanceRow]:
    """Lê a performance de um CSV (o mesmo formato do save_csv)."""
    with path.open(encoding="utf-8") as f:
        rows = [
            PerformanceRow(
                creative_id=row["creative_id"],
                impressions=int(row["impressions"]),
                clicks=int(row["clicks"]),
                spend=float(row["spend"]),
            )
            for row in csv.DictReader(f)
        ]
    _sem_repetidos([r.creative_id for r in rows], path.name)
    return rows


def load_countries(pasta: Path) -> dict[str, str]:
    """O país de cada criativo, lido da mídia diária (vazio se não houver).

    A regressão usa o país como controle: compara rosto com sem-rosto dentro
    do mesmo país. Sem mídia diária, todo mundo fica no mesmo "país".
    """
    midia = pasta / "midia_diaria.csv"
    if not midia.exists():
        return {}
    with midia.open(encoding="utf-8") as f:
        return {row["ad_id"]: row["country"] for row in csv.DictReader(f)}


def check_filter(filtro: Filter, midia: Path) -> None:
    """Para com erro claro se o filtro pede algo que não existe nos dados.

    Sem isso, "pais=BRA" (em vez de BR) devolveria zero linhas e a pessoa
    (ou o agente) não saberia por quê. O erro já lista o que existe.
    """
    existe = available_values(midia)
    for pedidos, chave, nome in (
        (filtro.countries, "paises", "País"),
        (filtro.platforms, "plataformas", "Plataforma"),
    ):
        faltam = [v for v in pedidos if v not in existe[chave]]
        if faltam:
            raise FilterError(
                f"{nome} sem dados: {', '.join(faltam)}. "
                f"Disponíveis: {', '.join(existe[chave])}"
            )


def load_dataset(
    pasta: Path, filtro: Filter | None = None
) -> tuple[list[CreativeSpec], list[PerformanceRow], str]:
    """Lê as etiquetas (ou, se não houver, o gabarito) e a performance.

    Etiquetas: etiquetas.csv quando existe (o que o etiquetador viu); senão,
    criativos.csv (o gabarito). Performance: midia_diaria.csv somada por
    anúncio quando existe; senão, performance.csv. Devolve também o nome do
    arquivo de etiquetas usado. Para com erro claro se o dado for inválido.

    Com `filtro`, só entram os criativos que rodaram no recorte, com os
    números do recorte. Precisa da mídia diária (o performance.csv já vem
    somado e não tem país, plataforma nem data).
    """
    filtro = filtro or Filter()
    etiquetas, gabarito = pasta / "etiquetas.csv", pasta / "criativos.csv"
    fichas = etiquetas if etiquetas.exists() else gabarito
    midia, perf = pasta / "midia_diaria.csv", pasta / "performance.csv"
    if not fichas.exists() or not (midia.exists() or perf.exists()):
        raise FileNotFoundError(
            f"Não achei os dados em {pasta.resolve()}. Rode antes: adlens gerar"
        )
    if filtro.active and not midia.exists():
        raise FilterError(
            "Os filtros precisam da mídia diária (midia_diaria.csv), que tem "
            "país, plataforma e data. Rode: adlens gerar"
        )
    specs = load_specs(fichas)
    if not midia.exists():
        linhas = load_performance(perf)
    else:
        if filtro.active:
            check_filter(filtro, midia)
        linhas = performance_from_media(midia, filtro)
    validate_performance(linhas)
    ids = {r.creative_id for r in linhas}
    if filtro.active:
        # No recorte, quem não rodou simplesmente fica de fora
        specs = [s for s in specs if s.creative_id in ids]
        if len(specs) < MIN_CREATIVES:
            raise FilterError(
                f"Só {len(specs)} criativos no recorte ({filtro.describe()}); "
                f"o mínimo para uma análise confiável é {MIN_CREATIVES}. "
                "Afrouxe os filtros."
            )
        return specs, linhas, fichas.name
    faltando = sorted({s.creative_id for s in specs} - ids)
    if faltando:
        raise ValueError(f"Criativos sem performance: {', '.join(faltando[:5])}")
    return specs, linhas, fichas.name
