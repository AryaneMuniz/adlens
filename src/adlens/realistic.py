"""Simulação realista: as armadilhas que enganam a análise simples.

A simulação da Fase 1 é "boazinha": as etiquetas são sorteadas de forma
independente, todo criativo tem peso parecido e não existe país. Assim, a
análise simples (comparar o CTR de quem tem a etiqueta com o de quem não
tem) acerta. Dado de verdade não é assim. Cada função aqui cria um "mundo"
com UMA armadilha conhecida e um gabarito (`truth`), para mostrar onde a
análise simples erra:

- confounded: rosto não faz nada, mas quase sempre vem junto com CTA.
- simpson: rosto ajuda em todo país, mas o país de CTR alto quase não usa rosto.
- giant: nenhuma etiqueta faz nada, mas uma peça gigante, por acaso, foi bem.
- noisy: nenhuma etiqueta faz nada, mas cada criativo tem seu próprio "jeito".

A correção vem depois (regressão, Issue #35). Aqui só mostramos o problema.
"""

import random
from dataclasses import dataclass

from adlens.confidence import bootstrap_lifts
from adlens.performance import PerformanceRow, sample_clicks
from adlens.synthetic import CreativeSpec, generate_specs

BASE_CTR = 0.012


@dataclass(frozen=True)
class World:
    """Um conjunto de dados com uma armadilha e o gabarito dela."""

    specs: list[CreativeSpec]
    rows: list[PerformanceRow]
    country: dict[str, str]  # criativo -> país
    truth: dict[str, float]  # efeito VERDADEIRO de cada etiqueta (lift)


def _spec(i: int, face: bool, product: bool, cta: bool) -> CreativeSpec:
    """Um criativo com cor e formato fixos (só as etiquetas sim/não variam)."""
    return CreativeSpec(f"CR{i:04d}", face, product, cta, "azul", "quadrado")


def _row(
    rng: random.Random, cid: str, ctr: float, impressions: int = 0
) -> PerformanceRow:
    """A performance de um criativo com o CTR verdadeiro informado."""
    impressions = impressions or rng.randint(20_000, 80_000)
    clicks = sample_clicks(rng, impressions, ctr)
    return PerformanceRow(cid, impressions, clicks, round(impressions / 1000 * 15, 2))


def confounded(n: int = 2000, seed: int = 0) -> World:
    """Rosto NÃO muda o CTR, mas 90% dos criativos com rosto têm CTA (+20%)."""
    rng = random.Random(seed)
    specs, rows = [], []
    for i in range(1, n + 1):
        face = rng.random() < 0.5
        cta = rng.random() < (0.9 if face else 0.2)
        spec = _spec(i, face, rng.random() < 0.5, cta)
        specs.append(spec)
        rows.append(_row(rng, spec.creative_id, BASE_CTR * (1.2 if cta else 1.0)))
    country = {s.creative_id: "BR" for s in specs}
    return World(specs, rows, country, {"rosto": 0.0, "cta": 0.2, "produto": 0.0})


def simpson(n: int = 2000, seed: int = 0) -> World:
    """Rosto dá +15% em TODO país, mas o país de CTR alto quase não usa rosto.

    BR: CTR base 2,4% e só 15% dos criativos com rosto.
    MX: CTR base 0,8% e 85% dos criativos com rosto.
    """
    rng = random.Random(seed)
    perfil = {"BR": (0.024, 0.15), "MX": (0.008, 0.85)}  # (CTR base, % com rosto)
    specs, rows, country = [], [], {}
    for i in range(1, n + 1):
        pais = "BR" if i % 2 else "MX"
        base, chance_rosto = perfil[pais]
        face = rng.random() < chance_rosto
        spec = _spec(i, face, rng.random() < 0.5, rng.random() < 0.5)
        specs.append(spec)
        rows.append(_row(rng, spec.creative_id, base * (1.15 if face else 1.0)))
        country[spec.creative_id] = pais
    return World(specs, rows, country, {"rosto": 0.15, "cta": 0.0, "produto": 0.0})


