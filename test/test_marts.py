"""Testes unitários de pipeline/marts.py e de dois marts (sql/marts/01 e 03).

Tudo roda em tmp_path: o banco é criado ali, os .sql de teste também.
As tabelas de refined são inventadas pelo teste, com poucas linhas.
"""

from datetime import date, datetime
from decimal import Decimal

import duckdb
import pytest

from pipeline import db, marts
from pipeline.transformacao import TABELAS

PASTA_SQL_REAL = marts.PASTA_MARTS  # os .sql de verdade, lidos mas não alterados


def _refined_vazio(con):
    # Para testes de execução: refined existe com as oito tabelas, sem linhas.
    con.execute("CREATE SCHEMA refined")
    for tabela in TABELAS:
        con.execute(f"CREATE TABLE refined.{tabela} (x INTEGER)")


def _preparar(monkeypatch, tmp_path, sqls, com_refined=True):
    """Cria o banco em tmp_path e uma pasta de .sql com o conteúdo dado."""
    banco = tmp_path / "teste.duckdb"
    pasta = tmp_path / "marts"
    pasta.mkdir()
    for nome, texto in sqls.items():
        (pasta / nome).write_text(texto, encoding="utf-8")

    con = duckdb.connect(str(banco))
    if com_refined:
        _refined_vazio(con)
    con.close()

    monkeypatch.setattr(db, "conectar", lambda: duckdb.connect(str(banco)))
    monkeypatch.setattr(marts, "PASTA_MARTS", pasta)
    return banco, pasta


def _tabelas_marts(banco):
    con = duckdb.connect(str(banco))
    try:
        return {
            linha[0]
            for linha in con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'marts'"
            ).fetchall()
        }
    finally:
        con.close()


def _schema_marts_existe(banco):
    con = duckdb.connect(str(banco))
    try:
        return con.execute(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'marts'"
        ).fetchone()[0] == 1
    finally:
        con.close()


def _linhas(banco, sql):
    con = duckdb.connect(str(banco))
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


# --- regras de execução -----------------------------------------------------

def test_sql_com_prefixo_vira_tabela_com_suas_linhas(monkeypatch, tmp_path, capsys):
    # "SELECT 1" devolve uma linha: o mart tem que nascer com uma linha.
    banco, _ = _preparar(monkeypatch, tmp_path, {"00_teste.sql": "SELECT 1 AS x"})

    marts.main()

    assert _linhas(banco, "SELECT x FROM marts.teste") == [(1,)]
    assert "✓ marts.teste" in capsys.readouterr().out


def test_arquivo_sem_prefixo_para_antes_de_executar(monkeypatch, tmp_path, capsys):
    # teste.sql sem prefixo: o 00_ ao lado não pode ser executado antes do erro.
    banco, _ = _preparar(
        monkeypatch, tmp_path,
        {"00_ok.sql": "SELECT 1 AS x", "teste.sql": "SELECT 1 AS x"},
    )

    with pytest.raises(SystemExit) as saida:
        marts.main()

    assert saida.value.code == 1
    assert "teste.sql" in capsys.readouterr().err
    assert not _schema_marts_existe(banco)


def test_prefixo_precisa_ter_exatamente_dois_digitos(monkeypatch, tmp_path):
    banco, _ = _preparar(monkeypatch, tmp_path, {"1_teste.sql": "SELECT 1 AS x"})

    with pytest.raises(SystemExit):
        marts.main()

    assert not _schema_marts_existe(banco)


def test_arquivo_apagado_faz_o_mart_sumir_na_execucao_seguinte(monkeypatch, tmp_path):
    banco, pasta = _preparar(
        monkeypatch, tmp_path,
        {"00_a.sql": "SELECT 1 AS x", "01_b.sql": "SELECT 2 AS x"},
    )
    marts.main()
    assert _tabelas_marts(banco) == {"a", "b"}

    (pasta / "01_b.sql").unlink()
    marts.main()

    assert _tabelas_marts(banco) == {"a"}


def test_erro_de_sintaxe_para_tudo_e_mostra_o_arquivo(monkeypatch, tmp_path, capsys):
    banco, pasta = _preparar(monkeypatch, tmp_path, {"00_teste.sql": "SELECT 1 AS x"})
    marts.main()
    (pasta / "01_ruim.sql").write_text("SELEC 1 AS x", encoding="utf-8")
    capsys.readouterr()

    with pytest.raises(SystemExit):
        marts.main()

    saida = capsys.readouterr()
    assert "01_ruim.sql" in saida.err
    assert "✓" not in saida.out


