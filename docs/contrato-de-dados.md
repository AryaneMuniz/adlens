# Contrato de dados do adlens

O adlens entrega duas tabelas. Este documento é a "promessa" de como elas são: quem monta um dashboard em cima delas pode confiar nestas colunas, nestes tipos e neste significado.

- Os nomes e tipos ficam em `src/adlens/export.py`.
- `tests/test_export.py` trava o formato: mudar uma coluna sem querer deixa o CI vermelho.
- Um teste também confere se toda coluna está documentada aqui.

Gerar as tabelas:

```bash
uv run adlens gerar --n 1000
uv run adlens exportar        # cria data/export/
```

## `adlens_criativos`

**Uma linha por anúncio**, com as dimensões da mídia, as etiquetas e as métricas somadas no período.

| Coluna | Tipo | O que é |
|---|---|---|
| `run_id` | STRING | Identificador da execução do adlens (ex.: `20261120T183000Z`) |
| `ad_id` | STRING | ID do anúncio |
| `ad_name` | STRING | Nome do anúncio |
| `platform` | STRING | Plataforma de mídia |
| `country` | STRING | País |
| `campaign_name` | STRING | Nome da campanha |
| `image_url` | STRING | Link da imagem do criativo |
| `has_face` | BOOL | O criativo tem rosto |
| `has_product` | BOOL | O criativo mostra o produto |
| `has_cta` | BOOL | O criativo tem botão de chamada para ação |
| `dominant_color` | STRING | Cor dominante |
| `format` | STRING | Formato: quadrado, vertical ou horizontal |
| `impressions` | INT64 | Impressões no período |
| `clicks` | INT64 | Cliques no período |
| `investment` | FLOAT64 | Investimento no período |
| `ctr` | FLOAT64 | Cliques / impressões |
| `tag_source` | STRING | Arquivo de onde vieram as etiquetas |

## `adlens_efeitos`

**Uma linha por etiqueta** (ex.: rosto = sim, cor = vermelho), com o efeito no CTR e o intervalo de 95%.

| Coluna | Tipo | O que é |
|---|---|---|
| `run_id` | STRING | Identificador da execução do adlens |
| `run_at` | TIMESTAMP | Quando a análise rodou (UTC) |
| `tag` | STRING | Etiqueta: rosto, produto, cta, cor, formato |
| `value` | STRING | Valor da etiqueta comparado |
| `reference` | STRING | Valor de referência da comparação |
| `lift` | FLOAT64 | Quanto o CTR muda em relação à referência (0.15 = +15%) |
| `ci_low` | FLOAT64 | Limite inferior do intervalo de 95% |
| `ci_high` | FLOAT64 | Limite superior do intervalo de 95% |
| `significant` | BOOL | Dá para afirmar que o efeito existe. Na regressão: p-valor corrigido por Benjamini-Hochberg abaixo de 5% (mais exigente que "o intervalo não cruza o zero"). No simples: o intervalo não cruza o zero |
| `creatives` | INT64 | Quantos criativos têm esse valor |
| `method` | STRING | Como o efeito foi calculado: `regressao` (padrão, efeito isolado das outras etiquetas e do país) ou `simples` (comparação de grupos) |

## Regras

- **Execuções se acumulam.** Cada execução tem um `run_id` novo. Para mostrar o resultado atual, filtre pela execução mais recente:
  ```sql
  SELECT *
  FROM adlens_efeitos
  WHERE run_id = (SELECT MAX(run_id) FROM adlens_efeitos)
  ```
- **Mudar o contrato é uma decisão combinada.** Coluna nova no fim da tabela não quebra quem já consome. Renomear ou remover coluna quebra: só com aviso a quem usa as tabelas.
- **Booleanos** vêm como `true`/`false` e **vazio** significa sem valor.
- **Texto que parece fórmula ganha um apóstrofo.** Se um texto (ex.: `ad_name`) começa com `=`, `+`, `-`, `@`, tab ou quebra de linha, ele sai com `'` na frente (`'=HYPERLINK(...)`), para o Excel não executar como fórmula. Números não mudam: um `lift` de `-0.05` continua `-0.05`.

## Carregar no BigQuery

Cada tabela vem com o schema em JSON (`schema_adlens_*.json`). Com um dataset de testes (sandbox):

```bash
bq load --source_format=CSV --skip_leading_rows=1 \
  SEU_PROJETO:SEU_DATASET.adlens_efeitos \
  data/export/adlens_efeitos.csv data/export/schema_adlens_efeitos.json
```

O mesmo vale para `adlens_criativos`. Sem `--replace`, as execuções novas são acrescentadas às antigas.

## Página de exemplo

`uv run adlens painel` gera `data/export/painel.html`, uma página com filtros de país e plataforma montada **só** com estas duas tabelas. Ela serve de rascunho para a página oficial num hub de dashboards.
