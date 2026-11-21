# adlens 🔎

[![CI](https://github.com/AryaneMuniz/adlens/actions/workflows/ci.yml/badge.svg)](https://github.com/AryaneMuniz/adlens/actions/workflows/ci.yml)


🌐 **Hub:** https://aryanemuniz.github.io/adlens/


**Inteligência de criativos:** um etiquetador "olha" cada criativo de anúncio (rosto, produto, cor, formato, CTA) e o adlens cruza essas etiquetas com a performance para mostrar **quais características puxam o CTR**, com intervalo de confiança.


> 🚧 Piloto de aprendizado em engenharia de dados e IA.

## Por que existe

Ferramentas de mercado (como Segwise, VidMob e CreativeX) cobram para responder perguntas como *"criativos com rosto performam melhor?"*. O adlens é uma alternativa aberta, que pode rodar perto dos dados (BigQuery) sem enviar criativos para fora.

## Como funciona

```
criativos ──► etiquetador ──┐
                            ├──► lift por etiqueta + intervalo de 95% ──► relatório HTML
performance ────────────────┘
```

- **Dado sintético com gabarito:** criativos e performance são gerados por código com efeitos plantados (ex.: rosto = +15% de CTR). A análise não vê o gabarito e precisa redescobri-lo, o que prova que o sistema funciona. Nenhum dado de cliente entra neste repositório.
- **Etiquetadores trocáveis (SOLID):** todo etiquetador segue o mesmo contrato. Hoje existem o `PixelTagger` (lê os pixels das imagens sintéticas) e o `FakeTagger` (gabarito com erro opcional, para testes). Um etiquetador com IA de visão entra sem mudar o resto.
- **Efeito isolado (regressão):** o efeito de cada etiqueta é medido com todo o resto igual (outras etiquetas e país), cada criativo vale 1 voto e a correção de Benjamini-Hochberg evita alarme falso quando muitas etiquetas são testadas juntas. A comparação simples continua disponível com `--metodo simples`, para mostrar onde ela erra (`uv run python -m adlens.realistic`).
- **Honesto sobre a incerteza:** cada efeito vem com intervalo de 95%. Se não dá para afirmar o efeito, o adlens avisa.

## Como rodar

Pré-requisito: [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/AryaneMuniz/adlens.git
cd adlens
uv sync

uv run adlens gerar --n 1000 --imagens   # cria criativos, performance e imagens
uv run adlens etiquetar                  # etiqueta as imagens
uv run adlens analisar                   # mostra o lift de cada etiqueta (regressão)
uv run adlens relatorio                  # gera data/relatorio.html
uv run adlens exportar                   # tabelas do contrato em data/export/
uv run adlens painel                     # página com filtros (rascunho do Hub)
uv run adlens hub                        # site com abas em site/ (o GitHub Pages publica)
```

Para analisar só um recorte, use os filtros no `analisar` e no `relatorio`
(também valem nas ferramentas do MCP como `pais`, `plataforma`,
`data_inicio` e `data_fim`):

```bash
uv run adlens analisar --pais BR,MX --plataforma meta --de 2026-10-01 --ate 2026-10-15
uv run adlens relatorio --pais BR       # o relatório mostra o recorte no topo
```

O filtro corta a mídia diária antes de somar por anúncio: um criativo entra
só com os números do recorte. Recortes com menos de 30 criativos são
recusados, e um valor que não existe nos dados (ex.: `BRA`) gera um erro
que lista os disponíveis.

## Servidor MCP (agentes de IA)

Com `uv run adlens-mcp`, um agente de IA (Claude, Copilot...) consulta o
adlens sozinho. São seis ferramentas, todas com os filtros acima:

| Ferramenta | Para quê |
|---|---|
| `resumo_dos_dados` | Totais e o que existe para filtrar (países, plataformas, período) |
| `efeito_das_caracteristicas` | Quanto cada etiqueta muda o CTR, com intervalo de 95% |
| `distribuicao_das_etiquetas` | Quantos criativos e quanta mídia tem cada etiqueta (grupo pequeno = resultado frágil) |
| `top_criativos` | Os melhores ou piores criativos, com as etiquetas (exemplos, não prova) |
| `comparar` | O efeito de cada etiqueta em dois recortes (ex.: BR × MX) e se a diferença é real |
| `gerar_relatorio` | Grava o relatório HTML |

## Contrato de dados e página do Hub

O adlens entrega duas tabelas com formato combinado: `adlens_criativos` (uma linha por anúncio) e `adlens_efeitos` (uma linha por etiqueta, com o intervalo de 95%). Os tipos seguem o padrão do BigQuery e cada tabela vem com o schema em JSON. Detalhes em [docs/contrato-de-dados.md](docs/contrato-de-dados.md).

O comando `adlens painel` monta uma página com filtros de país e plataforma lendo **só** essas duas tabelas. Ela é o rascunho de uma página num hub de dashboards.

## Achado: etiquetador que erra esconde o efeito

| Etiquetador | Erro | Rosto (gabarito +15%) |
|---|---|---|
| pixel | 0% | +14,7% |
| fake | 10% | +11,6% |
| fake | 30% | +5,7% |

Etiqueta errada não inventa efeito: mistura os grupos e **encolhe** o efeito real. Antes de usar um etiquetador em dado real, é preciso medir a precisão dele.

- [x] Estrutura do projeto e fluxo de trabalho (branch, PR, testes)
- [x] Gerador de criativos e performance sintéticos
- [x] Análise de efeito por etiqueta com intervalo de confiança
- [x] Linha de comando e relatório HTML
- [x] Etiquetadores trocáveis (pixel e fake)
- [x] CI no GitHub Actions
- [x] Servidor MCP (agentes de IA consultando o adlens)
- [x] Mídia diária no formato de plataforma de anúncios
- [x] Contrato de dados pronto para o BigQuery
- [x] Página com filtros (rascunho para um hub de dashboards)
- [x] Hub com abas publicado automaticamente no GitHub Pages (CD)
- [x] Etiquetador com IA de visão (ClaudeTagger; precisão real a medir quando houver chave)
- [x] Simulação realista com as armadilhas do dado de verdade
- [x] Regressão: efeito isolado de cada etiqueta, controlando país, peso igual por criativo e correção para muitos testes
- [x] Regressão ligada à linha de comando, ao relatório, ao contrato, ao MCP e ao hub
- [x] Filtros por país, plataforma e período (linha de comando, relatório e MCP)
- [x] MCP: distribuição das etiquetas, ranking de criativos e comparação de recortes
- [ ] Dados no BigQuery e execução na nuvem

## Autora

Aryane Muniz · [LinkedIn](https://www.linkedin.com/in/aryanemuniz-ai) · [Portfólio](https://aryanemuniz.github.io)
