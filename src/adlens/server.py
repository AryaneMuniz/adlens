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

from adlens.confidence import Interval
from adlens.explore import (
    RANK_BY,
    compare_effects,
    group_values,
    tag_distribution,
    top_creatives,
)
from adlens.filters import Filter, parse_filter
from adlens.media import available_values
from adlens.metrics import METRICS, Metric, get_metric
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
        "intervalo de confiança. Além do CTR (padrão), dá para analisar o "
        "CPM e o CPC com metrica=cpm ou cpc: neles, lift NEGATIVO é bom "
        "(ficou mais barato). O método padrão é a regressão, que isola "
        "cada etiqueta e controla o país. Para perguntas sobre um país, uma "
        "plataforma ou um período, use os filtros (pais, plataforma, "
        "data_inicio, data_fim); resumo_dos_dados lista o que existe para "
        "filtrar. Para saber se um grupo é grande o bastante, use "
        "distribuicao_das_etiquetas; para exemplos concretos, top_criativos; "
        'para "o efeito é igual no país A e no B?", comparar. '
        "Os dados de demonstração são sintéticos."
    ),
)

# Menos sorteios que isso dá intervalo errado; mais que isso trava o servidor
MIN_SORTEIOS, MAX_SORTEIOS = 50, 2000

# Avisa o agente que a ferramenta só LÊ: ele pode chamar sem pedir licença
SO_LEITURA = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

# Guarda as últimas análises: perguntar de novo, sem os dados mudarem, é
# instantâneo. Guarda 4 (e não 1) porque o comparar faz duas de uma vez.
_cache: dict[tuple, tuple] = {}
MAX_CACHE = 4

# O ranking devolve no máximo isso: o agente não precisa de mil linhas
MAX_RANKING = 50


def _pasta_segura(pasta: str) -> Path:
    """Só aceita pastas DENTRO da pasta atual (o agente não sai passeando)."""
    base = Path.cwd().resolve()
    caminho = (base / pasta).resolve()
    if not caminho.is_relative_to(base):
        raise ToolError(f"Pasta fora do projeto não é permitida: {pasta}")
    return caminho


def _filtro(pais: str, plataforma: str, data_inicio: str, data_fim: str) -> Filter:
    """Monta o filtro; se vier errado (data inválida...), explica para o agente."""
    try:
        return parse_filter(pais, plataforma, data_inicio, data_fim)
    except ValueError as erro:
        raise ToolError(str(erro)) from erro


def _carregar(
    base: Path, filtro: Filter | None = None
) -> tuple[list[CreativeSpec], list[PerformanceRow], str]:
    """Lê os dados e, se der errado, explica o motivo para o agente.

    Sem isso, o agente recebe só "Error executing tool" e não sabe o que fazer.
    """
    try:
        return load_dataset(base, filtro)
    except FileNotFoundError as erro:
        raise ToolError(f"{erro}. Rode antes: adlens gerar") from erro
    except ValueError as erro:
        raise ToolError(f"Os dados têm um problema: {erro}") from erro


def _metrica(nome: str) -> Metric:
    """A métrica pelo nome; se não existir, explica para o agente."""
    try:
        return get_metric(nome)
    except ValueError as erro:
        raise ToolError(str(erro)) from erro


def _analise(
    base: Path,
    metodo: str,
    sorteios: int,
    filtro: Filter | None = None,
    metrica: Metric = METRICS["ctr"],
) -> tuple[list[CreativeSpec], list[PerformanceRow], list[Interval], dict]:
    """A análise completa, guardada até algum CSV da pasta mudar.

    O filtro e a métrica entram na chave: outro recorte = outra análise.
    """
    filtro = filtro or Filter()
    carimbo = tuple((p.name, p.stat().st_mtime_ns) for p in sorted(base.glob("*.csv")))
    chave = (str(base), carimbo, metodo, sorteios, filtro, metrica.name)
    if chave not in _cache:
        specs, rows, _ = _carregar(base, filtro)
        if len(_cache) >= MAX_CACHE:  # tira a mais antiga: a memória não cresce
            del _cache[next(iter(_cache))]
        try:
            efeitos = compute_effects(
                specs, rows, load_countries(base), metodo, sorteios, metrica
            )
        except ValueError as erro:  # poucos criativos, etiquetas sempre juntas...
            raise ToolError(str(erro)) from erro
        _cache[chave] = (specs, rows, efeitos, group_values(specs, rows, metrica))
    return _cache[chave]


