import json

import pytest

from conftest import ClienteFalso, json_concurso
from megasena import db
from megasena.coletor import Coletor, revalidar


def novo_coletor(conn, tmp_path, cliente):
    return Coletor(conn, cliente, tmp_path / "raw", pausa=0)


def test_baixa_tudo_e_grava(conn, tmp_path):
    cliente = ClienteFalso(ultimo=10)
    r = novo_coletor(conn, tmp_path, cliente).coletar()
    assert (r.ausentes, r.baixados, r.falhas) == (10, 10, {})
    assert db.numeros_existentes(conn) == set(range(1, 11))
    assert len(list((tmp_path / "raw").glob("*.json"))) == 10
    assert conn.execute("SELECT COUNT(*) FROM dezenas").fetchone()[0] == 60
    assert conn.execute("SELECT COUNT(*) FROM rateio").fetchone()[0] == 30


def test_guarda_as_duas_ordens(conn, tmp_path):
    novo_coletor(conn, tmp_path, ClienteFalso(ultimo=1)).coletar()
    esperado = json_concurso(1)
    crescente, sorteio = db.dezenas_gravadas(conn, 1)
    assert crescente == [int(d) for d in esperado["listaDezenas"]]
    assert sorteio == [int(d) for d in esperado["dezenasSorteadasOrdemSorteio"]]


def test_json_original_preservado_byte_a_byte(conn, tmp_path):
    cliente = ClienteFalso(ultimo=1)
    novo_coletor(conn, tmp_path, cliente).coletar()
    assert (tmp_path / "raw" / "000001.json").read_bytes() == cliente.concurso(1)


def test_segunda_execucao_nao_baixa_nada(conn, tmp_path):
    novo_coletor(conn, tmp_path, ClienteFalso(ultimo=5)).coletar()
    cliente = ClienteFalso(ultimo=5)
    r = novo_coletor(conn, tmp_path, cliente).coletar()
    assert r.ausentes == 0 and cliente.pedidos == []


def test_baixa_somente_novos(conn, tmp_path):
    novo_coletor(conn, tmp_path, ClienteFalso(ultimo=5)).coletar()
    cliente = ClienteFalso(ultimo=8)
    novo_coletor(conn, tmp_path, cliente).coletar()
    assert cliente.pedidos == [6, 7, 8]


def test_retoma_apos_falhas(conn, tmp_path):
    r = novo_coletor(conn, tmp_path, ClienteFalso(ultimo=6, falhar_em={3, 5})).coletar()
    assert set(r.falhas) == {3, 5}
    assert db.numeros_existentes(conn) == {1, 2, 4, 6}
    erros = conn.execute("SELECT concurso FROM coleta_log WHERE status='erro'").fetchall()
    assert {e[0] for e in erros} == {3, 5}

    cliente = ClienteFalso(ultimo=6)
    r = novo_coletor(conn, tmp_path, cliente).coletar()
    assert cliente.pedidos == [3, 5] and r.falhas == {}
    assert conn.execute("SELECT COUNT(*) FROM coleta_log WHERE status='erro'").fetchone()[0] == 0


def test_retoma_apos_interrupcao(conn, tmp_path):
    class Interrompe(ClienteFalso):
        def concurso(self, numero):
            if numero == 4:
                raise KeyboardInterrupt
            return super().concurso(numero)

    with pytest.raises(KeyboardInterrupt):
        novo_coletor(conn, tmp_path, Interrompe(ultimo=6)).coletar()
    assert db.numeros_existentes(conn) == {1, 2, 3}

    cliente = ClienteFalso(ultimo=6)
    novo_coletor(conn, tmp_path, cliente).coletar()
    assert cliente.pedidos == [4, 5, 6]


def test_reaproveita_json_local(conn, tmp_path):
    novo_coletor(conn, tmp_path, ClienteFalso(ultimo=3)).coletar()
    with conn:
        conn.execute("DELETE FROM concursos WHERE numero = 2")
    cliente = ClienteFalso(ultimo=3)
    r = novo_coletor(conn, tmp_path, cliente).coletar()
    assert cliente.pedidos == [] and r.do_cache == 1
    assert 2 in db.numeros_existentes(conn)


def test_json_local_corrompido_e_baixado_de_novo(conn, tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "000001.json").write_text("{ corrompido")
    cliente = ClienteFalso(ultimo=1)
    r = novo_coletor(conn, tmp_path, cliente).coletar()
    assert cliente.pedidos == [1] and r.baixados == 1


def test_rejeita_data_fora_de_sequencia(conn, tmp_path):
    class DataErrada(ClienteFalso):
        def concurso(self, numero):
            if numero == 3:
                return json.dumps(json_concurso(3, dataApuracao="12/03/1996")).encode()
            return super().concurso(numero)

    r = novo_coletor(conn, tmp_path, DataErrada(ultimo=5)).coletar()
    assert set(r.falhas) == {3}


def test_refazer_regrava_concurso(conn, tmp_path):
    novo_coletor(conn, tmp_path, ClienteFalso(ultimo=3)).coletar()
    cliente = ClienteFalso(ultimo=3)
    novo_coletor(conn, tmp_path, cliente).coletar(refazer=[2])
    assert cliente.pedidos == [2]
    assert conn.execute("SELECT COUNT(*) FROM dezenas WHERE concurso=2").fetchone()[0] == 6


def test_revalidar_detecta_adulteracao_e_buracos(conn, tmp_path):
    novo_coletor(conn, tmp_path, ClienteFalso(ultimo=4)).coletar()
    assert revalidar(conn, tmp_path / "raw") == []

    arq = tmp_path / "raw" / "000002.json"
    j = json.loads(arq.read_bytes())
    j["dataApuracao"] = "19/03/1996"
    arq.write_text(json.dumps(j))
    with conn:
        conn.execute("DELETE FROM concursos WHERE numero = 3")

    problemas = revalidar(conn, tmp_path / "raw")
    assert any(p.startswith("2: SHA-256") for p in problemas)
    assert any(p.startswith("2: data no banco") for p in problemas)
    assert any("ausentes no banco: 3" in p for p in problemas)