def test_erro_de_sintaxe_deixa_marts_como_estava_antes(monkeypatch, tmp_path):
    banco, pasta = _preparar(monkeypatch, tmp_path, {"00_teste.sql": "SELECT 7 AS x"})
    marts.main()
    (pasta / "01_ruim.sql").write_text("SELEC 1 AS x", encoding="utf-8")

    with pytest.raises(SystemExit):
        marts.main()

    # O 00_teste foi recriado antes do erro, mas a transação volta atrás.
    assert _linhas(banco, "SELECT x FROM marts.teste") == [(7,)]
    assert _tabelas_marts(banco) == {"teste"}


def test_mart_vazio_encerra_e_deixa_marts_como_estava(monkeypatch, tmp_path, capsys):
    banco, pasta = _preparar(monkeypatch, tmp_path, {"00_teste.sql": "SELECT 1 AS x"})
    marts.main()
    (pasta / "01_vazio.sql").write_text("SELECT 1 AS x WHERE false", encoding="utf-8")

    with pytest.raises(SystemExit):
        marts.main()

    assert _tabelas_marts(banco) == {"teste"}
    assert _linhas(banco, "SELECT x FROM marts.teste") == [(1,)]


def test_pasta_sem_nenhum_sql_encerra(monkeypatch, tmp_path):
    banco, _ = _preparar(monkeypatch, tmp_path, {})

    with pytest.raises(SystemExit):
        marts.main()

    assert not _schema_marts_existe(banco)


def test_refined_incompleto_encerra_e_manda_rodar_transformacao(monkeypatch, tmp_path, capsys):
    banco, _ = _preparar(monkeypatch, tmp_path, {"00_teste.sql": "SELECT 1 AS x"})
    con = duckdb.connect(str(banco))
    con.execute("DROP TABLE refined.pedidos")
    con.close()

    with pytest.raises(SystemExit):
        marts.main()

    erro = capsys.readouterr().err
    assert "pedidos" in erro
    assert "pipeline.transformacao" in erro
    assert not _schema_marts_existe(banco)


def test_dois_arquivos_com_o_mesmo_nome_de_tabela_encerram(monkeypatch, tmp_path, capsys):
    banco, _ = _preparar(
        monkeypatch, tmp_path,
        {"01_teste.sql": "SELECT 1 AS x", "02_teste.sql": "SELECT 2 AS x"},
    )

    with pytest.raises(SystemExit):
        marts.main()

    erro = capsys.readouterr().err
    assert "01_teste.sql" in erro and "02_teste.sql" in erro
    assert not _schema_marts_existe(banco)


def test_nome_com_hifen_vira_identificador_entre_aspas(monkeypatch, tmp_path):
    banco, _ = _preparar(monkeypatch, tmp_path, {"00_vendas-mensais.sql": "SELECT 1 AS x"})

    marts.main()

    assert _tabelas_marts(banco) == {"vendas-mensais"}


def test_nome_simples_sai_sem_aspas():
    assert marts.identificador("vendas_mensais") == "vendas_mensais"


def test_nome_com_caractere_especial_sai_entre_aspas():
    assert marts.identificador("vendas-mensais") == '"vendas-mensais"'


def test_saida_tem_uma_linha_por_mart_e_linha_final(monkeypatch, tmp_path, capsys):
    _preparar(
        monkeypatch, tmp_path,
        {"00_a.sql": "SELECT 1 AS x", "01_b.sql": "SELECT 1 AS x UNION ALL SELECT 2"},
    )

    marts.main()

    linhas = capsys.readouterr().out.splitlines()
    assert linhas[0].startswith("✓ marts.a")
    assert linhas[1].startswith("✓ marts.b")
    assert linhas[2] == "2 marts, 3 linhas"


def test_rodar_duas_vezes_imprime_exatamente_o_mesmo(monkeypatch, tmp_path, capsys):
    _preparar(monkeypatch, tmp_path, {"00_teste.sql": "SELECT 1 AS x"})

    marts.main()
    primeira = capsys.readouterr().out
    marts.main()
    segunda = capsys.readouterr().out

    assert primeira == segunda


# --- sql/marts/01 e 03 sobre tabelas inventadas -----------------------------
# Lê o .sql real do projeto e roda no banco do teste. Só o refined é inventado.