@mcp.tool(annotations=SO_LEITURA)
def resumo_dos_dados(
    pasta: str = "data",
    pais: str = "",
    plataforma: str = "",
    data_inicio: str = "",
    data_fim: str = "",
) -> dict:
    """Resumo dos dados: quantos criativos, impressões, cliques, CTR e investimento.

    Filtros opcionais (vazio = todos): `pais` e `plataforma` aceitam vários
    separados por vírgula ("BR,MX"); `data_inicio` e `data_fim` no formato
    AAAA-MM-DD, inclusive. `recorte` diz qual filtro foi usado e
    `disponivel` lista os países, plataformas e o período que existem nos
    dados: consulte antes de filtrar.
    """
    base = _pasta_segura(pasta)
    filtro = _filtro(pais, plataforma, data_inicio, data_fim)
    specs, rows, fonte = _carregar(base, filtro)
    ids = {s.creative_id for s in specs}
    rows = [r for r in rows if r.creative_id in ids]
    midia = base / "midia_diaria.csv"
    impressoes = sum(r.impressions for r in rows)
    cliques = sum(r.clicks for r in rows)
    return {
        "criativos": len(specs),
        "impressoes": impressoes,
        "cliques": cliques,
        "ctr": round(cliques / impressoes, 5) if impressoes else 0.0,
        "investimento": round(sum(r.spend for r in rows), 2),
        "etiquetas_de": fonte,
        "recorte": filtro.describe(),
        "disponivel": available_values(midia) if midia.exists() else None,
    }


@mcp.tool(annotations=SO_LEITURA)
def efeito_das_caracteristicas(
    pasta: str = "data",
    metodo: str = "regressao",
    sorteios: int = 200,
    metrica: str = "ctr",
    pais: str = "",
    plataforma: str = "",
    data_inicio: str = "",
    data_fim: str = "",
) -> list[dict]:
    """Quanto cada característica muda o CTR (ou o CPM/CPC), com intervalo de 95%.

    `metrica`: "ctr" (padrão, maior é melhor), "cpm" ou "cpc" (custo: menor é
    melhor, então lift NEGATIVO é bom). `bom` já diz se o efeito ajuda,
    considerando esse sentido (só quando `significativo`).

    `metodo`: "regressao" (padrão) isola cada etiqueta das outras e do país:
    o lift é "com todo o resto igual". "simples" só compara os grupos e pode
    enganar quando as etiquetas andam juntas; use só para comparar.

    `lift` é relativo à `referencia`: 0.15 quer dizer CTR 15% maior que o
    dos criativos de referência (sem a característica, cor azul ou formato
    quadrado). `valor_grupo` e `valor_referencia` são a métrica bruta dos
    dois lados (sem controle nenhum; na regressão o lift pode diferir deles,
    e é justamente essa a correção), e `criativos` é quantos criativos estão no grupo: grupo
    pequeno = resultado menos confiável. `significativo` diz se dá para
    afirmar que o efeito existe (na regressão, já corrigido para muitas
    etiquetas testadas de uma vez). `sorteios` (só no simples) vai de 50 a
    2000 (padrão 200).

    Filtros opcionais, iguais aos do resumo_dos_dados: `pais`, `plataforma`
    (vários separados por vírgula) e `data_inicio`/`data_fim` (AAAA-MM-DD).
    Cada linha traz o `recorte` usado. Recorte com menos de 30 criativos é
    recusado (resultado não confiável).
    """
    if metodo not in METHODS:
        raise ToolError(
            f"metodo deve ser um de: {', '.join(METHODS)} (recebi {metodo})"
        )
    if not MIN_SORTEIOS <= sorteios <= MAX_SORTEIOS:
        raise ToolError(
            f"sorteios deve ficar entre {MIN_SORTEIOS} e {MAX_SORTEIOS} (recebi {sorteios})"
        )
    filtro = _filtro(pais, plataforma, data_inicio, data_fim)
    m = _metrica(metrica)
    base = _pasta_segura(pasta)
    _, _, intervalos, grupos = _analise(base, metodo, sorteios, filtro, m)

    resultado = []
    for r in sorted(intervalos, key=lambda r: r.lift, reverse=True):
        g = grupos.get((r.tag, r.value))
        if g is None:  # num recorte pequeno pode faltar o grupo
            continue
        resultado.append(
            {
                "etiqueta": r.tag,
                "valor": r.value,
                "referencia": g.reference,
                "lift": round(r.lift, 4),
                "intervalo_95": [round(r.low, 4), round(r.high, 4)],
                "significativo": r.significant,
                "bom": r.significant and (r.lift > 0) == m.higher_is_better,
                "metrica": m.name,
                "valor_grupo": round(g.metric_value, 5),
                "valor_referencia": round(g.metric_reference, 5),
                "criativos": g.creatives,
                "metodo": metodo,
                "recorte": filtro.describe(),
            }
        )
    return resultado