def giant(n: int = 300, seed: int = 0) -> World:
    """Nenhuma etiqueta muda o CTR. Mas UM criativo com produto recebeu
    metade de todas as impressões e, por acaso, foi 80% melhor que a média."""
    rng = random.Random(seed)
    specs = [
        _spec(i, rng.random() < 0.5, rng.random() < 0.5, rng.random() < 0.5)
        for i in range(2, n + 1)
    ]
    rows = [_row(rng, s.creative_id, BASE_CTR) for s in specs]
    gigante = _spec(1, False, True, False)
    total = sum(r.impressions for r in rows)
    specs.insert(0, gigante)
    rows.insert(0, _row(rng, gigante.creative_id, BASE_CTR * 1.8, impressions=total))
    country = {s.creative_id: "BR" for s in specs}
    return World(specs, rows, country, {"rosto": 0.0, "cta": 0.0, "produto": 0.0})


def noisy(n: int = 200, seed: int = 0, spread: float = 0.3) -> World:
    """Nenhuma etiqueta muda o CTR, mas cada criativo tem seu próprio "jeito":
    um CTR que varia ~30% para cima ou para baixo, sem relação com etiqueta."""
    rng = random.Random(seed)
    specs = generate_specs(n, seed=seed)  # cores e formatos variados: 9 comparações
    rows = [
        _row(rng, s.creative_id, BASE_CTR * max(0.1, rng.gauss(1.0, spread)))
        for s in specs
    ]
    country = {s.creative_id: "BR" for s in specs}
    return World(specs, rows, country, {"rosto": 0.0, "cta": 0.0, "produto": 0.0})


def simple_lift(world: World, tag: str, keep=None) -> float:
    """O lift que a análise simples mede para uma etiqueta sim/não.

    `keep` filtra os criativos antes (ex.: só um país): é o "olhar por dentro".
    """
    column = {"rosto": "has_face", "produto": "has_product", "cta": "has_cta"}[tag]
    clicks = {True: 0, False: 0}
    impressions = {True: 0, False: 0}
    for s, r in zip(world.specs, world.rows):
        if keep is None or keep(s, world.country[s.creative_id]):
            has = getattr(s, column)
            clicks[has] += r.clicks
            impressions[has] += r.impressions
    ctr_yes = clicks[True] / impressions[True]
    ctr_no = clicks[False] / impressions[False]
    return ctr_yes / ctr_no - 1


def false_alarms(world: World, n_boot: int = 100) -> int:
    """Quantas etiquetas a análise simples chama de "efeito real" (todas são falsas
    quando o gabarito é zero para tudo, como no mundo `noisy`)."""
    return sum(
        r.significant for r in bootstrap_lifts(world.specs, world.rows, n_boot=n_boot)
    )


if __name__ == "__main__":
    print(
        f"{'armadilha':<12}{'etiqueta':<10}{'real':>8}{'medido':>9}  olhando por dentro"
    )
    c = confounded()
    dentro = simple_lift(c, "rosto", keep=lambda s, _: s.has_cta)
    print(
        f"{'confounded':<12}{'rosto':<10}{0:>+8.0%}{simple_lift(c, 'rosto'):>+9.1%}"
        f"  só com CTA: {dentro:+.1%}"
    )
    s = simpson()
    br = simple_lift(s, "rosto", keep=lambda _, p: p == "BR")
    mx = simple_lift(s, "rosto", keep=lambda _, p: p == "MX")
    print(
        f"{'simpson':<12}{'rosto':<10}{0.15:>+8.0%}{simple_lift(s, 'rosto'):>+9.1%}"
        f"  BR: {br:+.1%} | MX: {mx:+.1%}"
    )
    g = giant()
    sem = simple_lift(g, "produto", keep=lambda s, _: s.creative_id != "CR0001")
    print(
        f"{'giant':<12}{'produto':<10}{0:>+8.0%}{simple_lift(g, 'produto'):>+9.1%}"
        f"  sem a peça gigante: {sem:+.1%}"
    )
    alarmes = [false_alarms(noisy(seed=k)) for k in range(20)]
    com_alarme = sum(a > 0 for a in alarmes)
    print(
        f"{'noisy':<12}{'todas':<10}{0:>+8.0%}{'':>9}"
        f"  {com_alarme} de 20 análises acusaram efeito que não existe"
    )
