"""Testes unitários de pipeline/transformacao.py.

As oito tabelas de raw são criadas pelo teste, em tmp_path, com linhas inventadas.
Cada linha tem um comentário dizendo por que está ali.
"""

from datetime import date, datetime
from decimal import Decimal

import duckdb
import pytest

from pipeline import db, transformacao

# Uma linha válida por tabela de raw. Os testes trocam só o que precisam.
PEDIDO = {
    # Pedido entregue, com todas as datas preenchidas: linha de referência.
    "order_id": "p1", "customer_id": "c1", "order_status": "delivered",
    "order_purchase_timestamp": "2018-01-01 10:00:00",
    "order_approved_at": "2018-01-01 11:00:00",
    "order_delivered_carrier_date": "2018-01-02 09:00:00",
    "order_delivered_customer_date": "2018-01-05 15:00:00",
    "order_estimated_delivery_date": "2018-01-06 00:00:00",
}
ITEM = {  # um item do pedido p1, a 12,50
    "order_id": "p1", "order_item_id": "1", "product_id": "prod1",
    "seller_id": "s1", "shipping_limit_date": "2018-01-03 00:00:00",
    "price": "12.50", "freight_value": "3.00",
}
PAGAMENTO = {  # pagamento único do p1, à vista
    "order_id": "p1", "payment_sequential": "1", "payment_type": "credit_card",
    "payment_installments": "1", "payment_value": "15.50",
}
CLIENTE = {  # CEP com zero à esquerda: tem que continuar texto
    "customer_id": "c1", "customer_unique_id": "u1",
    "customer_zip_code_prefix": "01151", "customer_city": "sao paulo",
    "customer_state": "SP",
}
VENDEDOR = {
    "seller_id": "s1", "seller_zip_code_prefix": "01151",
    "seller_city": "sao paulo", "seller_state": "SP",
}
PRODUTO = {
    "product_id": "prod1", "product_category_name": "beleza_saude",
    "product_name_lenght": "40", "product_description_lenght": "300",
    "product_photos_qty": "2", "product_weight_g": "500",
    "product_length_cm": "20", "product_height_cm": "5", "product_width_cm": "15",
}
TRADUCAO = {
    "product_category_name": "beleza_saude",
    "product_category_name_english": "health_beauty",
}
AVALIACAO = {  # nota 5, sem título nem comentário: avaliação sem texto é normal
    "review_id": "r1", "order_id": "p1", "review_score": "5",
    "review_comment_title": None, "review_comment_message": None,
    "review_creation_date": "2018-01-10 00:00:00",
    "review_answer_timestamp": "2018-01-10 12:00:00",
}

PADRAO = {
    "pedidos": [PEDIDO],
    "itens_pedido": [ITEM],
    "pagamentos": [PAGAMENTO],
    "clientes": [CLIENTE],
    "vendedores": [VENDEDOR],
    "produtos": [PRODUTO],
    "traducao_categorias": [TRADUCAO],
    "avaliacoes": [AVALIACAO],
}


def _preparar(monkeypatch, tmp_path, **trocar):
    """Cria o raw em tmp_path. trocar: tabela -> lista de linhas, no lugar do padrão."""
    banco = tmp_path / "teste.duckdb"
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA raw")
    linhas_por_tabela = {**PADRAO, **trocar}
    for tabela, spec in transformacao.TABELAS.items():
        colunas = spec["colunas_raw"]
        definicao = ", ".join(f'"{c}" VARCHAR' for c in colunas)
        con.execute(f'CREATE TABLE raw."{tabela}" ({definicao})')
        for registro in linhas_por_tabela.get(tabela, []):
            valores = [registro.get(c) for c in colunas]
            marcas = ", ".join("?" for _ in colunas)
            con.execute(f'INSERT INTO raw."{tabela}" VALUES ({marcas})', valores)
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


# --- nomes ------------------------------------------------------------------

