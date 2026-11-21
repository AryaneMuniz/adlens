"""Testes do ClaudeTagger, com um cliente de mentira (sem internet e sem custo)."""

import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from adlens.claude_tagger import (
    FAST_MODEL,
    MAX_SIDE,
    STRONG_MODEL,
    ClaudeTagger,
    TaggingError,
)
from adlens.render import render_creative
from adlens.synthetic import CreativeSpec

CERTO = {
    "has_face": True,
    "has_product": False,
    "has_cta": True,
    "dominant_color": "vermelho",
    "confidence": 0.9,
}


class FakeClient:
    """Imita o cliente da Anthropic: anota cada pedido e devolve a resposta
    combinada para cada modelo."""

    def __init__(self, answers: dict[str, dict], stop_reason: str = "end_turn"):
        self.calls: list[dict] = []
        self._answers = answers
        self._stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **request):
        self.calls.append(request)
        answer = self._answers[request["model"]]
        return SimpleNamespace(
            stop_reason=self._stop_reason,
            content=[SimpleNamespace(type="text", text=json.dumps(answer))],
            usage=SimpleNamespace(input_tokens=300, output_tokens=40),
        )


@pytest.fixture
def imagem(tmp_path):
    """Um criativo vertical (540 x 960) desenhado pelo adlens."""
    spec = CreativeSpec("CR0001", True, False, True, "vermelho", "vertical")
    return render_creative(spec, tmp_path / "CR0001.png")


def test_etiqueta_com_a_resposta_da_ia_e_formato_pelo_tamanho(imagem):
    tagger = ClaudeTagger(client=FakeClient({FAST_MODEL: CERTO}))
    etiqueta = tagger.tag(imagem, "CR0001")
    assert etiqueta == CreativeSpec("CR0001", True, False, True, "vermelho", "vertical")


def test_uma_chamada_por_imagem_com_resposta_em_json(imagem):
    client = FakeClient({FAST_MODEL: CERTO})
    ClaudeTagger(client=client).tag(imagem, "CR0001")
    assert len(client.calls) == 1
    assert client.calls[0]["output_config"]["format"]["type"] == "json_schema"


def test_imagem_vai_reduzida(imagem):
    client = FakeClient({FAST_MODEL: CERTO})
    ClaudeTagger(client=client).tag(imagem, "CR0001")
    enviada = client.calls[0]["messages"][0]["content"][0]["source"]["data"]
    with Image.open(io.BytesIO(base64.b64decode(enviada))) as img:
        assert max(img.size) <= MAX_SIDE


def test_confianca_baixa_chama_o_modelo_forte(imagem):
    duvida = {**CERTO, "has_face": False, "confidence": 0.3}
    client = FakeClient({FAST_MODEL: duvida, STRONG_MODEL: CERTO})
    etiqueta = ClaudeTagger(client=client).tag(imagem, "CR0001")
    assert [c["model"] for c in client.calls] == [FAST_MODEL, STRONG_MODEL]
    assert etiqueta.has_face is True  # valeu a resposta do forte


def test_confianca_alta_nao_chama_o_modelo_forte(imagem):
    client = FakeClient({FAST_MODEL: CERTO})
    ClaudeTagger(client=client).tag(imagem, "CR0001")
    assert [c["model"] for c in client.calls] == [FAST_MODEL]


def test_cache_evita_pagar_duas_vezes(imagem, tmp_path):
    cache = tmp_path / "cache.jsonl"
    client = FakeClient({FAST_MODEL: CERTO})
    primeiro = ClaudeTagger(client=client, cache_path=cache)
    primeiro.tag(imagem, "CR0001")
    primeiro.tag(imagem, "CR0001")
    # Outra execução (tagger novo) lendo o mesmo arquivo de cache
    segundo = ClaudeTagger(client=client, cache_path=cache)
    segundo.tag(imagem, "CR0001")
    assert len(client.calls) == 1
    assert primeiro.cache_hits == 1 and segundo.cache_hits == 1


def test_conta_o_uso_de_cada_modelo(imagem):
    tagger = ClaudeTagger(client=FakeClient({FAST_MODEL: CERTO}))
    tagger.tag(imagem, "CR0001")
    uso = tagger.usage[FAST_MODEL]
    assert (uso.calls, uso.input_tokens, uso.output_tokens) == (1, 300, 40)


@pytest.mark.parametrize("motivo", ["refusal", "max_tokens"])
def test_resposta_incompleta_vira_erro_claro(imagem, motivo):
    client = FakeClient({FAST_MODEL: CERTO}, stop_reason=motivo)
    with pytest.raises(TaggingError):
        ClaudeTagger(client=client).tag(imagem, "CR0001")
