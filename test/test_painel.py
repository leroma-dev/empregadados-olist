"""Testes unitários de painel.py. Os DataFrames são inventados aqui, linha a linha."""

from datetime import date
from decimal import Decimal

import duckdb
import pandas as pd

import painel


# --- formato ----------------------------------------------------------------

def test_reais_usa_milhar_com_ponto_e_decimal_com_virgula():
    assert painel.reais(Decimal("1003862.14")) == "R$ 1.003.862,14"


def test_reais_com_centavos_fica_com_dois_digitos():
    assert painel.reais(Decimal("137.42")) == "R$ 137,42"


def test_reais_aceita_zero_casas_decimais():
    assert painel.reais(Decimal("1500"), casas=0) == "R$ 1.500"


def test_pct_troca_separador_e_acrescenta_sinal_de_percentual():
    assert painel.pct(93.2) == "93,2%"


def test_pct_com_duas_casas():
    assert painel.pct(0.63, 2) == "0,63%"


def test_numero_sem_casas_usa_ponto_de_milhar():
    assert painel.numero(96470) == "96.470"


def test_numero_com_casas_usa_virgula_decimal():
    assert painel.numero(4.09, 2) == "4,09"
    assert painel.numero(12.5, 1) == "12,5"


def test_rotulo_mes_usa_abreviacao_em_portugues_sem_locale():
    assert painel.rotulo_mes(date(2017, 1, 1)) == "jan/2017"
    assert painel.rotulo_mes(date(2018, 8, 1)) == "ago/2018"


# --- leitura ----------------------------------------------------------------

def _banco_com_marts(caminho):
    con = duckdb.connect(str(caminho))
    con.execute("CREATE SCHEMA marts")
    con.execute("CREATE TABLE marts.kpis AS SELECT 1 AS ticket_medio")  # uma linha
    con.execute("CREATE TABLE marts.vendas_mensais AS SELECT 2 AS receita, 3 AS pedidos")
    con.close()


def test_ler_devolve_so_os_marts_que_existem(monkeypatch, tmp_path):
    banco = tmp_path / "olist.duckdb"
    _banco_com_marts(banco)
    monkeypatch.setattr(painel, "ARQUIVO_BANCO", str(banco))

    dados = painel.ler(["kpis", "vendas_mensais", "nao_existe"])

    # O mart inexistente fica de fora em silêncio; quem chama é que compara.
    assert set(dados) == {"kpis", "vendas_mensais"}
    assert dados["kpis"].iloc[0]["ticket_medio"] == 1


def test_ler_fecha_a_conexao_e_libera_o_arquivo_para_escrita(monkeypatch, tmp_path):
    banco = tmp_path / "olist.duckdb"
    _banco_com_marts(banco)
    monkeypatch.setattr(painel, "ARQUIVO_BANCO", str(banco))

    painel.ler(["kpis"])

    # Se ler() deixasse a conexão aberta, este connect de escrita falharia.
    con = duckdb.connect(str(banco))
    con.execute("CREATE TABLE marts.depois AS SELECT 1 AS x")
    con.close()


# --- gráficos ----------------------------------------------------------------
# Cada gráfico tem que ter um ponto (ou barra) por linha do DataFrame inventado.

def _pontos(fig):
    return len(fig.data[0].x) if fig.data[0].x is not None else len(fig.data[0].y)


def test_faturamento_mensal_tem_um_ponto_por_mes():
    df = pd.DataFrame({
        "mes": [date(2017, 1, 1), date(2017, 2, 1), date(2017, 3, 1)],
        "receita": [10.0, 20.0, 30.0],
    })
    fig = painel.faturamento_mensal(df)
    assert len(fig.data[0].x) == 3
    assert fig.layout.title.text == "01 · Faturamento mensal"


def test_receita_por_categoria_tem_uma_barra_por_categoria():
    df = pd.DataFrame({
        "categoria": ["a", "b", "c"],
        "receita": [5.0, 9.0, 1.0],
    })
    fig = painel.receita_por_categoria(df)
    assert _pontos(fig) == 3
    # Maior em cima: a categoria de maior receita é a primeira da lista de eixo.
    assert fig.layout.yaxis.categoryarray[0] == "b"


def test_mix_pagamento_tem_uma_barra_por_tipo():
    df = pd.DataFrame({
        "tipo": ["credit_card", "boleto"],
        "pct_valor": [80.0, 20.0],
    })
    fig = painel.mix_pagamento(df)
    assert _pontos(fig) == 2


def test_ticket_por_uf_tem_uma_barra_por_uf():
    df = pd.DataFrame({"uf": ["PB", "SP", "RJ"], "ticket_medio": [150.0, 110.0, 120.0]})
    fig = painel.ticket_por_uf(df)
    assert _pontos(fig) == 3
    assert fig.layout.yaxis.categoryarray[0] == "PB"


def test_clientes_por_uf_tem_uma_barra_por_uf():
    df = pd.DataFrame({"uf": ["SP", "MG", "PR"], "clientes": [400, 200, 100]})
    fig = painel.clientes_por_uf(df)
    assert _pontos(fig) == 3
    assert fig.layout.yaxis.categoryarray[0] == "SP"


def test_nota_por_categoria_tem_um_ponto_por_categoria():
    df = pd.DataFrame({
        "categoria": ["x", "y", "z"],
        "nota_media": [3.1, 4.5, 2.0],
        "posicao_pior": [2, 3, 1],
    })
    fig = painel.nota_por_categoria(df)
    assert _pontos(fig) == 3
    # Pior posição primeiro: "z" (posicao_pior 1) é o topo do eixo.
    assert fig.layout.yaxis.categoryarray[0] == "z"


def test_concentracao_vendedores_tem_um_ponto_por_posicao():
    df = pd.DataFrame({
        "posicao": [1, 2, 3],
        "pct_acumulado": [50.0, 75.0, 100.0],
    })
    fig = painel.concentracao_vendedores(df)
    assert _pontos(fig) == 3
    # A linha tracejada em 80 existe como forma, não como ponto de dado.
    assert len(fig.layout.shapes) == 1
