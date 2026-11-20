# adlens 🔎

**Inteligência de criativos:** uma IA de visão etiqueta cada criativo de anúncio (rosto, produto, cor, texto, formato, CTA) e o adlens cruza essas etiquetas com a performance para mostrar **quais características puxam CTR e conversão**.

> 🚧 Projeto em construção: piloto de aprendizado em engenharia de dados e IA.

## Por que existe

Ferramentas de mercado (como Segwise, VidMob e CreativeX) cobram para responder perguntas como *"criativos com rosto performam melhor?"*. O adlens é uma alternativa aberta, que roda perto dos dados (BigQuery) e não envia criativos para fora.

## Como funciona

```
criativos ──► etiquetagem (IA) ──┐
                                 ├──► análise de efeito ──► relatório / servidor MCP
performance ─────────────────────┘
```

- **Dado sintético na demonstração:** os criativos e a performance são gerados por código, com efeitos plantados de propósito. Se a análise encontrar o efeito plantado, o sistema está funcionando. Nenhum dado de cliente entra neste repositório.
- **Arquitetura em camadas (SOLID):** fonte de dados, etiquetador (IA) e armazenamento são peças trocáveis.

## Como rodar

Pré-requisito: [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/AryaneMuniz/adlens.git
cd adlens
uv sync
uv run adlens
```

## Roteiro

- [x] Estrutura do projeto
- [ ] Gerador de criativos e performance sintéticos
- [ ] Núcleo e etiquetador de testes
- [ ] Análise de efeito por etiqueta
- [ ] Linha de comando e relatório
- [ ] Etiquetagem com IA de visão
- [ ] Servidor MCP e CI
- [ ] Nuvem (BigQuery + Cloud Run) e documentação

## Autora

Aryane Muniz · [LinkedIn](https://www.linkedin.com/in/aryanemuniz-ai) · [Portfólio](https://aryanemuniz.github.io)
