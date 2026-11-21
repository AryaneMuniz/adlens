"""Filtros: analisar só um recorte dos dados (país, plataforma, período).

A pergunta de verdade raramente é "no geral". É "no Brasil", "no TikTok",
"no mês passado". O filtro corta a MÍDIA DIÁRIA antes de somar por anúncio:
um criativo que rodou em outubro e novembro, filtrado para outubro, entra
só com as impressões e cliques de outubro.

Por isso o filtro precisa da mídia diária (uma linha por anúncio por dia,
com país e plataforma). O performance.csv já vem somado e não tem como
cortar.

O filtro vira um pedaço de SQL com parâmetros (?), nunca com o texto do
usuário colado na consulta: isso impede SQL injection.
"""

from dataclasses import dataclass
from datetime import date

# Abaixo disso o resultado do recorte não é confiável (e a análise pode quebrar)
MIN_CREATIVES = 30


@dataclass(frozen=True)
class Filter:
    """Um recorte dos dados. Campo vazio = sem filtro naquele campo."""

    countries: tuple[str, ...] = ()  # ex.: ("BR", "MX")
    platforms: tuple[str, ...] = ()  # ex.: ("meta",)
    start: date | None = None  # primeiro dia (inclusive)
    end: date | None = None  # último dia (inclusive)

    @property
    def active(self) -> bool:
        """Tem algum filtro ligado?"""
        return bool(self.countries or self.platforms or self.start or self.end)

    def describe(self) -> str:
        """O recorte em português, para mostrar nas telas."""
        partes = []
        if self.countries:
            partes.append("país " + ", ".join(self.countries))
        if self.platforms:
            partes.append("plataforma " + ", ".join(self.platforms))
        if self.start or self.end:
            de = self.start.isoformat() if self.start else "início"
            ate = self.end.isoformat() if self.end else "fim"
            partes.append(f"de {de} a {ate}")
        return " · ".join(partes) if partes else "todos os dados"

    def where(self) -> tuple[str, list]:
        """O filtro em SQL: o texto do WHERE e os valores dos parâmetros (?)."""
        condicoes: list[str] = []
        valores: list = []
        if self.countries:
            condicoes.append(f"country IN ({', '.join('?' * len(self.countries))})")
            valores += self.countries
        if self.platforms:
            condicoes.append(f"platform IN ({', '.join('?' * len(self.platforms))})")
            valores += self.platforms
        if self.start:
            condicoes.append("date >= ?")
            valores.append(self.start)
        if self.end:
            condicoes.append("date <= ?")
            valores.append(self.end)
        return " AND ".join(condicoes) or "TRUE", valores


def _lista(texto: str | None, maiusculas: bool) -> tuple[str, ...]:
    """'br, mx' -> ('BR', 'MX'): separa por vírgula, limpa espaços e repetidos."""
    itens = [i.strip() for i in (texto or "").split(",") if i.strip()]
    itens = [i.upper() if maiusculas else i.lower() for i in itens]
    return tuple(dict.fromkeys(itens))  # tira repetidos mantendo a ordem


def _data(texto: str | None, campo: str) -> date | None:
    """'2026-10-01' -> date; vazio -> None; formato errado -> erro claro."""
    if not texto or not texto.strip():
        return None
    try:
        return date.fromisoformat(texto.strip())
    except ValueError:
        raise ValueError(
            f"{campo} inválida: {texto!r}. Use o formato AAAA-MM-DD, ex.: 2026-10-01"
        ) from None


def parse_filter(
    countries: str | None = None,
    platforms: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> Filter:
    """Monta o filtro a partir do texto digitado (CLI) ou enviado (MCP).

    País vai para maiúsculas (BR) e plataforma para minúsculas (meta), do
    jeito que estão na mídia diária. Para com erro claro se a data vier
    errada ou se o início for depois do fim.
    """
    filtro = Filter(
        countries=_lista(countries, maiusculas=True),
        platforms=_lista(platforms, maiusculas=False),
        start=_data(start, "Data inicial"),
        end=_data(end, "Data final"),
    )
    if filtro.start and filtro.end and filtro.start > filtro.end:
        raise ValueError(
            f"A data inicial ({filtro.start}) é depois da final ({filtro.end})."
        )
    return filtro