@mcp.tool(annotations=SO_LEITURA)
def distribuicao_das_etiquetas(
    pasta: str = "data",
    pais: str = "",
    plataforma: str = "",
    data_inicio: str = "",
    data_fim: str = "",
) -> list[dict]:
    """Quantos criativos têm cada etiqueta, e quanta mídia eles levaram.

    Use antes de tirar conclusões: grupo com poucos criativos dá resultado
    frágil, e etiqueta presente em quase todas as peças não tem com quem
    comparar. `pct_criativos` e `pct_impressoes` são fatias de 0 a 1; se a
    de impressões for bem maior que a de criativos, a mídia está concentrada
    nesse grupo. `ctr` é o CTR bruto do grupo. Aceita os mesmos filtros do
    resumo_dos_dados.
    """
    filtro = _filtro(pais, plataforma, data_inicio, data_fim)
    specs, rows, _ = _carregar(_pasta_segura(pasta), filtro)
    return [
        {
            "etiqueta": d.tag,
            "valor": d.value,
            "criativos": d.creatives,
            "pct_criativos": round(d.share_creatives, 4),
            "impressoes": d.impressions,
            "pct_impressoes": round(d.share_impressions, 4),
            "ctr": round(d.ctr, 5),
            "recorte": filtro.describe(),
        }
        for d in tag_distribution(specs, rows)
    ]


@mcp.tool(annotations=SO_LEITURA)
def top_criativos(
    pasta: str = "data",
    ordenar_por: str = "ctr",
    quantidade: int = 10,
    minimo_impressoes: int = 1000,
    piores: bool = False,
    pais: str = "",
    plataforma: str = "",
    data_inicio: str = "",
    data_fim: str = "",
) -> list[dict]:
    """Os melhores (ou, com piores=true, os piores) criativos, com as etiquetas.

    `ordenar_por`: ctr (padrão), impressoes, cliques ou investimento.
    `quantidade`: de 1 a 50 (padrão 10). `minimo_impressoes` (padrão 1000)
    tira quem quase não rodou: com pouca entrega, CTR alto é sorte. Útil
    para mostrar exemplos concretos de um efeito, mas um ranking NÃO prova
    efeito: para isso use efeito_das_caracteristicas. Aceita os mesmos
    filtros do resumo_dos_dados.
    """
    if ordenar_por not in RANK_BY:
        raise ToolError(
            f"ordenar_por deve ser um de: {', '.join(RANK_BY)} (recebi {ordenar_por})"
        )
    if not 1 <= quantidade <= MAX_RANKING:
        raise ToolError(
            f"quantidade deve ficar entre 1 e {MAX_RANKING} (recebi {quantidade})"
        )
    if minimo_impressoes < 0:
        raise ToolError("minimo_impressoes não pode ser negativo")
    filtro = _filtro(pais, plataforma, data_inicio, data_fim)
    specs, rows, _ = _carregar(_pasta_segura(pasta), filtro)
    ranking = top_creatives(
        specs, rows, ordenar_por, quantidade, minimo_impressoes, piores
    )
    if not ranking:
        raise ToolError(
            f"Nenhum criativo com pelo menos {minimo_impressoes} impressões "
            f"({filtro.describe()}). Diminua o minimo_impressoes."
        )
    return [
        {
            "posicao": i,
            "criativo": c.creative_id,
            "etiquetas": c.tags,
            "impressoes": c.impressions,
            "cliques": c.clicks,
            "ctr": round(c.ctr, 5),
            "investimento": round(c.spend, 2),
            "recorte": filtro.describe(),
        }
        for i, c in enumerate(ranking, start=1)
    ]


