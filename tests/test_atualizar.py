import json

from conftest import ClienteFalso
from megasena import atualizar, db
from megasena.coletor import Coletor


def coletar(raiz, ultimo):
    """Coleta concursos fictícios para data/megasena.db e data/raw/megasena."""
    conn = db.conectar(raiz / "data" / "megasena.db")
    Coletor(conn, ClienteFalso(ultimo=ultimo), raiz / "data" / "raw" / "megasena",
            pausa=0).coletar()
    conn.close()


def projeto(tmp_path, analises: dict[str, str]):
    """Projeto mínimo: base com 1 concurso, pasta analises/ e paineis.json."""
    (tmp_path / "data").mkdir()
    coletar(tmp_path, 1)
    pasta = tmp_path / "analises"
    pasta.mkdir()
    for nome, codigo in analises.items():
        (pasta / nome).write_text(codigo, encoding="utf-8")
    (tmp_path / "paineis.json").write_text(json.dumps({"paineis": [{
        "nome": "P", "url": "https://claude.ai/artifact/x",
        "datasets": {"d": "data/dashboard/d.json"}}]}), encoding="utf-8")
    return tmp_path


GERA_PAINEL = """
import os, pathlib, sqlite3
n = sqlite3.connect(os.environ["MEGASENA_DB"]).execute("SELECT COUNT(*) FROM concursos").fetchone()[0]
p = pathlib.Path("data/dashboard"); p.mkdir(parents=True, exist_ok=True)
(p / "d.json").write_text(str(n))
"""


def test_descobre_analises_em_ordem_e_ignora_underscore(tmp_path):
    projeto(tmp_path, {"b.py": "", "a.py": "", "_util.py": "", "nota.txt": ""})
    assert [p.name for p in atualizar.descobrir_analises(tmp_path)] == ["a.py", "b.py"]


def test_roda_analises_com_a_base_ativa_e_detecta_painel_pendente(tmp_path, monkeypatch):
    projeto(tmp_path, {"10_painel.py": GERA_PAINEL})
    monkeypatch.chdir(tmp_path)
    r = atualizar.atualizar(tmp_path, coletar=False)
    assert [e.status for e in r.etapas] == ["pulada", "ok", "ok"]
    assert (tmp_path / "data/dashboard/d.json").read_text() == "1"
    assert [(p.dataset, p.arquivo) for p in r.paineis_pendentes] == [("d", "data/dashboard/d.json")]
    resumo = json.loads((tmp_path / "data/atualizacao.json").read_text(encoding="utf-8"))
    assert resumo["concursos"] == 1

    assert len(atualizar.marcar_publicado(tmp_path)) == 1
    assert atualizar.paineis_pendentes(tmp_path) == ([], [])

    # base muda -> painel volta a ficar pendente
    coletar(tmp_path, 2)
    r = atualizar.atualizar(tmp_path, coletar=False)
    assert len(r.paineis_pendentes) == 1


def test_analise_com_erro_nao_impede_as_demais(tmp_path, monkeypatch):
    projeto(tmp_path, {"a.py": "raise SystemExit(3)", "b.py": GERA_PAINEL})
    monkeypatch.chdir(tmp_path)
    r = atualizar.atualizar(tmp_path, coletar=False)
    assert [e.status for e in r.etapas] == ["pulada", "ok", "erro", "ok"]
    assert atualizar.codigo_saida(r) == 1


def test_arquivo_de_painel_nao_gerado_e_erro(tmp_path, monkeypatch):
    projeto(tmp_path, {})
    monkeypatch.chdir(tmp_path)
    r = atualizar.atualizar(tmp_path, coletar=False)
    assert r.etapas[-1].status == "erro"
    assert atualizar.codigo_saida(r) == 1


def test_coleta_com_api_fora_e_so_aviso(tmp_path, monkeypatch):
    projeto(tmp_path, {"p.py": GERA_PAINEL})
    monkeypatch.chdir(tmp_path)
    real = atualizar._rodar

    def falso(nome, cmd, raiz, env):
        if nome == "coleta":
            return atualizar.Etapa("coleta", "erro", codigo=2)
        return real(nome, cmd, raiz, env)

    monkeypatch.setattr(atualizar, "_rodar", falso)
    r = atualizar.atualizar(tmp_path, coletar=True)
    assert r.etapas[0].status == "aviso"
    assert atualizar.codigo_saida(r) == 0