def test_colunas_de_pedidos_saem_com_o_nome_em_portugues(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    transformacao.main()

    colunas = [
        linha[0]
        for linha in _consulta(
            banco,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'refined' AND table_name = 'pedidos' "
            "ORDER BY ordinal_position",
        )
    ]
    assert colunas == [
        "pedido_id", "cliente_id", "status", "data_compra", "data_aprovacao",
        "data_envio", "data_entrega", "data_entrega_prevista",
    ]


def test_coluna_do_raw_fora_do_mapa_encerra_com_systemexit(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)
    con = duckdb.connect(str(banco))
    con.execute('ALTER TABLE raw.pedidos ADD COLUMN "coluna_sobrando" VARCHAR')
    con.close()

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    assert not _refined_existe(banco)


def test_tabela_do_raw_faltando_encerra_com_systemexit_e_manda_rodar_ingestao(
    monkeypatch, tmp_path, capsys
):
    banco = _preparar(monkeypatch, tmp_path)
    con = duckdb.connect(str(banco))
    con.execute("DROP TABLE raw.clientes")
    con.close()

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    saida_texto = capsys.readouterr().out
    assert "clientes" in saida_texto
    assert "ingestao" in saida_texto


# --- duplicatas -------------------------------------------------------------

def test_duplicata_exata_sai_e_e_contada(monkeypatch, tmp_path, capsys):
    # Mesmo pedido p1 duas vezes, linha inteira igual: uma tem que sobrar.
    banco = _preparar(monkeypatch, tmp_path, pedidos=[PEDIDO, PEDIDO])

    transformacao.main()

    assert _consulta(banco, "SELECT count(*) FROM refined.pedidos") == [(1,)]
    assert "(1 duplicatas)" in capsys.readouterr().out


def test_chave_repetida_com_conteudo_diferente_encerra_sem_escolher(
    monkeypatch, tmp_path, capsys
):
    # Mesmo pedido_id, status diferentes: o script não pode escolher um sozinho.
    conflito = {**PEDIDO, "order_status": "canceled"}
    banco = _preparar(monkeypatch, tmp_path, pedidos=[PEDIDO, conflito])

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    assert "pedido_id='p1'" in capsys.readouterr().out
    assert not _refined_existe(banco)


def test_avaliacao_com_mesmo_id_em_pedidos_diferentes_nao_e_duplicata(monkeypatch, tmp_path):
    # review_id r1 aparece em dois pedidos: a chave é (avaliacao_id, pedido_id).
    outra_ordem = {**AVALIACAO, "order_id": "p2"}
    banco = _preparar(monkeypatch, tmp_path, avaliacoes=[AVALIACAO, outra_ordem])

    transformacao.main()

    assert _consulta(banco, "SELECT count(*) FROM refined.avaliacoes") == [(2,)]


# --- tipos ------------------------------------------------------------------

def test_datas_com_hora_viram_timestamp(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    transformacao.main()

    tipo = _consulta(
        banco,
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'refined' AND table_name = 'pedidos' "
        "AND column_name = 'data_compra'",
    )[0][0]
    valor = _consulta(banco, "SELECT data_compra FROM refined.pedidos")[0][0]
    assert tipo == "TIMESTAMP"
    assert valor == datetime(2018, 1, 1, 10, 0, 0)


def test_data_prevista_vira_date_sem_hora(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    transformacao.main()

    tipo = _consulta(
        banco,
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'refined' AND table_name = 'pedidos' "
        "AND column_name = 'data_entrega_prevista'",
    )[0][0]
    valor = _consulta(banco, "SELECT data_entrega_prevista FROM refined.pedidos")[0][0]
    assert tipo == "DATE"
    assert valor == date(2018, 1, 6)


def test_dinheiro_vira_decimal_com_centavos_exatos(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    transformacao.main()

    tipo = _consulta(
        banco,
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'refined' AND table_name = 'itens_pedido' "
        "AND column_name = 'preco'",
    )[0][0]
    preco = _consulta(banco, "SELECT preco FROM refined.itens_pedido")[0][0]
    assert tipo == "DECIMAL(10,2)"
    assert preco == Decimal("12.50")


def test_contagens_e_medidas_viram_inteiro(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    transformacao.main()

    tipo = _consulta(
        banco,
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'refined' AND table_name = 'produtos' "
        "AND column_name = 'peso_g'",
    )[0][0]
    peso = _consulta(banco, "SELECT peso_g FROM refined.produtos")[0][0]
    assert tipo == "INTEGER"
    assert peso == 500


def test_cep_continua_texto_com_zero_a_esquerda(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)

    transformacao.main()

    tipo = _consulta(
        banco,
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'refined' AND table_name = 'clientes' "
        "AND column_name = 'cep_prefixo'",
    )[0][0]
    cep = _consulta(banco, "SELECT cep_prefixo FROM refined.clientes")[0][0]
    assert tipo == "VARCHAR"
    assert cep == "01151"


def test_valor_que_nao_converte_encerra_sem_virar_nulo(monkeypatch, tmp_path, capsys):
    # "doze" não é número: o CAST tem que estourar, não devolver nulo.
    item_ruim = {**ITEM, "price": "doze"}
    banco = _preparar(monkeypatch, tmp_path, itens_pedido=[item_ruim])

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    texto = capsys.readouterr().out
    assert "raw.itens_pedido.price" in texto
    assert "'doze'" in texto
    assert not _refined_existe(banco)


def test_data_prevista_que_nao_converte_encerra_com_systemexit(monkeypatch, tmp_path, capsys):
    # Data prevista é DATE: "dia 30" não converte, e tem que parar aqui.
    pedido_ruim = {**PEDIDO, "order_estimated_delivery_date": "dia 30"}
    banco = _preparar(monkeypatch, tmp_path, pedidos=[pedido_ruim])

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    texto = capsys.readouterr().out
    assert "order_estimated_delivery_date" in texto
    assert "'dia 30'" in texto
    assert not _refined_existe(banco)


def test_coluna_do_mapa_ausente_no_raw_encerra_com_systemexit(monkeypatch, tmp_path, capsys):
    # Se o raw perdeu uma coluna que o SELECT lê, o script tem que parar antes.
    banco = _preparar(monkeypatch, tmp_path)
    con = duckdb.connect(str(banco))
    con.execute('ALTER TABLE raw.pedidos DROP COLUMN "order_estimated_delivery_date"')
    con.close()

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    assert "order_estimated_delivery_date" in capsys.readouterr().out
    assert not _refined_existe(banco)


def test_data_que_nao_converte_encerra_com_systemexit(monkeypatch, tmp_path, capsys):
    pedido_ruim = {**PEDIDO, "order_purchase_timestamp": "ontem"}
    banco = _preparar(monkeypatch, tmp_path, pedidos=[pedido_ruim])

    with pytest.raises(SystemExit) as saida:
        transformacao.main()

    assert saida.value.code == 1
    assert "order_purchase_timestamp" in capsys.readouterr().out
    assert not _refined_existe(banco)


# --- nulos ------------------------------------------------------------------

def test_nulo_em_data_nao_apaga_a_linha_nem_e_preenchido(monkeypatch, tmp_path, capsys):
    # Pedido cancelado: sem data de aprovação e sem entrega. A linha fica.
    cancelado = {
        **PEDIDO, "order_id": "p2", "order_status": "canceled",
        "order_approved_at": None, "order_delivered_customer_date": None,
    }
    banco = _preparar(monkeypatch, tmp_path, pedidos=[PEDIDO, cancelado])

    transformacao.main()

    assert _consulta(banco, "SELECT count(*) FROM refined.pedidos") == [(2,)]
    nulo = _consulta(
        banco, "SELECT data_aprovacao FROM refined.pedidos WHERE pedido_id = 'p2'"
    )[0][0]
    assert nulo is None
    assert "data_aprovacao 1" in capsys.readouterr().out


def test_titulo_e_comentario_nulos_continuam_nulos(monkeypatch, tmp_path):
    banco = _preparar(monkeypatch, tmp_path)  # AVALIACAO já tem título e comentário nulos

    transformacao.main()

    titulo, comentario = _consulta(
        banco, "SELECT titulo, comentario FROM refined.avaliacoes"
    )[0]
    assert titulo is None
    assert comentario is None


# --- saída e reexecução -----------------------------------------------------

def test_saida_tem_uma_linha_por_tabela_e_total(monkeypatch, tmp_path, capsys):
    _preparar(monkeypatch, tmp_path)

    transformacao.main()

    linhas = capsys.readouterr().out.splitlines()
    tabelas = [linha for linha in linhas if linha.startswith("refined.")]
    assert len(tabelas) == 8
    assert linhas[-1] == "Total: 8 linhas"


def test_rodar_duas_vezes_imprime_exatamente_o_mesmo(monkeypatch, tmp_path, capsys):
    banco = _preparar(monkeypatch, tmp_path)

    transformacao.main()
    primeira = capsys.readouterr().out
    transformacao.main()
    segunda = capsys.readouterr().out

    assert primeira == segunda
    assert _consulta(banco, "SELECT count(*) FROM refined.pedidos") == [(1,)]
