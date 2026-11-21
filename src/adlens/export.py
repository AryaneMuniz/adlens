"""Exportação no contrato de dados do adlens.

O "contrato de dados" é o formato combinado das tabelas que o adlens
entrega: nomes, tipos e significado de cada coluna. Quem consome (um
dashboard no Dataviz, uma tabela no BigQuery) confia nesse formato. Por
isso ele mora num lugar só (aqui) e tem testes que travam qualquer mudança.

Tabelas:
- adlens_criativos: uma linha por anúncio, com etiquetas e métricas
- adlens_efeitos: uma linha por etiqueta, com o lift, o intervalo de 95% e
  o método que calculou (regressão ou simples)

Além dos CSVs, gera o schema de cada tabela no formato JSON que o
BigQuery aceita para criar a tabela.
"""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from adlens.analysis import BINARY_TAGS, CATEGORICAL_TAGS
from adlens.regression import compute_effects
from adlens.storage import load_countries, load_dataset

# (coluna, tipo no BigQuery, descrição)
CRIATIVOS_SCHEMA: list[tuple[str, str, str]] = [
    ("run_id", "STRING", "Identificador da execução do adlens"),
    ("ad_id", "STRING", "ID do anúncio"),
    ("ad_name", "STRING", "Nome do anúncio"),
    ("platform", "STRING", "Plataforma de mídia"),
    ("country", "STRING", "País"),
    ("campaign_name", "STRING", "Nome da campanha"),
    ("image_url", "STRING", "Link da imagem do criativo"),
    ("has_face", "BOOL", "O criativo tem rosto"),
    ("has_product", "BOOL", "O criativo mostra o produto"),
    ("has_cta", "BOOL", "O criativo tem botão de chamada para ação"),
    ("dominant_color", "STRING", "Cor dominante"),
    ("format", "STRING", "Formato: quadrado, vertical ou horizontal"),
    ("impressions", "INT64", "Impressões no período"),
    ("clicks", "INT64", "Cliques no período"),
    ("investment", "FLOAT64", "Investimento no período"),
    ("ctr", "FLOAT64", "Cliques / impressões"),
    ("tag_source", "STRING", "Arquivo de onde vieram as etiquetas"),
]

EFEITOS_SCHEMA: list[tuple[str, str, str]] = [
    ("run_id", "STRING", "Identificador da execução do adlens"),
    ("run_at", "TIMESTAMP", "Quando a análise rodou (UTC)"),
    ("tag", "STRING", "Etiqueta: rosto, produto, cta, cor, formato"),
    ("value", "STRING", "Valor da etiqueta comparado"),
    ("reference", "STRING", "Valor de referência da comparação"),
    ("lift", "FLOAT64", "Quanto o CTR muda em relação à referência"),
    ("ci_low", "FLOAT64", "Limite inferior do intervalo de 95%"),
    ("ci_high", "FLOAT64", "Limite superior do intervalo de 95%"),
    ("significant", "BOOL", "Dá para afirmar que o efeito existe"),
    ("creatives", "INT64", "Quantos criativos têm esse valor"),
    ("method", "STRING", "Como o efeito foi calculado: regressao ou simples"),
]


def _dimensions(midia_csv: Path) -> dict[str, dict]:
    """Nome, plataforma, país, campanha e imagem de cada anúncio (da mídia diária)."""
    sql = """
        SELECT ad_id, any_value(ad_name), any_value(platform), any_value(country),
               any_value(campaign_name), any_value(image_url)
        FROM read_csv(?, header = true, types = {'ad_id': 'VARCHAR'})
        GROUP BY ad_id
    """
    campos = ["ad_name", "platform", "country", "campaign_name", "image_url"]
    return {
        ad: dict(zip(campos, resto))
        for ad, *resto in duckdb.execute(sql, [str(midia_csv)]).fetchall()
    }


