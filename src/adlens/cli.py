"""Linha de comando do adlens.

Exemplos:
    adlens gerar --n 500 --imagens
    adlens etiquetar --etiquetador pixel
    adlens analisar
    adlens relatorio
"""

import argparse
import os
from pathlib import Path

from adlens.confidence import bootstrap_lifts
from adlens.performance import PerformanceRow, save_csv, simulate_performance
from adlens.render import render_all
from adlens.report import THEMES, build_report, save_report
from adlens.storage import load_dataset, load_specs, save_specs
from adlens.synthetic import CreativeSpec, generate_specs
from adlens.tagging import FakeTagger, PixelTagger, Tagger, tag_all

PASTA_PADRAO = Path("data")


def _carregar(pasta: Path) -> tuple[list[CreativeSpec], list[PerformanceRow]] | None:
    """Lê os dados da pasta; avisa e devolve None se faltar algum arquivo."""
    try:
        specs, rows, fonte = load_dataset(pasta)
    except FileNotFoundError as erro:
        print(f"ERRO: {erro}")
        return None
    print(f"Usando as etiquetas de: {fonte}")
    return specs, rows


def cmd_gerar(args: argparse.Namespace) -> int:
    """Gera criativos e performance sintéticos (e, se pedir, as imagens)."""
    pasta: Path = args.pasta
    specs = generate_specs(n=args.n, seed=args.seed)
    save_specs(specs, pasta / "criativos.csv")
    save_csv(simulate_performance(specs, seed=args.seed), pasta / "performance.csv")
    # Dados novos: as etiquetas antigas não valem mais
    (pasta / "etiquetas.csv").unlink(missing_ok=True)
    print(f"OK: {len(specs)} criativos e a performance salvos em {pasta.resolve()}")
    if args.imagens:
        render_all(specs, pasta / "imagens")
        print(f"OK: {len(specs)} imagens desenhadas em {(pasta / 'imagens').resolve()}")
    return 0


def cmd_etiquetar(args: argparse.Namespace) -> int:
    """Etiqueta os criativos da pasta e salva em etiquetas.csv."""
    pasta: Path = args.pasta
    gabarito_csv, imagens = pasta / "criativos.csv", pasta / "imagens"
    if not gabarito_csv.exists():
        print("ERRO: Não achei os criativos. Rode antes: adlens gerar")
        return 1
    gabarito = load_specs(gabarito_csv)
    tagger: Tagger
    if args.etiquetador == "pixel":
        if not imagens.exists():
            print(
                "ERRO: O etiquetador pixel precisa das imagens: adlens gerar --imagens"
            )
            return 1
        tagger = PixelTagger()
    else:
        tagger = FakeTagger(gabarito, error_rate=args.erro, seed=args.seed)
    etiquetas = tag_all(tagger, [s.creative_id for s in gabarito], imagens)
    save_specs(etiquetas, pasta / "etiquetas.csv")
    acertos = sum(e == g for e, g in zip(etiquetas, gabarito))
    print(
        f"OK: {len(etiquetas)} criativos etiquetados ({args.etiquetador}); "
        f"{acertos / len(gabarito):.0%} com todas as etiquetas iguais ao gabarito"
    )
    return 0


def cmd_analisar(args: argparse.Namespace) -> int:
    """Mostra o lift de cada etiqueta, com o intervalo de 95%."""
    dados = _carregar(args.pasta)
    if dados is None:
        return 1
    resultados = bootstrap_lifts(*dados, n_boot=args.boot)
    print(f"{'etiqueta':<10}{'valor':<12}{'lift':>8}   intervalo de 95%     real?")
    for r in resultados:
        faixa = f"[{r.low:+.1%} a {r.high:+.1%}]"
        real = "sim" if r.significant else "não"
        print(f"{r.tag:<10}{r.value:<12}{r.lift:>+8.1%}   {faixa:<20} {real}")
    return 0


def cmd_relatorio(args: argparse.Namespace) -> int:
    """Gera o relatório HTML."""
    pasta: Path = args.pasta
    dados = _carregar(pasta)
    if dados is None:
        return 1
    specs, rows = dados
    intervalos = bootstrap_lifts(specs, rows, n_boot=args.boot)
    saida: Path = args.saida or pasta / "relatorio.html"
    # Até 8 imagens de exemplo, com o caminho relativo ao relatório
    pngs = sorted((pasta / "imagens").glob("*.png"))[:8]
    imagens = [os.path.relpath(p, saida.parent).replace("\\", "/") for p in pngs]
    html = build_report(intervalos, specs, rows, imagens, THEMES[args.tema])
    print(f"OK: relatório salvo em {save_report(html, saida).resolve()}")
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

    etiquetar = sub.add_parser("etiquetar", help="etiqueta os criativos")
    etiquetar.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    etiquetar.add_argument("--etiquetador", choices=["pixel", "fake"], default="pixel")
    etiquetar.add_argument("--erro", type=float, default=0.0, help="só no fake: 0 a 1")
    etiquetar.add_argument("--seed", type=int, default=0)
    etiquetar.set_defaults(func=cmd_etiquetar)

    analisar = sub.add_parser("analisar", help="calcula o lift de cada etiqueta")
    analisar.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    analisar.add_argument("--boot", type=int, default=300, help="sorteios do bootstrap")
    analisar.set_defaults(func=cmd_analisar)

    relatorio = sub.add_parser("relatorio", help="gera o relatório HTML")
    relatorio.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    relatorio.add_argument("--saida", type=Path, help="padrão: PASTA/relatorio.html")
    relatorio.add_argument("--boot", type=int, default=300)
    relatorio.add_argument("--tema", choices=sorted(THEMES), default="neutro")
    relatorio.set_defaults(func=cmd_relatorio)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada: lê o que foi digitado e chama o comando certo."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
