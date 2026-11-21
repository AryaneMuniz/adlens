"""Servidor MCP do adlens: deixa agentes de IA consultarem a análise.

MCP (Model Context Protocol) é o "plugue" padrão entre agentes de IA
(Claude, Copilot...) e ferramentas. Cada função marcada com @mcp.tool()
vira uma ferramenta que o agente pode chamar sozinho, com a descrição
da docstring explicando para ele quando usar.

Rodar: uv run adlens-mcp   (o agente conversa com ele pelo stdin/stdout)
"""

from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from adlens.analysis import TagLift, analyze, build_database
from adlens.confidence import LiftInterval, bootstrap_lifts
from adlens.performance import PerformanceRow
from adlens.report import TEMA_PADRAO, THEMES, build_report, save_report
from adlens.storage import load_dataset
from adlens.synthetic import CreativeSpec

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

# Avisa o agente que a ferramenta só LÊ: ele pode chamar sem pedir licença
SO_LEITURA = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

# Guarda a última análise: perguntar de novo, sem os dados mudarem, é instantâneo
_cache: dict[tuple, tuple] = {}


def _pasta_segura(pasta: str) -> Path:
    """Só aceita pastas DENTRO da pasta atual (o agente não sai passeando)."""
    base = Path.cwd().resolve()
    caminho = (base / pasta).resolve()
    if not caminho.is_relative_to(base):
        raise ToolError(f"Pasta fora do projeto não é permitida: {pasta}")
    return caminho


def _carregar(base: Path) -> tuple[list[CreativeSpec], list[PerformanceRow], str]:
    """Lê os dados e, se der errado, explica o motivo para o agente.

    Sem isso, o agente recebe só "Error executing tool" e não sabe o que fazer.
    """
    try:
        return load_dataset(base)
    except FileNotFoundError as erro:
        raise ToolError(f"{erro}. Rode antes: adlens gerar") from erro
    except ValueError as erro:
        raise ToolError(f"Os dados têm um problema: {erro}") from erro


def _analise(
    base: Path, sorteios: int
) -> tuple[list[CreativeSpec], list[PerformanceRow], list[LiftInterval], list[TagLift]]:
    """A análise completa, guardada até algum CSV da pasta mudar."""
    carimbo = tuple((p.name, p.stat().st_mtime_ns) for p in sorted(base.glob("*.csv")))
    chave = (str(base), carimbo, sorteios)
    if chave not in _cache:
        specs, rows, _ = _carregar(base)
        _cache.clear()  # só a última análise: a memória não cresce sem parar
        _cache[chave] = (
            specs,
            rows,
            bootstrap_lifts(specs, rows, n_boot=sorteios),
            analyze(build_database(specs, rows)),
        )
    return _cache[chave]


@mcp.tool(annotations=SO_LEITURA)
def resumo_dos_dados(pasta: str = "data") -> dict:
    """Resumo dos dados: quantos criativos, impressões, cliques, CTR e investimento."""
    specs, rows, fonte = _carregar(_pasta_segura(pasta))
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


@mcp.tool(annotations=SO_LEITURA)
def efeito_das_caracteristicas(pasta: str = "data", sorteios: int = 200) -> list[dict]:
    """Quanto cada característica do criativo muda o CTR, com intervalo de 95%.

    `lift` é relativo à `referencia`: 0.15 quer dizer CTR 15% maior que o
    dos criativos de referência (sem a característica, cor azul ou formato
    quadrado). `ctr_grupo` e `ctr_referencia` são os CTRs dos dois lados da
    comparação, e `criativos` é quantos criativos estão no grupo: grupo
    pequeno = resultado menos confiável. `significativo` é falso quando o
    intervalo cruza o zero: nesse caso não dá para afirmar que o efeito
    existe. `sorteios` vai de 50 a 2000 (padrão 200).
    """
    if not MIN_SORTEIOS <= sorteios <= MAX_SORTEIOS:
        raise ToolError(
            f"sorteios deve ficar entre {MIN_SORTEIOS} e {MAX_SORTEIOS} (recebi {sorteios})"
        )
    _, _, intervalos, pontos = _analise(_pasta_segura(pasta), sorteios)
    grupos = {(p.tag, p.value): p for p in pontos}

    resultado = []
    for r in sorted(intervalos, key=lambda r: r.lift, reverse=True):
        g = grupos[(r.tag, r.value)]
        resultado.append(
            {
                "etiqueta": r.tag,
                "valor": r.value,
                "referencia": g.reference,
                "lift": round(r.lift, 4),
                "intervalo_95": [round(r.low, 4), round(r.high, 4)],
                "significativo": r.significant,
                "ctr_grupo": round(g.ctr, 5),
                "ctr_referencia": round(g.ctr_reference, 5),
                "criativos": g.creatives,
            }
        )
    return resultado


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,  # grava um arquivo...
        destructiveHint=False,  # ...mas não apaga nada dos dados
        idempotentHint=True,  # rodar duas vezes dá o mesmo resultado
        openWorldHint=False,
    )
)
def gerar_relatorio(pasta: str = "data") -> str:
    """Gera (ou atualiza) o relatório HTML da análise e devolve o caminho do arquivo."""
    base = _pasta_segura(pasta)
    specs, rows, intervalos, _ = _analise(base, 200)
    html = build_report(intervalos, specs, rows, None, THEMES[TEMA_PADRAO])
    return str(save_report(html, base / "relatorio.html"))


def main() -> None:
    """Liga o servidor no modo stdio (o agente fala com ele pelo terminal)."""
    mcp.run()


if __name__ == "__main__":
    main()
