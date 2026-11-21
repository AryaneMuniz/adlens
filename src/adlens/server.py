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
from adlens.confidence import Interval
from adlens.performance import PerformanceRow
from adlens.regression import METHODS, compute_effects
from adlens.report import TEMA_PADRAO, THEMES, build_report, save_report
from adlens.storage import load_countries, load_dataset
from adlens.synthetic import CreativeSpec

mcp = MCPServer(
    "adlens",
    instructions=(
        "Ferramentas do adlens, inteligência de criativos de anúncio. "
        "Use para dizer quais características dos criativos (rosto, produto, "
        "CTA, cor, formato) aumentam ou diminuem o CTR, sempre informando o "
        "intervalo de confiança. O método padrão é a regressão, que isola "
        "cada etiqueta e controla o país. Os dados de demonstração são sintéticos."
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
    base: Path, metodo: str, sorteios: int
) -> tuple[list[CreativeSpec], list[PerformanceRow], list[Interval], list[TagLift]]:
    """A análise completa, guardada até algum CSV da pasta mudar."""
    carimbo = tuple((p.name, p.stat().st_mtime_ns) for p in sorted(base.glob("*.csv")))
    chave = (str(base), carimbo, metodo, sorteios)
    if chave not in _cache:
        specs, rows, _ = _carregar(base)
        _cache.clear()  # só a última análise: a memória não cresce sem parar
        try:
            efeitos = compute_effects(
                specs, rows, load_countries(base), metodo, sorteios
            )
        except ValueError as erro:  # poucos criativos, etiquetas sempre juntas...
            raise ToolError(str(erro)) from erro
        _cache[chave] = (specs, rows, efeitos, analyze(build_database(specs, rows)))
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
def efeito_das_caracteristicas(
    pasta: str = "data", metodo: str = "regressao", sorteios: int = 200
) -> list[dict]:
    """Quanto cada característica do criativo muda o CTR, com intervalo de 95%.

    `metodo`: "regressao" (padrão) isola cada etiqueta das outras e do país:
    o lift é "com todo o resto igual". "simples" só compara os grupos e pode
    enganar quando as etiquetas andam juntas; use só para comparar.

    `lift` é relativo à `referencia`: 0.15 quer dizer CTR 15% maior que o
    dos criativos de referência (sem a característica, cor azul ou formato
    quadrado). `ctr_grupo` e `ctr_referencia` são os CTRs brutos dos dois
    lados (sem controle nenhum; na regressão o lift pode diferir deles, e é
    justamente essa a correção), e `criativos` é quantos criativos estão no grupo: grupo
    pequeno = resultado menos confiável. `significativo` diz se dá para
    afirmar que o efeito existe (na regressão, já corrigido para muitas
    etiquetas testadas de uma vez). `sorteios` (só no simples) vai de 50 a
    2000 (padrão 200).
    """
    if metodo not in METHODS:
        raise ToolError(
            f"metodo deve ser um de: {', '.join(METHODS)} (recebi {metodo})"
        )
    if not MIN_SORTEIOS <= sorteios <= MAX_SORTEIOS:
        raise ToolError(
            f"sorteios deve ficar entre {MIN_SORTEIOS} e {MAX_SORTEIOS} (recebi {sorteios})"
        )
    _, _, intervalos, pontos = _analise(_pasta_segura(pasta), metodo, sorteios)
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
                "metodo": metodo,
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
    specs, rows, intervalos, _ = _analise(base, "regressao", 200)
    html = build_report(intervalos, specs, rows, None, THEMES[TEMA_PADRAO])
    return str(save_report(html, base / "relatorio.html"))


def main() -> None:
    """Liga o servidor no modo stdio (o agente fala com ele pelo terminal)."""
    mcp.run()


if __name__ == "__main__":
    main()
