"""Testes unitários de pipeline/geolocalizacao.py.

A tabela raw.geolocalizacao é criada pelo teste, em tmp_path, com linhas inventadas.
Cada linha tem um comentário dizendo por que está ali.
"""

import duckdb
import pytest

from pipeline import db, geolocalizacao

COLUNAS_RAW = [
    "geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
    "geolocation_city", "geolocation_state",
]

# Um ponto de referência: CEP 01151 em São Paulo.
PONTO = {
    "geolocation_zip_code_prefix": "01151", "geolocation_lat": "-23.54",
    "geolocation_lng": "-46.64", "geolocation_city": "sao paulo",
    "geolocation_state": "SP",
}


def _preparar(monkeypatch, tmp_path, linhas=None, sem_raw=False, colunas=None):
    """Cria raw.geolocalizacao em tmp_path e aponta db.conectar para lá."""
    banco = tmp_path / "teste.duckdb"
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA raw")
    if not sem_raw:
        cols = colunas or COLUNAS_RAW
        definicao = ", ".join(f'"{c}" VARCHAR' for c in cols)
        con.execute(f'CREATE TABLE raw.geolocalizacao ({definicao})')
        for registro in (linhas if linhas is not None else [PONTO]):
            valores = [registro.get(c) for c in cols]
            marcas = ", ".join("?" for _ in cols)
            con.execute(f"INSERT INTO raw.geolocalizacao VALUES ({marcas})", valores)
    con.close()
    monkeypatch.setattr(db, "conectar", lambda: duckdb.connect(str(banco)))
    return banco


def _consulta(banco, sql):
    con = duckdb.connect(str(banco))
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _refined_existe(banco):
    return _consulta(
        banco,
        "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'refined'",
    )[0][0] == 1