@mcp.tool(annotations=SO_LEITURA)
def comparar(
    pasta: str = "data",
    a_pais: str = "",
    a_plataforma: str = "",
    a_data_inicio: str = "",
    a_data_fim: str = "",
    b_pais: str = "",
    b_plataforma: str = "",
    b_data_inicio: str = "",
    b_data_fim: str = "",
    metodo: str = "regressao",
    metrica: str = "ctr",
) -> dict:
    """Compara o efeito de cada etiqueta entre dois recortes, A e B.

    Ex.: "o rosto funciona igual no Brasil e no México?" = a_pais="BR",
    b_pais="MX". Cada recorte usa os mesmos filtros do resumo_dos_dados,
    com o prefixo a_ ou b_. Para cada etiqueta: `lift_a`, `lift_b` e
    `diferente` (se a diferença é real, já corrigida para muitas etiquetas
    testadas de uma vez). `diferente` falso NÃO quer dizer "igual": pode ser
    só falta de dado. `criativos_em_comum` acima de zero (comum ao comparar
    períodos) deixa o teste otimista; o `aviso` diz quando isso acontece.
    `metrica`: ctr (padrão), cpm ou cpc.
    """
    if metodo not in METHODS:
        raise ToolError(
            f"metodo deve ser um de: {', '.join(METHODS)} (recebi {metodo})"
        )
    filtro_a = _filtro(a_pais, a_plataforma, a_data_inicio, a_data_fim)
    filtro_b = _filtro(b_pais, b_plataforma, b_data_inicio, b_data_fim)
    if filtro_a == filtro_b:
        raise ToolError(
            "Os recortes A e B são iguais. Mude ao menos um filtro, "
            'ex.: a_pais="BR" e b_pais="MX".'
        )
    m = _metrica(metrica)
    base = _pasta_segura(pasta)
    specs_a, _, efeitos_a, _ = _analise(base, metodo, 200, filtro_a, m)
    specs_b, _, efeitos_b, _ = _analise(base, metodo, 200, filtro_b, m)
    em_comum = {s.creative_id for s in specs_a} & {s.creative_id for s in specs_b}
    resultado = {
        "recorte_a": filtro_a.describe(),
        "recorte_b": filtro_b.describe(),
        "criativos_a": len(specs_a),
        "criativos_b": len(specs_b),
        "criativos_em_comum": len(em_comum),
        "metodo": metodo,
        "metrica": m.name,
        "etiquetas": [
            {
                "etiqueta": c.tag,
                "valor": c.value,
                "lift_a": round(c.lift_a, 4),
                "lift_b": round(c.lift_b, 4),
                "diferenca": round(c.lift_a - c.lift_b, 4),
                "diferente": c.different,
                "p_corrigido": round(c.p_adjusted, 4),
            }
            for c in compare_effects(efeitos_a, efeitos_b)
        ],
    }
    if em_comum:
        resultado["aviso"] = (
            f"{len(em_comum)} criativos estão nos dois recortes: o teste supõe "
            "recortes independentes e fica otimista (pode apontar diferença "
            "que não existe)."
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
def gerar_relatorio(
    pasta: str = "data",
    pais: str = "",
    plataforma: str = "",
    data_inicio: str = "",
    data_fim: str = "",
    metrica: str = "ctr",
) -> str:
    """Gera (ou atualiza) o relatório HTML da análise e devolve o caminho do arquivo.

    Aceita os mesmos filtros e a mesma `metrica` do efeito_das_caracteristicas;
    o relatório mostra o recorte e a métrica no topo.
    """
    base = _pasta_segura(pasta)
    filtro = _filtro(pais, plataforma, data_inicio, data_fim)
    m = _metrica(metrica)
    specs, rows, intervalos, _ = _analise(base, "regressao", 200, filtro, m)
    html = build_report(
        intervalos, specs, rows, None, THEMES[TEMA_PADRAO], filtro.describe(), m
    )
    return str(save_report(html, base / "relatorio.html"))


def main() -> None:
    """Liga o servidor no modo stdio (o agente fala com ele pelo terminal)."""
    mcp.run()


if __name__ == "__main__":
    main()
