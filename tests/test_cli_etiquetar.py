"""Testes do comando adlens etiquetar."""

from adlens.cli import main
from adlens.storage import load_specs


def test_etiquetar_pixel_bate_com_o_gabarito(tmp_path):
    main(["gerar", "--n", "40", "--pasta", str(tmp_path), "--imagens"])
    assert main(["etiquetar", "--pasta", str(tmp_path)]) == 0
    etiquetas = load_specs(tmp_path / "etiquetas.csv")
    assert etiquetas == load_specs(tmp_path / "criativos.csv")


def test_etiquetar_pixel_sem_imagens_avisa(tmp_path, capsys):
    main(["gerar", "--n", "10", "--pasta", str(tmp_path)])
    assert main(["etiquetar", "--pasta", str(tmp_path)]) == 1
    assert "--imagens" in capsys.readouterr().out


def test_etiquetar_fake_com_erro_muda_etiquetas(tmp_path):
    main(["gerar", "--n", "100", "--pasta", str(tmp_path)])
    main(
        [
            "etiquetar",
            "--pasta",
            str(tmp_path),
            "--etiquetador",
            "fake",
            "--erro",
            "0.3",
        ]
    )
    etiquetas = load_specs(tmp_path / "etiquetas.csv")
    assert etiquetas != load_specs(tmp_path / "criativos.csv")


def test_analisar_usa_as_etiquetas_quando_existem(tmp_path, capsys):
    main(["gerar", "--n", "100", "--pasta", str(tmp_path)])
    main(["etiquetar", "--pasta", str(tmp_path), "--etiquetador", "fake"])
    capsys.readouterr()
    main(["analisar", "--pasta", str(tmp_path), "--boot", "20"])
    assert "etiquetas.csv" in capsys.readouterr().out


def test_gerar_de_novo_apaga_etiquetas_antigas(tmp_path):
    main(["gerar", "--n", "20", "--pasta", str(tmp_path)])
    main(["etiquetar", "--pasta", str(tmp_path), "--etiquetador", "fake"])
    main(["gerar", "--n", "20", "--pasta", str(tmp_path)])
    assert not (tmp_path / "etiquetas.csv").exists()


def test_amostra_mede_precisao_sem_salvar_etiquetas(tmp_path, capsys):
    main(["gerar", "--n", "30", "--pasta", str(tmp_path)])
    capsys.readouterr()
    argv = ["etiquetar", "--pasta", str(tmp_path), "--etiquetador", "fake"]
    assert main([*argv, "--amostra", "10"]) == 0
    saida = capsys.readouterr().out
    assert "amostra de 10" in saida
    assert "100%" in saida
    assert not (tmp_path / "etiquetas.csv").exists()


def test_claude_sem_chave_avisa(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    main(["gerar", "--n", "5", "--pasta", str(tmp_path), "--imagens"])
    argv = ["etiquetar", "--pasta", str(tmp_path), "--etiquetador", "claude"]
    assert main(argv) == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out
