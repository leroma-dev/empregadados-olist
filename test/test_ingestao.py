"""Testes unitários de pipeline/ingestao.py.

Os nove .csv.gz são escritos pelo próprio teste, em tmp_path, com poucas linhas.
O banco também fica em tmp_path: conectar() é trocado por um que aponta para lá.
"""

import gzip

import duckdb
import pytest

from pipeline import db, ingestao


def _csv_gz(caminho, texto):
    with gzip.open(caminho, "wt", encoding="utf-8", newline="") as arq:
        arq.write(texto)


# Um CSV mínimo por arquivo do MAPA. Só o de pedidos importa para as asserções;
# os outros existem para a checagem de arquivos faltando passar.
CONTEUDO = {
    "olist_orders_dataset.csv.gz": (
        "order_id,customer_id,order_status,order_purchase_timestamp,"
        "order_approved_at,order_delivered_carrier_date,"
        "order_delivered_customer_date,order_estimated_delivery_date\n"
        # Pedido entregue, com todas as datas: a linha de referência.
        "p1,c1,delivered,2018-01-01 10:00:00,2018-01-01 11:00:00,"
        "2018-01-02 09:00:00,2018-01-05 15:00:00,2018-01-06 00:00:00\n"
        # Pedido cancelado, sem datas de envio nem de entrega: campo vazio vira nulo.
        "p2,c2,canceled,2018-01-03 10:00:00,,,,2018-01-10 00:00:00\n"
        # Mesma linha de p1 de novo: a ingestão NÃO deduplica, tem que manter.
        "p1,c1,delivered,2018-01-01 10:00:00,2018-01-01 11:00:00,"
        "2018-01-02 09:00:00,2018-01-05 15:00:00,2018-01-06 00:00:00\n"
    ),
    "olist_order_items_dataset.csv.gz": "order_id,order_item_id\np1,1\n",
    "olist_order_payments_dataset.csv.gz": "order_id,payment_sequential\np1,1\n",
    "olist_order_reviews_dataset.csv.gz": "review_id,order_id\nr1,p1\n",
    "olist_customers_dataset.csv.gz": (
        "customer_id,customer_zip_code_prefix\n"
        # CEP com zero à esquerda: a ingestão não converte número, o zero fica.
        "c1,01151\n"
    ),
    "olist_sellers_dataset.csv.gz": "seller_id\ns1\n",
    "olist_products_dataset.csv.gz": "product_id\nprod1\n",
    "product_category_name_translation.csv.gz": (
        "product_category_name,product_category_name_english\nbeleza,beauty\n"
    ),
    "olist_geolocation_dataset.csv.gz": "geolocation_zip_code_prefix\n01151\n",
}


def _preparar(monkeypatch, tmp_path, faltando=()):
    pasta_raw = tmp_path / "raw"
    pasta_raw.mkdir()
    for arquivo, texto in CONTEUDO.items():
        if arquivo not in faltando:
            _csv_gz(pasta_raw / arquivo, texto)
    banco = tmp_path / "teste.duckdb"

    monkeypatch.setattr(db, "PASTA_RAW", pasta_raw)
    monkeypatch.setattr(db, "conectar", lambda: duckdb.connect(str(banco)))
    return banco


def test_csv_vira_tabela_com_as_mesmas_linhas(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    ingestao.main()

    con = duckdb.connect(str(banco))
    try:
        # O CSV tem três linhas de pedido (uma repetida); a tabela tem as três.
        contagem = con.execute("SELECT count(*) FROM raw.pedidos").fetchone()[0]
        assert contagem == 3
    finally:
        con.close()


def test_todas_as_colunas_entram_como_texto(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    ingestao.main()

    con = duckdb.connect(str(banco))
    try:
        tipos = {
            linha[0]: linha[1]
            for linha in con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'raw' AND table_name = 'pedidos'"
            ).fetchall()
        }
        assert tipos  # a tabela existe e tem colunas
        assert set(tipos.values()) == {"VARCHAR"}
    finally:
        con.close()


def test_campo_vazio_vira_nulo_e_nao_texto_vazio(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    ingestao.main()

    con = duckdb.connect(str(banco))
    try:
        # p2 é o pedido cancelado, com data_aprovacao vazia no CSV.
        valor = con.execute(
            "SELECT order_approved_at FROM raw.pedidos WHERE order_id = 'p2'"
        ).fetchone()[0]
        assert valor is None
    finally:
        con.close()


def test_texto_que_parece_nulo_continua_texto(monkeypatch, tmp_path):
    # keep_default_na=False: só campo vazio vira nulo. "NA" e "null" são texto.
    conteudo = dict(CONTEUDO)
    conteudo["olist_orders_dataset.csv.gz"] = (
        "order_id,customer_id,order_status,order_purchase_timestamp,"
        "order_approved_at,order_delivered_carrier_date,"
        "order_delivered_customer_date,order_estimated_delivery_date\n"
        "p9,c9,NA,null,,,,2018-01-10 00:00:00\n"
    )
    banco = _preparar(monkeypatch, tmp_path)
    _csv_gz(db.PASTA_RAW / "olist_orders_dataset.csv.gz", conteudo["olist_orders_dataset.csv.gz"])

    ingestao.main()

    con = duckdb.connect(str(banco))
    try:
        status, compra = con.execute(
            "SELECT order_status, order_purchase_timestamp FROM raw.pedidos"
        ).fetchone()
        assert status == "NA"
        assert compra == "null"
    finally:
        con.close()


def test_cep_com_zero_a_esquerda_continua_igual(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    ingestao.main()

    con = duckdb.connect(str(banco))
    try:
        cep = con.execute(
            "SELECT customer_zip_code_prefix FROM raw.clientes"
        ).fetchone()[0]
        assert cep == "01151"
    finally:
        con.close()


def test_saida_tem_uma_linha_por_tabela_e_total(monkeypatch, tmp_path, capsys):
    _preparar(monkeypatch, tmp_path)

    ingestao.main()

    linhas = capsys.readouterr().out.strip().splitlines()
    # Nove tabelas + uma linha de total.
    assert len(linhas) == 10
    assert linhas[0].startswith("raw.pedidos")
    # Total = 3 (pedidos) + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 = 11.
    assert linhas[-1].endswith("11 registros")


def test_rodar_duas_vezes_imprime_exatamente_o_mesmo(monkeypatch, tmp_path, capsys):
    _preparar(monkeypatch, tmp_path)

    ingestao.main()
    primeira = capsys.readouterr().out
    ingestao.main()
    segunda = capsys.readouterr().out

    assert primeira == segunda
    assert primeira  # e não estava vazio


def test_arquivo_faltando_encerra_com_systemexit_e_nao_abre_banco(monkeypatch, tmp_path, capsys):
    faltando = ["olist_sellers_dataset.csv.gz"]
    banco = _preparar(monkeypatch, tmp_path, faltando=faltando)

    with pytest.raises(SystemExit) as saida:
        ingestao.main()

    assert saida.value.code == 1
    # Nada foi ingerido: o banco nem foi criado.
    assert not banco.exists()
    # A mensagem diz qual arquivo falta.
    assert "olist_sellers_dataset.csv.gz" in capsys.readouterr().out


def test_arquivo_faltando_nao_grava_nenhuma_tabela(monkeypatch, tmp_path):
    # Mesmo que o arquivo que falta seja o último da lista, nenhuma tabela
    # pode ter sido gravada antes da checagem.
    banco = _preparar(monkeypatch, tmp_path, faltando=["olist_geolocation_dataset.csv.gz"])

    with pytest.raises(SystemExit):
        ingestao.main()

    assert not banco.exists()
