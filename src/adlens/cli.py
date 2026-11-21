"""Linha de comando do adlens.

Exemplos:
    adlens gerar --n 500 --imagens
    adlens etiquetar --etiquetador pixel
    adlens etiquetar --etiquetador claude --amostra 20
    adlens analisar
    adlens analisar --metodo simples --boot 300
    adlens relatorio
    adlens exportar
    adlens painel
    adlens hub
"""

import argparse
import os
from pathlib import Path

from adlens.confidence import Interval
from adlens.export import export_all
from adlens.hub import publish_hub
from adlens.media import save_media, simulate_media
from adlens.panel import build_panel, read_contract
from adlens.performance import PerformanceRow, save_csv, simulate_performance
from adlens.regression import METHODS, compute_effects
from adlens.render import render_all
from adlens.report import TEMA_PADRAO, THEMES, build_report, save_report
from adlens.storage import load_countries, load_dataset, load_specs, save_specs
from adlens.synthetic import CreativeSpec, generate_specs
from adlens.tagging import (
    FakeTagger,
    PixelTagger,
    Tagger,
    accuracy_by_tag,
    tag_all,
)

PASTA_PADRAO = Path("data")
EXTENSOES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".mov"}


def _carregar(pasta: Path) -> tuple[list[CreativeSpec], list[PerformanceRow]] | None:
    """Lê os dados da pasta; avisa e devolve None se faltar algum arquivo."""
    try:
        specs, rows, fonte = load_dataset(pasta)
    except FileNotFoundError as erro:
        print(f"ERRO: {erro}")
        return None
    print(f"Usando as etiquetas de: {fonte}")
    return specs, rows


def _efeitos(
    args: argparse.Namespace, specs: list[CreativeSpec], rows: list[PerformanceRow]
) -> list[Interval] | None:
    """Calcula os efeitos pelo método pedido; avisa e devolve None se não der."""
    try:
        return compute_effects(
            specs, rows, load_countries(args.pasta), args.metodo, args.boot
        )
    except ValueError as erro:  # ex.: poucos criativos, etiquetas sempre juntas
        print(f"ERRO: {erro}")
        return None


def cmd_gerar(args: argparse.Namespace) -> int:
    """Gera criativos e performance sintéticos (e, se pedir, as imagens)."""
    pasta: Path = args.pasta
    specs = generate_specs(n=args.n, seed=args.seed)
    save_specs(specs, pasta / "criativos.csv")
    save_csv(simulate_performance(specs, seed=args.seed), pasta / "performance.csv")
    save_media(simulate_media(specs, seed=args.seed), pasta / "midia_diaria.csv")
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
    if args.etiquetador != "fake" and not imagens.exists():
        print(
            f"ERRO: O etiquetador {args.etiquetador} precisa das imagens: "
            "adlens gerar --imagens"
        )
        return 1
    tagger: Tagger
    claude = None  # o ClaudeTagger, quando for ele (para mostrar o uso no fim)
    erros_da_ia: tuple[type[Exception], ...] = ()  # vazio = não captura nada
    if args.etiquetador == "pixel":
        tagger = PixelTagger()
    elif args.etiquetador == "claude":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "ERRO: O etiquetador claude precisa de uma chave de API na "
                "variável ANTHROPIC_API_KEY (nunca escreva a chave no código)."
            )
            return 1
        # Importa só aqui: a biblioteca anthropic leva dezenas de segundos para
        # carregar e só o etiquetador claude precisa dela
        from anthropic import AnthropicError

        from adlens.claude_tagger import ClaudeTagger, TaggingError

        claude = ClaudeTagger(cache_path=pasta / "cache_claude.jsonl")
        tagger = claude
        erros_da_ia = (TaggingError, AnthropicError)
    else:
        tagger = FakeTagger(gabarito, error_rate=args.erro, seed=args.seed)

    # Amostra: etiqueta só os N primeiros para medir a precisão antes de
    # pagar por tudo. Nesse caso NÃO salva etiquetas.csv (ficaria incompleto).
    alvo = gabarito[: args.amostra] if args.amostra > 0 else gabarito
    try:
        etiquetas = tag_all(tagger, [s.creative_id for s in alvo], imagens)
    except erros_da_ia as erro:
        print(f"ERRO: a IA não conseguiu etiquetar: {erro}")
        return 1

    if args.amostra > 0:
        print(f"OK: amostra de {len(etiquetas)} criativos ({args.etiquetador}).")
    else:
        save_specs(etiquetas, pasta / "etiquetas.csv")
        print(f"OK: {len(etiquetas)} criativos etiquetados ({args.etiquetador}).")
    print("Precisão de cada etiqueta (comparada com o gabarito):")
    for campo, precisao in accuracy_by_tag(etiquetas, alvo).items():
        print(f"  {campo:<16}{precisao:>6.0%}")
    if claude is not None:
        print(f"Vindos do cache (sem custo): {claude.cache_hits}")
        for modelo, uso in claude.usage.items():
            print(
                f"  {modelo}: {uso.calls} chamadas, {uso.input_tokens} tokens de "
                f"entrada, {uso.output_tokens} de saída"
            )
    return 0