def build_exports(
    pasta: Path,
    boot: int = 300,
    run_at: datetime | None = None,
    method: str = "regressao",
) -> tuple[list[dict], list[dict]]:
    """Monta as linhas das duas tabelas do contrato."""
    run_at = run_at or datetime.now(UTC)
    run_id = run_at.strftime("%Y%m%dT%H%M%SZ")
    specs, rows, fonte = load_dataset(pasta)
    midia = pasta / "midia_diaria.csv"
    dims = _dimensions(midia) if midia.exists() else {}
    perf = {r.creative_id: r for r in rows}

    criativos = []
    for s in specs:
        p = perf[s.creative_id]
        criativos.append(
            {
                "run_id": run_id,
                "ad_id": s.creative_id,
                **dims.get(
                    s.creative_id,
                    dict.fromkeys(
                        ["ad_name", "platform", "country", "campaign_name", "image_url"]
                    ),
                ),
                "has_face": s.has_face,
                "has_product": s.has_product,
                "has_cta": s.has_cta,
                "dominant_color": s.dominant_color,
                "format": s.format,
                "impressions": p.impressions,
                "clicks": p.clicks,
                "investment": p.spend,
                "ctr": round(p.ctr, 6),
                "tag_source": fonte,
            }
        )

    nomes = {v: k for k, v in BINARY_TAGS.items()}
    nomes |= {nome: col for col, (nome, _) in CATEGORICAL_TAGS.items()}
    referencias = {nome: ref for nome, ref in CATEGORICAL_TAGS.values()}
    efeitos = []
    for r in compute_effects(specs, rows, load_countries(pasta), method, boot):
        coluna = nomes[r.tag]
        if r.tag in referencias:
            n = sum(getattr(s, coluna) == r.value for s in specs)
        else:
            n = sum(bool(getattr(s, coluna)) for s in specs)
        efeitos.append(
            {
                "run_id": run_id,
                "run_at": run_at.isoformat(timespec="seconds"),
                "tag": r.tag,
                "value": r.value,
                "reference": referencias.get(r.tag, "não"),
                "lift": round(r.lift, 6),
                "ci_low": round(r.low, 6),
                "ci_high": round(r.high, 6),
                "significant": r.significant,
                "creatives": n,
                "method": method,
            }
        )
    return criativos, efeitos


# Se uma célula de texto começa com um destes, o Excel acha que é fórmula
INICIO_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def seguro_para_excel(texto: str) -> str:
    """Desarma texto que o Excel executaria como fórmula.

    Um nome de anúncio como `=HYPERLINK("site-falso", "clique")` vira link
    (ou coisa pior) quando alguém abre o CSV no Excel. Com um apóstrofo na
    frente, o Excel mostra o texto como texto.
    """
    return "'" + texto if texto.startswith(INICIO_DE_FORMULA) else texto


def _valor(v):
    """Formata para CSV do jeito que o BigQuery entende (true/false, vazio).

    Só TEXTO é desarmado: números negativos (lift -0.05) continuam números.
    """
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return seguro_para_excel(v)
    return "" if v is None else v


def write_table(
    rows: list[dict], schema: list[tuple[str, str, str]], path: Path
) -> Path:
    """Grava a tabela em CSV, com as colunas exatamente na ordem do contrato."""
    path.parent.mkdir(parents=True, exist_ok=True)
    colunas = [c for c, _, _ in schema]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(colunas)
        for row in rows:
            writer.writerow([_valor(row[c]) for c in colunas])
    return path


def write_schema(schema: list[tuple[str, str, str]], path: Path) -> Path:
    """Grava o schema no formato JSON aceito pelo BigQuery."""
    path.parent.mkdir(parents=True, exist_ok=True)
    campos = [
        {"name": c, "type": t, "mode": "NULLABLE", "description": d}
        for c, t, d in schema
    ]
    path.write_text(json.dumps(campos, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_all(
    pasta: Path, saida: Path, boot: int = 300, method: str = "regressao"
) -> list[Path]:
    """Gera as duas tabelas do contrato e os schemas, prontos para o BigQuery."""
    criativos, efeitos = build_exports(pasta, boot, method=method)
    return [
        write_table(criativos, CRIATIVOS_SCHEMA, saida / "adlens_criativos.csv"),
        write_table(efeitos, EFEITOS_SCHEMA, saida / "adlens_efeitos.csv"),
        write_schema(CRIATIVOS_SCHEMA, saida / "schema_adlens_criativos.json"),
        write_schema(EFEITOS_SCHEMA, saida / "schema_adlens_efeitos.json"),
    ]
