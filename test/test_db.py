"""Testes unitários de pipeline/db.py. Nada aqui toca o olist.duckdb do projeto."""

import importlib
from pathlib import Path

import duckdb
import pandas as pd

from pipeline import db

RAIZ = Path(db.__file__).resolve().parent.parent
CONNECT_REAL = duckdb.connect


def test_importar_db_nao_abre_banco(monkeypatch):
    # Se importar o módulo abrisse o banco, o connect falso estouraria aqui.
    def proibido(*args, **kwargs):
        raise AssertionError("duckdb.connect não deveria ser chamado no import")

    monkeypatch.setattr(duckdb, "connect", proibido)
    importlib.reload(db)


def test_conectar_aponta_para_olist_na_raiz_do_projeto(monkeypatch, tmp_path):
    # Não abrimos o banco de verdade: o connect falso só anota o caminho
    # recebido e devolve um banco em memória.
    recebidos = []

    def falso_connect(caminho, *args, **kwargs):
        recebidos.append(caminho)
        return CONNECT_REAL(":memory:")

    monkeypatch.setattr(duckdb, "connect", falso_connect)
    monkeypatch.chdir(tmp_path)  # rodar de outra pasta não muda o destino

    con = db.conectar()
    con.close()

    assert recebidos == [str(RAIZ / "olist.duckdb")]
    assert not (tmp_path / "olist.duckdb").exists()


def test_criar_schema_pode_ser_chamado_duas_vezes(tmp_path):
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    try:
        db.criar_schema(con, "raw")
        db.criar_schema(con, "raw")  # segunda vez não pode dar erro
        schemas = {
            linha[0]
            for linha in con.execute("SELECT schema_name FROM information_schema.schemata").fetchall()
        }
        assert "raw" in schemas
    finally:
        con.close()


def test_gravar_devolve_a_contagem_do_banco_na_primeira_e_na_segunda_execucao(tmp_path):
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    try:
        db.criar_schema(con, "raw")
        df = pd.DataFrame({"a": ["1", "2", "3"]})  # três linhas inventadas
        assert db.gravar(con, df, "raw", "exemplo") == 3
        assert db.gravar(con, df, "raw", "exemplo") == 3
    finally:
        con.close()


def test_gravar_recria_a_tabela_e_nao_acrescenta(tmp_path):
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    try:
        db.criar_schema(con, "raw")
        db.gravar(con, pd.DataFrame({"a": ["1", "2", "3"]}), "raw", "exemplo")
        # Segunda gravação com duas linhas: tem que sobrar duas, não cinco.
        contagem = db.gravar(con, pd.DataFrame({"a": ["x", "y"]}), "raw", "exemplo")
        assert contagem == 2
        valores = con.execute('SELECT a FROM raw."exemplo" ORDER BY a').fetchall()
        assert valores == [("x",), ("y",)]
    finally:
        con.close()


def test_gravar_mantem_texto_como_varchar_e_nulo_como_null(tmp_path):
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    try:
        db.criar_schema(con, "raw")
        # "01151" é um CEP com zero à esquerda: tem que continuar texto.
        df = pd.DataFrame({"cep": ["01151", None]})
        db.gravar(con, df, "raw", "exemplo")
        tipo = con.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_name = 'exemplo'"
        ).fetchone()[0]
        valores = con.execute('SELECT cep FROM raw."exemplo" ORDER BY cep NULLS LAST').fetchall()
        assert tipo == "VARCHAR"
        assert valores == [("01151",), (None,)]
    finally:
        con.close()


def test_gravar_nao_deixa_view_nem_tabela_temporaria_para_tras(tmp_path):
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    try:
        db.criar_schema(con, "raw")
        db.gravar(con, pd.DataFrame({"a": ["1"]}), "raw", "exemplo")
        nomes = {
            linha[0]
            for linha in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
        }
        assert nomes == {"exemplo"}
    finally:
        con.close()
