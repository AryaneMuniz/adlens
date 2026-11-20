"""Testes da linha de comando."""

from adlens.cli import main


def test_gerar_cria_os_dois_csvs(tmp_path):
    codigo = main(["gerar", "--n", "30", "--pasta", str(tmp_path)])
    assert codigo == 0
    assert (tmp_path / "criativos.csv").exists()
    assert (tmp_path / "performance.csv").exists()


def test_gerar_com_imagens_desenha_um_png_por_criativo(tmp_path):
    main(["gerar", "--n", "5", "--pasta", str(tmp_path), "--imagens"])
    assert len(list((tmp_path / "imagens").glob("*.png"))) == 5


def test_analisar_mostra_a_tabela(tmp_path, capsys):
    main(["gerar", "--n", "300", "--pasta", str(tmp_path)])
    codigo = main(["analisar", "--pasta", str(tmp_path), "--boot", "30"])
    saida = capsys.readouterr().out
    assert codigo == 0
    assert "rosto" in saida
    assert "intervalo de 95%" in saida


def test_analisar_sem_dados_avisa_e_retorna_erro(tmp_path, capsys):
    codigo = main(["analisar", "--pasta", str(tmp_path)])
    assert codigo == 1
    assert "adlens gerar" in capsys.readouterr().out


def test_relatorio_gera_o_html(tmp_path):
    main(["gerar", "--n", "200", "--pasta", str(tmp_path), "--imagens"])
    codigo = main(["relatorio", "--pasta", str(tmp_path), "--boot", "20"])
    html = (tmp_path / "relatorio.html").read_text(encoding="utf-8")
    assert codigo == 0
    assert "adlens · relatório de criativos" in html
    assert 'src="imagens/CR0001.png"' in html


def test_relatorio_sem_dados_retorna_erro(tmp_path):
    assert main(["relatorio", "--pasta", str(tmp_path)]) == 1
