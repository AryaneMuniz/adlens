"""Servidor MCP do adlens: deixa agentes de IA consultarem a análise.

MCP (Model Context Protocol) é o "plugue" padrão entre agentes de IA
(Claude, Copilot...) e ferramentas. Cada função marcada com @mcp.tool()
vira uma ferramenta que o agente pode chamar sozinho, com a descrição
da docstring explicando para ele quando usar.

Rodar: uv run adlens-mcp   (o agente conversa com ele pelo stdin/stdout)
"""

from pathlib import Path

from mcp.server.mcpserver import MCPServer

from adlens.analysis import CATEGORICAL_TAGS
from adlens.confidence import bootstrap_lifts
from adlens.report import THEMES, build_report, save_report
from adlens.storage import load_dataset

mcp = MCPServer(
    "adlens",
    instructions=(
        "Ferramentas do adlens, inteligência de criativos de anúncio. "
        "Use para dizer quais características dos criativos (rosto, produto, "
        "CTA, cor, formato) aumentam ou diminuem o CTR, sempre informando o "
        "intervalo de confiança. Os dados de demonstração são sintéticos."
    ),
)

# Menos sorteios que isso dá intervalo errado; mais que isso trava o servidor
MIN_SORTEIOS, MAX_SORTEIOS = 50, 2000


# Com o que cada etiqueta é comparada: {"cor": "azul", "formato": "quadrado"}
REFERENCIAS = {nome: ref for nome, ref in CATEGORICAL_TAGS.values()}


def _pasta_segura(pasta: str) -> Path:
    """Só aceita pastas DENTRO da pasta atual (o agente não sai passeando)."""
    base = Path.cwd().resolve()
    caminho = (base / pasta).resolve()
    if not caminho.is_relative_to(base):
        raise ValueError(f"Pasta fora do projeto não é permitida: {pasta}")
    return caminho


@mcp.tool()
def resumo_dos_dados(pasta: str = "data") -> dict:
    """Resumo dos dados: quantos criativos, impressões, cliques, CTR e investimento."""
    specs, rows, fonte = load_dataset(_pasta_segura(pasta))
    impressoes = sum(r.impressions for r in rows)
    cliques = sum(r.clicks for r in rows)
    return {
        "criativos": len(specs),
        "impressoes": impressoes,
        "cliques": cliques,
        "ctr": round(cliques / impressoes, 5) if impressoes else 0.0,
        "investimento": round(sum(r.spend for r in rows), 2),
        "etiquetas_de": fonte,
    }


@mcp.tool()
def efeito_das_caracteristicas(pasta: str = "data", sorteios: int = 200) -> list[dict]:
    """Quanto cada característica do criativo muda o CTR, com intervalo de 95%.

    `lift` é relativo à `referencia`: 0.15 quer dizer CTR 15% maior que o
    dos criativos de referência (sem a característica, cor azul ou formato
    quadrado). `significativo` é falso quando o intervalo cruza o zero:
        nesse caso não dá para afirmar que o efeito existe. `sorteios` vai de
    50 a 2000 (padrão 200).
    """
    if not MIN_SORTEIOS <= sorteios <= MAX_SORTEIOS:
        raise ValueError(
            f"sorteios deve ficar entre {MIN_SORTEIOS} e {MAX_SORTEIOS} (recebi {sorteios})"
        )
    specs, rows, _ = load_dataset(_pasta_segura(pasta))

    return [
        {
            "etiqueta": r.tag,
            "valor": r.value,
            "referencia": REFERENCIAS.get(r.tag, "não"),
            "lift": round(r.lift, 4),
            "intervalo_95": [round(r.low, 4), round(r.high, 4)],
            "significativo": r.significant,
        }
        for r in sorted(
            bootstrap_lifts(specs, rows, n_boot=sorteios),
            key=lambda r: r.lift,
            reverse=True,
        )
    ]


@mcp.tool()
def gerar_relatorio(pasta: str = "data") -> str:
    """Gera o relatório HTML da análise e devolve o caminho do arquivo."""
    base = _pasta_segura(pasta)
    specs, rows, _ = load_dataset(base)
    html = build_report(
        bootstrap_lifts(specs, rows), specs, rows, None, THEMES["neutro"]
    )
    return str(save_report(html, base / "relatorio.html"))


def main() -> None:
    """Liga o servidor no modo stdio (o agente fala com ele pelo terminal)."""
    mcp.run()


if __name__ == "__main__":
    main()
