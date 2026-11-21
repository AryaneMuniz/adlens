"""Métricas: além do CTR, o CPM e o CPC.

Para branding, clicar nem sempre é o objetivo. Às vezes a pergunta é
"qual criativo sai mais barato para aparecer?" (CPM) ou "qual traz clique
mais barato?" (CPC). As três métricas são uma DIVISÃO de duas colunas que
já temos:

    CTR = cliques / impressões          (maior é melhor)
    CPM = investimento / impressões x 1000   (menor é melhor)
    CPC = investimento / cliques        (menor é melhor)

Por isso a mesma análise serve para as três: só troca o que vai em cima
e o que vai embaixo da divisão. O cuidado é o sentido: no CTR, lift
positivo é bom; no CPM e no CPC, lift positivo é RUIM (ficou mais caro).

View rate, completion rate e outras de vídeo precisam de colunas que o
adlens ainda não tem: entram quando o time decidir.
"""

from dataclasses import dataclass

from adlens.performance import PerformanceRow


@dataclass(frozen=True)
class Metric:
    """Uma métrica que é a divisão de duas colunas da performance."""

    name: str  # como se pede: "cpc"
    label: str  # como se mostra: "CPC"
    numerator: str  # campo do PerformanceRow em cima da divisão
    denominator: str  # campo embaixo
    scale: float  # CPM é "por mil": 1000; as outras, 1
    higher_is_better: bool

    def ratio(self, numerator: float, denominator: float) -> float:
        """A métrica de totais já somados (0 se não der para dividir)."""
        return numerator / denominator * self.scale if denominator else 0.0

    def of(self, row: PerformanceRow) -> float:
        """A métrica de um criativo."""
        return self.ratio(getattr(row, self.numerator), getattr(row, self.denominator))

    def smoothed(self, row: PerformanceRow) -> float:
        """A métrica de um criativo sem nunca dar zero (a regressão usa log).

        Um criativo sem clique teria CTR 0 e CPC infinito; somar um pouquinho
        em cima e embaixo resolve sem mudar o resultado dos criativos normais.
        """
        num = getattr(row, self.numerator) + _SUAVIZAR[self.numerator]
        den = getattr(row, self.denominator) + _SUAVIZAR[self.denominator]
        return num / den * self.scale

    def direction(self) -> str:
        """O sentido em português, para mostrar nas telas."""
        return "maior é melhor" if self.higher_is_better else "menor é melhor"


# O "pouquinho" somado em cada coluna (meio clique, uma impressão, um centavo)
_SUAVIZAR = {"clicks": 0.5, "impressions": 1.0, "spend": 0.01}

METRICS: dict[str, Metric] = {
    "ctr": Metric("ctr", "CTR", "clicks", "impressions", 1.0, True),
    "cpm": Metric("cpm", "CPM", "spend", "impressions", 1000.0, False),
    "cpc": Metric("cpc", "CPC", "spend", "clicks", 1.0, False),
}


def get_metric(name: str) -> Metric:
    """A métrica pelo nome ("CPC" ou "cpc"); erro claro se não existir."""
    chave = name.strip().lower()
    if chave not in METRICS:
        raise ValueError(
            f"Métrica desconhecida: {name}. Use uma de: {', '.join(METRICS)}"
        )
    return METRICS[chave]


def is_good(lift: float, metric: Metric) -> bool:
    """O efeito é bom? No CTR, subir é bom; no CPM e no CPC, cair é bom."""
    return lift > 0 if metric.higher_is_better else lift < 0