def _refined_pedidos(tmp_path, pedidos, itens=()):
    con = duckdb.connect(str(tmp_path / "m.duckdb"))
    con.execute("CREATE SCHEMA refined")
    con.execute(
        "CREATE TABLE refined.pedidos (pedido_id VARCHAR, cliente_id VARCHAR, "
        "status VARCHAR, data_compra TIMESTAMP, data_aprovacao TIMESTAMP, "
        "data_envio TIMESTAMP, data_entrega TIMESTAMP, data_entrega_prevista DATE)"
    )
    con.execute(
        "CREATE TABLE refined.itens_pedido (pedido_id VARCHAR, item_seq INTEGER, "
        "produto_id VARCHAR, vendedor_id VARCHAR, data_limite_envio TIMESTAMP, "
        "preco DECIMAL(10,2), frete DECIMAL(10,2))"
    )
    for p in pedidos:
        con.execute(
            "INSERT INTO refined.pedidos VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [p["pedido_id"], "c1", p["status"], p["data_compra"], None, None,
             p.get("data_entrega"), p["data_entrega_prevista"]],
        )
    for i in itens:
        con.execute(
            "INSERT INTO refined.itens_pedido VALUES (?, ?, 'prod1', 's1', NULL, ?, 0)",
            [i["pedido_id"], i["item_seq"], i["preco"]],
        )
    return con


def _rodar_mart(con, nome):
    sql = (PASTA_SQL_REAL / nome).read_text(encoding="utf-8").strip().removesuffix(";")
    return con.execute(sql).fetchall()


def _pedido(pedido_id, status="delivered", **extra):
    base = {
        "pedido_id": pedido_id, "status": status,
        "data_compra": datetime(2018, 1, 10, 9, 0, 0),
        "data_entrega_prevista": date(2018, 1, 20),
    }
    return {**base, **extra}


def test_pedido_com_dois_itens_conta_uma_vez_e_soma_os_dois_precos(tmp_path):
    # p1 tem dois itens (10,00 e 5,00): conta 1 pedido e receita 15,00.
    con = _refined_pedidos(
        tmp_path,
        [_pedido("p1")],
        itens=[
            {"pedido_id": "p1", "item_seq": 1, "preco": "10.00"},
            {"pedido_id": "p1", "item_seq": 2, "preco": "5.00"},
        ],
    )
    try:
        mes, pedidos, receita = _rodar_mart(con, "01_vendas_mensais.sql")[0]
    finally:
        con.close()

    assert mes == date(2018, 1, 1)
    assert pedidos == 1
    assert receita == Decimal("15.00")


def test_cancelado_fica_fora_da_receita(tmp_path):
    # p1 entregue, 10,00. p2 cancelado no mesmo mês, 99,00: não entra.
    con = _refined_pedidos(
        tmp_path,
        [_pedido("p1"), _pedido("p2", status="canceled")],
        itens=[
            {"pedido_id": "p1", "item_seq": 1, "preco": "10.00"},
            {"pedido_id": "p2", "item_seq": 1, "preco": "99.00"},
        ],
    )
    try:
        mes, pedidos, receita = _rodar_mart(con, "01_vendas_mensais.sql")[0]
    finally:
        con.close()

    assert pedidos == 1
    assert receita == Decimal("10.00")


def test_entrega_no_dia_previsto_a_tarde_esta_no_prazo(tmp_path):
    # Previsto para 20/01 (00:00). Entregue 20/01 às 15h: no prazo.
    con = _refined_pedidos(
        tmp_path,
        [_pedido("p1", data_entrega=datetime(2018, 1, 20, 15, 0, 0))],
    )
    try:
        entregues, no_prazo, atrasados, pct = _rodar_mart(con, "03_entrega_no_prazo.sql")[0]
    finally:
        con.close()

    assert entregues == 1
    assert no_prazo == 1
    assert atrasados == 0


def test_entrega_no_dia_seguinte_ao_previsto_esta_atrasada(tmp_path):
    con = _refined_pedidos(
        tmp_path,
        [_pedido("p1", data_entrega=datetime(2018, 1, 21, 9, 0, 0))],
    )
    try:
        entregues, no_prazo, atrasados, pct = _rodar_mart(con, "03_entrega_no_prazo.sql")[0]
    finally:
        con.close()

    assert no_prazo == 0
    assert atrasados == 1


def test_pedido_entregue_sem_data_de_entrega_fica_fora_do_calculo(tmp_path):
    # p2 está como delivered mas sem data_entrega (anomalia da Olist): não entra.
    con = _refined_pedidos(
        tmp_path,
        [
            _pedido("p1", data_entrega=datetime(2018, 1, 20, 15, 0, 0)),
            _pedido("p2", data_entrega=None),
        ],
    )
    try:
        entregues, no_prazo, atrasados, pct = _rodar_mart(con, "03_entrega_no_prazo.sql")[0]
    finally:
        con.close()

    assert entregues == 1
    assert no_prazo == 1


def test_pedido_cancelado_fica_fora_do_prazo(tmp_path):
    con = _refined_pedidos(
        tmp_path,
        [_pedido("p1", status="canceled")],
    )
    try:
        linhas = _rodar_mart(con, "03_entrega_no_prazo.sql")
    finally:
        con.close()

    # Sem nenhum entregue, o agregado ainda devolve uma linha; entregues é zero.
    assert linhas[0][0] == 0
