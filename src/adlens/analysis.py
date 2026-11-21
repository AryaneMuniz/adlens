"""Análise: quanto cada característica do criativo muda o CTR.

Junta as etiquetas dos criativos com a performance num banco DuckDB
(SQL dentro do Python, sem servidor) e calcula o "lift" de cada etiqueta:
quanto o CTR de quem tem a característica fica acima (ou abaixo)
de quem não tem.
"""

from dataclasses import dataclass

import duckdb

from adlens.performance import PerformanceRow, simulate_performance
from adlens.synthetic import CreativeSpec, generate_specs

# Etiquetas de sim/não: coluna -> nome amigável
BINARY_TAGS: dict[str, str] = {
    "has_face": "rosto",
    "has_product": "produto",
    "has_cta": "cta",
}

# Etiquetas com várias opções: coluna -> (nome amigável, valor de referência)
CATEGORICAL_TAGS: dict[str, tuple[str, str]] = {
    "dominant_color": ("cor", "azul"),
    "format": ("formato", "quadrado"),
}


@dataclass(frozen=True)
class TagLift:
    """O efeito de uma etiqueta no CTR, comparado com a referência."""

    tag: str  # ex.: "rosto"
    value: str  # ex.: "sim" ou "vermelho"
    reference: str  # ex.: "não" ou "azul"
    ctr: float
    ctr_reference: float
    creatives: int

    @property
    def lift(self) -> float:
        return self.ctr / self.ctr_reference - 1


def build_database(
    specs: list[CreativeSpec], rows: list[PerformanceRow]
) -> duckdb.DuckDBPyConnection:
    """Cria um banco DuckDB em memória com as tabelas criativos e performance."""
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE criativos (
            creative_id VARCHAR PRIMARY KEY,
            has_face BOOLEAN,
            has_product BOOLEAN,
            has_cta BOOLEAN,
            dominant_color VARCHAR,
            format VARCHAR
        )
        """
    )
    con.executemany(
        "INSERT INTO criativos VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                s.creative_id,
                s.has_face,
                s.has_product,
                s.has_cta,
                s.dominant_color,
                s.format,
            )
            for s in specs
        ],
    )
    con.execute(
        """
        CREATE TABLE performance (
            creative_id VARCHAR,
            impressions INTEGER,
            clicks INTEGER,
            spend DOUBLE
        )
        """
    )
    con.executemany(
        "INSERT INTO performance VALUES (?, ?, ?, ?)",
        [(r.creative_id, r.impressions, r.clicks, r.spend) for r in rows],
    )
    return con


def _ctr_by(
    con: duckdb.DuckDBPyConnection, column: str
) -> dict[str, tuple[float, int]]:
    """CTR e quantidade de criativos para cada valor de uma coluna."""
    if column not in BINARY_TAGS and column not in CATEGORICAL_TAGS:
        raise ValueError(f"coluna desconhecida: {column}")
    sql = f"""
        SELECT
            CAST(c.{column} AS VARCHAR) AS valor,
            SUM(p.clicks) / SUM(p.impressions) AS ctr,
            COUNT(*) AS criativos
        FROM criativos AS c
        JOIN performance AS p USING (creative_id)
        GROUP BY 1
    """
    return {valor: (ctr, n) for valor, ctr, n in con.execute(sql).fetchall()}


def analyze(con: duckdb.DuckDBPyConnection) -> list[TagLift]:
    """Calcula o lift de todas as etiquetas.

    Se faltar um dos lados da comparação (num recorte pequeno, nenhum
    criativo azul, por exemplo), aquela etiqueta fica de fora em vez de
    quebrar a análise.
    """
    results: list[TagLift] = []
    for column, name in BINARY_TAGS.items():
        groups = _ctr_by(con, column)
        if "true" not in groups or "false" not in groups:
            continue
        ctr_yes, n_yes = groups["true"]
        ctr_no, _ = groups["false"]
        results.append(TagLift(name, "sim", "não", ctr_yes, ctr_no, n_yes))
    for column, (name, reference) in CATEGORICAL_TAGS.items():
        groups = _ctr_by(con, column)
        if reference not in groups:
            continue
        ctr_ref, _ = groups[reference]
        for value, (ctr, n) in sorted(groups.items()):
            if value != reference:
                results.append(TagLift(name, value, reference, ctr, ctr_ref, n))
    return results


if __name__ == "__main__":
    specs = generate_specs(n=3000, seed=42)
    con = build_database(specs, simulate_performance(specs, seed=42))
    print(f"{'etiqueta':<10}{'valor':<12}{'vs':<10}{'lift':>8}")
    for r in analyze(con):
        print(f"{r.tag:<10}{r.value:<12}{r.reference:<10}{r.lift:>+8.1%}")
