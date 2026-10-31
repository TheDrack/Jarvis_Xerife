from pathlib import Path

from app.adapters.edge import portas_core
from app.adapters.edge.portas_visualizacao import _resumo

MACROS = Path(__file__).resolve().parents[3] / "data" / "portas" / "macros"


def test_catalogo_real_carrega_com_risco_declarado():
    catalogo = portas_core.carregar_macros(MACROS)
    assert "ler_titulo" in catalogo
    assert catalogo["ler_titulo"]["risco"] == "leitura"


def test_resumo_nao_expoe_passos_nem_valores():
    macro = portas_core.carregar_macros(MACROS)["ler_titulo"]
    resumo = _resumo(macro)
    assert "passos" not in resumo
    assert set(resumo) == {"nome", "descricao", "risco", "parametros", "dominios_permitidos"}


def test_macro_sem_risco_e_rejeitada(tmp_path: Path):
    (tmp_path / "sem.json").write_text(
        '{"nome":"sem","descricao":"d","parametros":{},"dominios_permitidos":[],"passos":[]}',
        encoding="utf-8",
    )
    import pytest

    with pytest.raises(ValueError, match="campo ausente 'risco'"):
        portas_core.carregar_macros(tmp_path)