def cmd_analisar(args: argparse.Namespace) -> int:
    """Mostra o lift de cada etiqueta, com o intervalo de 95%."""
    dados = _carregar(args.pasta)
    if dados is None:
        return 1
    resultados = _efeitos(args, *dados)
    if resultados is None:
        return 1
    print(f"Método: {args.metodo}")
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
    intervalos = _efeitos(args, specs, rows)
    if intervalos is None:
        return 1
    saida: Path = args.saida or pasta / "relatorio.html"
    # Até 12 criativos de exemplo (estáticos, GIFs ou vídeos), com o caminho
    # relativo ao relatório
    pecas = sorted(
        p for p in (pasta / "imagens").glob("*") if p.suffix.lower() in EXTENSOES
    )[:12]
    imagens = [os.path.relpath(p, saida.parent).replace("\\", "/") for p in pecas]
    html = build_report(intervalos, specs, rows, imagens, THEMES[args.tema])
    print(f"OK: relatório salvo em {save_report(html, saida).resolve()}")
    return 0


def cmd_exportar(args: argparse.Namespace) -> int:
    """Exporta as tabelas do contrato de dados (prontas para o BigQuery)."""
    pasta: Path = args.pasta
    try:
        arquivos = export_all(
            pasta, args.saida or pasta / "export", method=args.metodo, boot=args.boot
        )
    except (FileNotFoundError, ValueError) as erro:
        print(f"ERRO: {erro}")
        return 1
    for arquivo in arquivos:
        print(f"OK: {arquivo.resolve()}")
    return 0


def cmd_painel(args: argparse.Namespace) -> int:
    """Gera a página do Hub (rascunho) lendo só as tabelas do contrato."""
    pasta: Path = args.pasta
    try:
        criativos, efeitos = read_contract(pasta)
    except (FileNotFoundError, ValueError) as erro:
        print(f"ERRO: {erro}")
        return 1
    saida: Path = args.saida or pasta / "painel.html"
    html = build_panel(criativos, efeitos, THEMES[args.tema])
    print(f"OK: painel salvo em {save_report(html, saida).resolve()}")
    return 0


def cmd_hub(args: argparse.Namespace) -> int:
    """Gera o hub (site com abas) pronto para o GitHub Pages."""
    try:
        destino = publish_hub(
            args.pasta, args.saida, method=args.metodo, boot=args.boot
        )
    except (FileNotFoundError, ValueError) as erro:
        print(f"ERRO: {erro}")
        return 1
    print(f"OK: hub salvo em {destino.resolve()}")
    return 0


def _metodo(comando: argparse.ArgumentParser, boot: int) -> None:
    """As opções de método, iguais em todos os comandos que calculam efeitos."""
    comando.add_argument(
        "--metodo",
        choices=METHODS,
        default=METHODS[0],
        help="regressao (padrão, isola cada etiqueta) ou simples (comparação de grupos)",
    )
    comando.add_argument(
        "--boot", type=int, default=boot, help="só no simples: sorteios do bootstrap"
    )


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
    etiquetar.add_argument(
        "--etiquetador", choices=["pixel", "fake", "claude"], default="pixel"
    )
    etiquetar.add_argument("--erro", type=float, default=0.0, help="só no fake: 0 a 1")
    etiquetar.add_argument("--seed", type=int, default=0)
    etiquetar.add_argument(
        "--amostra", type=int, default=0, help="só mede a precisão nos N primeiros"
    )
    etiquetar.set_defaults(func=cmd_etiquetar)

    analisar = sub.add_parser("analisar", help="calcula o lift de cada etiqueta")
    analisar.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    _metodo(analisar, boot=300)
    analisar.set_defaults(func=cmd_analisar)

    relatorio = sub.add_parser("relatorio", help="gera o relatório HTML")
    relatorio.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    relatorio.add_argument("--saida", type=Path, help="padrão: PASTA/relatorio.html")
    _metodo(relatorio, boot=300)
    relatorio.add_argument("--tema", choices=sorted(THEMES), default=TEMA_PADRAO)
    relatorio.set_defaults(func=cmd_relatorio)

    exportar = sub.add_parser("exportar", help="exporta as tabelas do contrato")
    exportar.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    exportar.add_argument("--saida", type=Path, help="padrão: PASTA/export")
    _metodo(exportar, boot=300)
    exportar.set_defaults(func=cmd_exportar)

    painel = sub.add_parser("painel", help="gera a página do Hub (rascunho)")
    painel.add_argument("--pasta", type=Path, default=PASTA_PADRAO / "export")
    painel.add_argument("--saida", type=Path, help="padrão: PASTA/painel.html")
    painel.add_argument("--tema", choices=sorted(THEMES), default="neutro")
    painel.set_defaults(func=cmd_painel)

    hub = sub.add_parser("hub", help="gera o hub (site com abas)")
    hub.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    hub.add_argument("--saida", type=Path, default=Path("site"))
    _metodo(hub, boot=200)
    hub.set_defaults(func=cmd_hub)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada: lê o que foi digitado e chama o comando certo."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
