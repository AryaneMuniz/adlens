"""Testes dos filtros (país, plataforma, período)."""

from datetime import date

import pytest

from adlens.analysis import analyze, build_database
from adlens.cli import main as cli
from adlens.filters import Filter, parse_filter
from adlens.media import available_values, performance_from_media
from adlens.storage import load_dataset


@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    """Uma pasta com 600 criativos e a mídia diária, gerada uma vez só."""
    destino = tmp_path_factory.mktemp("dados")
    cli(["gerar", "--n", "600", "--pasta", str(destino)])
    return destino


# --- montar o filtro a partir do texto -------------------------------------


def test_texto_vazio_e_sem_filtro():
    filtro = parse_filter("", None, "", None)
    assert filtro == Filter()
    assert not filtro.active
    assert filtro.describe() == "todos os dados"


def test_pais_maiusculo_plataforma_minuscula_sem_repetidos():
    filtro = parse_filter(" br, mx ,BR", "Meta,TIKTOK")
    assert filtro.countries == ("BR", "MX")
    assert filtro.platforms == ("meta", "tiktok")


def test_datas_viram_date_e_aparecem_na_descricao():
    filtro = parse_filter(start="2026-10-01", end="2026-10-15")
    assert filtro.start == date(2026, 10, 1)
    assert filtro.describe() == "de 2026-10-01 a 2026-10-15"


def test_data_em_formato_errado_explica_o_formato():
    with pytest.raises(ValueError, match="AAAA-MM-DD"):
        parse_filter(start="01/10/2026")


def test_inicio_depois_do_fim_e_erro():
    with pytest.raises(ValueError, match="depois da final"):
        parse_filter(start="2026-10-20", end="2026-10-01")


def test_where_usa_parametros_nunca_o_texto_colado():
    filtro = parse_filter("BR'; DROP TABLE x; --")
    sql, valores = filtro.where()
    assert "DROP" not in sql  # o texto vai como valor, não como SQL
    assert sql == "country IN (?)"
    assert valores == ["BR'; DROP TABLE X; --"]


# --- aplicar o filtro na mídia diária --------------------------------------


def test_disponivel_lista_paises_plataformas_e_periodo(pasta):
    existe = available_values(pasta / "midia_diaria.csv")
    assert existe["paises"] == ["AR", "BR", "CL", "CO", "MX", "PE"]
    assert existe["plataformas"] == ["dv360", "google", "meta", "tiktok"]
    assert existe["periodo"] == ["2026-10-01", "2026-10-30"]


def test_periodo_soma_so_os_dias_do_recorte(pasta):
    midia = pasta / "midia_diaria.csv"
    tudo = sum(r.impressions for r in performance_from_media(midia))
    metade = performance_from_media(midia, parse_filter(end="2026-10-15"))
    resto = performance_from_media(midia, parse_filter(start="2026-10-16"))
    # As duas metades somadas dão exatamente o total
    assert (
        sum(r.impressions for r in metade) + sum(r.impressions for r in resto) == tudo
    )


def test_filtro_de_pais_so_traz_criativos_daquele_pais(pasta):
    specs, rows, _ = load_dataset(pasta, parse_filter("BR"))
    ids_br = {
        linha.split(",")[5]
        for linha in (pasta / "midia_diaria.csv")
        .read_text(encoding="utf-8")
        .splitlines()[1:]
        if linha.split(",")[3] == "BR"
    }
    assert {s.creative_id for s in specs} == ids_br
    assert {r.creative_id for r in rows} == ids_br


def test_pais_que_nao_existe_lista_os_disponiveis(pasta):
    with pytest.raises(ValueError, match="Disponíveis: AR, BR, CL, CO, MX, PE"):
        load_dataset(pasta, parse_filter("BRA"))


def test_recorte_pequeno_demais_e_recusado(pasta):
    filtro = parse_filter("BR", "meta", "2026-10-01", "2026-10-01")
    with pytest.raises(ValueError, match="mínimo para uma análise confiável"):
        load_dataset(pasta, filtro)


def test_filtro_sem_midia_diaria_explica(pasta, tmp_path):
    for nome in ("criativos.csv", "performance.csv"):
        (tmp_path / nome).write_bytes((pasta / nome).read_bytes())
    with pytest.raises(ValueError, match="midia_diaria.csv"):
        load_dataset(tmp_path, parse_filter("BR"))


def test_analise_ignora_etiqueta_sem_grupo_de_referencia(pasta):
    specs, rows, _ = load_dataset(pasta)
    sem_azul = [s for s in specs if s.dominant_color != "azul"]
    resultados = analyze(build_database(sem_azul, rows))
    assert not [r for r in resultados if r.tag == "cor"]  # cor some, sem quebrar
    assert [r for r in resultados if r.tag == "rosto"]


# --- na linha de comando ----------------------------------------------------


def test_analisar_com_filtro_mostra_o_recorte(pasta, capsys):
    argv = ["analisar", "--pasta", str(pasta), "--pais", "br,mx"]
    assert cli([*argv, "--plataforma", "meta,tiktok"]) == 0
    saida = capsys.readouterr().out
    assert "Recorte: país BR, MX · plataforma meta, tiktok" in saida
    assert "rosto" in saida


def test_analisar_com_pais_errado_avisa(pasta, capsys):
    assert cli(["analisar", "--pasta", str(pasta), "--pais", "BRA"]) == 1
    assert "País sem dados: BRA" in capsys.readouterr().out


def test_relatorio_com_filtro_mostra_o_recorte(pasta):
    saida = pasta / "relatorio_br.html"
    argv = ["relatorio", "--pasta", str(pasta), "--saida", str(saida)]
    assert cli([*argv, "--pais", "BR"]) == 0
    assert "recorte: país BR" in saida.read_text(encoding="utf-8")


def test_erro_de_filtro_tem_nome_proprio_e_continua_sendo_valueerror(pasta):
    from adlens.filters import FilterError

    with pytest.raises(FilterError):
        load_dataset(pasta, parse_filter("BRA"))
    assert issubclass(FilterError, ValueError)