def test_colunas_saem_com_o_nome_em_portugues(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    geolocalizacao.main()

    colunas = [
        linha[0]
        for linha in _consulta(
            banco,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'refined' AND table_name = 'geolocalizacao' "
            "ORDER BY ordinal_position",
        )
    ]
    assert colunas == ["cep_prefixo", "latitude", "longitude", "cidade", "uf"]


def test_linha_inteira_repetida_sai_e_e_contada(monkeypatch, tmp_path, capsys):
    # O mesmo ponto duas vezes, linha inteira igual: uma tem que sobrar.
    banco = _preparar(monkeypatch, tmp_path, linhas=[PONTO, PONTO])

    geolocalizacao.main()

    assert _consulta(banco, "SELECT count(*) FROM refined.geolocalizacao") == [(1,)]
    assert "(1 duplicatas)" in capsys.readouterr().out


def test_mesmo_cep_com_coordenadas_diferentes_nao_e_agregado(monkeypatch, tmp_path):
    # Dois pontos no mesmo CEP, coordenadas diferentes: são dois pontos observados.
    outro_ponto = {**PONTO, "geolocation_lat": "-23.55", "geolocation_lng": "-46.65"}
    banco = _preparar(monkeypatch, tmp_path, linhas=[PONTO, outro_ponto])

    geolocalizacao.main()

    assert _consulta(banco, "SELECT count(*) FROM refined.geolocalizacao") == [(2,)]


def test_cidade_com_e_sem_acento_sao_linhas_diferentes(monkeypatch, tmp_path):
    # A spec deixa 'sao paulo' e 'são paulo' como estão: não se normaliza texto.
    sem_acento = dict(PONTO)
    com_acento = {**PONTO, "geolocation_city": "são paulo"}
    banco = _preparar(monkeypatch, tmp_path, linhas=[sem_acento, com_acento])

    geolocalizacao.main()

    cidades = _consulta(banco, "SELECT cidade FROM refined.geolocalizacao ORDER BY cidade")
    assert cidades == [("sao paulo",), ("são paulo",)]


def test_latitude_e_longitude_viram_double(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    geolocalizacao.main()

    tipos = dict(_consulta(
        banco,
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'refined' AND table_name = 'geolocalizacao'",
    ))
    assert tipos["latitude"] == "DOUBLE"
    assert tipos["longitude"] == "DOUBLE"
    assert _consulta(banco, "SELECT latitude FROM refined.geolocalizacao") == [(-23.54,)]


def test_cep_continua_texto_com_zero_a_esquerda(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    geolocalizacao.main()

    tipo = _consulta(
        banco,
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'refined' AND table_name = 'geolocalizacao' "
        "AND column_name = 'cep_prefixo'",
    )[0][0]
    cep = _consulta(banco, "SELECT cep_prefixo FROM refined.geolocalizacao")[0][0]
    assert tipo == "VARCHAR"
    assert cep == "01151"


def test_coordenada_que_nao_converte_encerra_sem_virar_nulo(monkeypatch, tmp_path, capsys):
    # "vinte" não é número: o CAST tem que estourar, não devolver nulo.
    ruim = {**PONTO, "geolocation_lat": "vinte"}
    banco = _preparar(monkeypatch, tmp_path, linhas=[ruim])

    with pytest.raises(SystemExit) as saida:
        geolocalizacao.main()

    assert saida.value.code == 1
    texto = capsys.readouterr().out
    assert "geolocation_lat -> latitude" in texto
    assert "'vinte'" in texto
    assert not _refined_existe(banco)


def test_nulos_nao_apagam_a_linha_nem_sao_preenchidos(monkeypatch, tmp_path, capsys):
    # Cidade vazia no CSV: a linha fica e o nulo fica nulo.
    sem_cidade = {**PONTO, "geolocation_city": None}
    banco = _preparar(monkeypatch, tmp_path, linhas=[PONTO, sem_cidade])

    geolocalizacao.main()

    assert _consulta(banco, "SELECT count(*) FROM refined.geolocalizacao") == [(2,)]
    assert _consulta(
        banco, "SELECT count(*) FROM refined.geolocalizacao WHERE cidade IS NULL"
    ) == [(1,)]
    assert "cidade 1" in capsys.readouterr().out


def test_saida_tem_a_linha_da_tabela_e_o_total(monkeypatch, tmp_path, capsys):
    _preparar(monkeypatch, tmp_path, linhas=[PONTO, PONTO])

    geolocalizacao.main()

    linhas = capsys.readouterr().out.splitlines()
    assert linhas[0].startswith("refined.geolocalizacao")
    assert " ".join(linhas[0].split()) == (
        "refined.geolocalizacao 2 -> 1 linhas (1 duplicatas)"
    )
    assert linhas[-1] == "Total: 1 linhas"


def test_raw_continua_com_todas_as_linhas(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path, linhas=[PONTO, PONTO])

    geolocalizacao.main()

    assert _consulta(banco, "SELECT count(*) FROM raw.geolocalizacao") == [(2,)]


def test_rodar_duas_vezes_imprime_exatamente_o_mesmo(monkeypatch, tmp_path, capsys):
    banco = _preparar(monkeypatch, tmp_path, linhas=[PONTO, PONTO])

    geolocalizacao.main()
    primeira = capsys.readouterr().out
    geolocalizacao.main()
    segunda = capsys.readouterr().out

    assert primeira == segunda
    assert _consulta(banco, "SELECT count(*) FROM refined.geolocalizacao") == [(1,)]


def test_raw_faltando_encerra_e_manda_rodar_ingestao(monkeypatch, tmp_path, capsys):
    banco = _preparar(monkeypatch, tmp_path, sem_raw=True)

    with pytest.raises(SystemExit) as saida:
        geolocalizacao.main()

    assert saida.value.code == 1
    texto = capsys.readouterr().out
    assert "raw.geolocalizacao" in texto
    assert "pipeline.ingestao" in texto
    assert not _refined_existe(banco)


def test_coluna_fora_do_mapa_encerra_com_systemexit(monkeypatch, tmp_path, capsys):
    # Coluna sobrando no raw seria descartada em silêncio: o script tem que parar.
    banco = _preparar(monkeypatch, tmp_path, colunas=COLUNAS_RAW + ["extra"])

    with pytest.raises(SystemExit) as saida:
        geolocalizacao.main()

    assert saida.value.code == 1
    assert "extra" in capsys.readouterr().out
    assert not _refined_existe(banco)
