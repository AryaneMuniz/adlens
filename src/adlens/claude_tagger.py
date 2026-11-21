"""ClaudeTagger: o etiquetador que usa a IA de visão do Claude.

Ele segue o mesmo contrato dos outros etiquetadores (`Tagger`), então o
resto do adlens não muda nada. O cuidado aqui é o CUSTO, porque cada
chamada à IA é paga:

1. Uma chamada por imagem, pedindo todas as etiquetas de uma vez.
2. O formato não vai para a IA: sai do tamanho da imagem, de graça e sem erro.
3. A imagem é reduzida antes de ir (imagem menor = menos tokens).
4. Modelo rápido primeiro; o modelo forte só entra quando o rápido diz
   que não tem certeza.
5. Cache pelo conteúdo da imagem: a mesma peça nunca é paga duas vezes,
   nem em outra execução.
"""

import base64
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from PIL import Image

from adlens.synthetic import CreativeSpec
from adlens.tagging import format_of

FAST_MODEL = "claude-haiku-5-5"
STRONG_MODEL = "claude-opus-5-5"
MAX_SIDE = 512  # maior lado da imagem enviada, em pixels
CACHE_VERSION = "v1"  # mudou o pedido à IA? suba a versão e o cache antigo cai

# Quanto o modelo "pensa" antes de responder: pouco no rápido, médio no forte
EFFORT = {FAST_MODEL: "low", STRONG_MODEL: "medium"}

INSTRUCTIONS = """Você etiqueta criativos de anúncios. Olhe a imagem e responda:
- has_face: aparece o rosto de uma pessoa?
- has_product: aparece um produto (frasco, embalagem, pote)?
- has_cta: aparece um botão ou chamada para ação (ex.: "Compre já")?
- dominant_color: a cor que ocupa a maior área do fundo.
- confidence: de 0 a 1, o quanto você tem certeza de TODAS as respostas.
Na dúvida, diga a resposta mais provável e baixe a confidence."""

# O formato da resposta: a API garante que o JSON volta exatamente assim
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "has_face": {"type": "boolean"},
        "has_product": {"type": "boolean"},
        "has_cta": {"type": "boolean"},
        "dominant_color": {"type": "string", "enum": list(CreativeSpec.COLORS)},
        "confidence": {"type": "number"},
    },
    "required": ["has_face", "has_product", "has_cta", "dominant_color", "confidence"],
    "additionalProperties": False,
}


class TaggingError(Exception):
    """A IA não conseguiu etiquetar (recusou, cortou a resposta etc.)."""


@dataclass
class Usage:
    """Quanto cada modelo foi usado: a base para medir o custo."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class ClaudeTagger:
    """Etiqueta criativos com o Claude, gastando o mínimo possível.

    `client` é o cliente da API da Anthropic. Nos testes, passamos um
    cliente de mentira, que responde sem internet e sem custo.
    """

    def __init__(
        self,
        client: Any = None,
        cache_path: Path | None = None,
        min_confidence: float = 0.7,
        fast_model: str = FAST_MODEL,
        strong_model: str = STRONG_MODEL,
    ):
        if client is None:
            # Lê a chave da variável ANTHROPIC_API_KEY. Espera no máximo 60 s
            # por resposta e tenta de novo só 2 vezes, para não travar
            client = anthropic.Anthropic(timeout=60, max_retries=2)
        self._client = client
        self._cache_path = cache_path
        self._min_confidence = min_confidence
        self._fast_model = fast_model
        self._strong_model = strong_model
        self._cache = _read_cache(cache_path)
        self.cache_hits = 0
        self.usage: dict[str, Usage] = {}

    def tag(self, image_path: Path, creative_id: str) -> CreativeSpec:
        data = image_path.read_bytes()
        key = hashlib.sha256(CACHE_VERSION.encode() + data).hexdigest()
        answer = self._cache.get(key)
        if answer is None:
            answer = self._ask_ai(data)
            self._remember(key, answer)
        else:
            self.cache_hits += 1
        return CreativeSpec(
            creative_id=creative_id,
            has_face=answer["has_face"],
            has_product=answer["has_product"],
            has_cta=answer["has_cta"],
            dominant_color=answer["dominant_color"],
            format=answer["format"],
        )

    def _ask_ai(self, data: bytes) -> dict[str, Any]:
        """Pergunta ao modelo rápido e, se ele tiver dúvida, ao forte."""
        with Image.open(io.BytesIO(data)) as img:
            image_format = format_of(*img.size)
            image_b64 = _shrink(img)
        answer = self._call(self._fast_model, image_b64)
        if answer["confidence"] < self._min_confidence:
            answer = self._call(self._strong_model, image_b64)
        answer["format"] = image_format
        return answer

    def _call(self, model: str, image_b64: str) -> dict[str, Any]:
        """Uma chamada à API: manda a imagem e recebe o JSON das etiquetas."""
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": 4000,
            "system": INSTRUCTIONS,
            "output_config": {
                "effort": EFFORT.get(model, "low"),
                "format": {"type": "json_schema", "schema": ANSWER_SCHEMA},
            },
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": "Etiquete este criativo."},
                    ],
                }
            ],
        }
        if model == self._strong_model:
            # Se o modelo forte recusar por engano, a API tenta outro sozinha
            request["betas"] = ["server-side-fallback-2026-07-01"]
            request["fallbacks"] = "default"
        response = self._client.beta.messages.create(**request)

        if response.stop_reason == "refusal":
            raise TaggingError(f"O {model} se recusou a etiquetar esta imagem.")
        if response.stop_reason == "max_tokens":
            raise TaggingError(f"A resposta do {model} foi cortada no meio.")
        self._count(model, response.usage)
        text = next(b.text for b in response.content if b.type == "text")
        answer = json.loads(text)
        answer["confidence"] = min(max(float(answer["confidence"]), 0.0), 1.0)
        answer["model"] = model
        return answer

    def _count(self, model: str, usage: Any) -> None:
        total = self.usage.setdefault(model, Usage())
        total.calls += 1
        total.input_tokens += usage.input_tokens
        total.output_tokens += usage.output_tokens

    def _remember(self, key: str, answer: dict[str, Any]) -> None:
        """Guarda a resposta na memória e, se houver arquivo, no disco."""
        self._cache[key] = answer
        if self._cache_path is not None:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Uma linha por imagem, acrescentada na hora: se cair no meio,
            # o que já foi pago não se perde
            with self._cache_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, **answer}, ensure_ascii=False) + "\n")


def _shrink(img: Image.Image) -> str:
    """Reduz a imagem (sem distorcer) e devolve o PNG em base64."""
    small = img.convert("RGB")
    small.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    small.save(buffer, format="PNG")
    return base64.standard_b64encode(buffer.getvalue()).decode("ascii")


def _read_cache(path: Path | None) -> dict[str, dict[str, Any]]:
    """Lê o cache do disco: {chave da imagem: resposta}."""
    if path is None or not path.exists():
        return {}
    cache = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            cache[item.pop("key")] = item
    return cache
