"""Linha de comando do adlens.

Exemplos:
    adlens gerar --n 500 --imagens
    adlens analisar
"""

import argparse
from pathlib import Path

from adlens.confidence import bootstrap_lifts
from adlens.performance import save_csv, simulate_performance
from adlens.render import render_all
from adlens.storage import load_performance, load_specs, save_specs
from adlens.synthetic import generate_specs

PASTA_PADRAO = Path("data")


def cmd_gerar(args: argparse.Namespace) -> int:
    """Gera criativos e performance sintéticos (e, se pedir, as imagens)."""
    pasta: Path = args.pasta
    specs = generate_specs(n=args.n, seed=args.seed)
    save_specs(specs, pasta / "criativos.csv")
    save_csv(simulate_performance(specs, seed=args.seed), pasta / "performance.csv")
    print(f"OK: {len(specs)} criativos e a performance salvos em {pasta.resolve()}")
    if args.imagens:
        render_all(specs, pasta / "imagens")
        print(f"OK: {len(specs)} imagens desenhadas em {(pasta / 'imagens').resolve()}")
    return 0


def cmd_analisar(args: argparse.Namespace) -> int:
    """Lê os CSVs da pasta e mostra o lift de cada etiqueta."""
    pasta: Path = args.pasta
    specs_csv, perf_csv = pasta / "criativos.csv", pasta / "performance.csv"
    if not specs_csv.exists() or not perf_csv.exists():
        print(
            f"ERRO: Não achei os dados em {pasta.resolve()}. Rode antes: adlens gerar"
        )
        return 1
    resultados = bootstrap_lifts(
        load_specs(specs_csv), load_performance(perf_csv), n_boot=args.boot
    )
    print(f"{'etiqueta':<10}{'valor':<12}{'lift':>8}   intervalo de 95%     real?")
    for r in resultados:
        faixa = f"[{r.low:+.1%} a {r.high:+.1%}]"
        real = "sim" if r.significant else "não"
        print(f"{r.tag:<10}{r.value:<12}{r.lift:>+8.1%}   {faixa:<20} {real}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Monta o "cardápio" de comandos e opções."""
    parser = argparse.ArgumentParser(
        prog="adlens",
        description="Inteligência de criativos: quais características puxam o CTR.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    gerar = sub.add_parser("gerar", help="gera dados sintéticos")
    gerar.add_argument("--n", type=int, default=1000, help="quantos criativos")
    gerar.add_argument("--seed", type=int, default=42, help="semente do sorteio")
    gerar.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    gerar.add_argument("--imagens", action="store_true", help="desenha os PNGs")
    gerar.set_defaults(func=cmd_gerar)

    analisar = sub.add_parser("analisar", help="calcula o lift de cada etiqueta")
    analisar.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    analisar.add_argument("--boot", type=int, default=300, help="sorteios do bootstrap")
    analisar.set_defaults(func=cmd_analisar)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada: lê o que foi digitado e chama o comando certo."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
