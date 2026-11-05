"""Testes unitários de relatorio.py.

Os marts são criados num olist.duckdb falso, em tmp_path, com linhas inventadas.
O arquivo de saída também vai para tmp_path: o relatorio.html do projeto não é tocado.
"""

import re
from datetime import date

import duckdb
import pytest

import painel
import relatorio

# Colunas que relatorio.py e painel.py leem de cada mart. Os marts que a página
# não usa diretamente (nota_por_prazo, tempo_entrega_por_estado) entram com uma
# coluna qualquer, só para existirem.
MARTS_INVENTADOS = {
    "vendas_mensais": ("mes DATE, receita DOUBLE", [
        (date(2017, 1, 1), 100.0), (date(2017, 2, 1), 200.0), (date(2018, 9, 1), 999.0),
    ]),
    "top_categorias": ("categoria VARCHAR, receita DOUBLE", [("beleza", 50.0)]),
    "entrega_no_prazo": ("pct_no_prazo DOUBLE", [(93.2,)]),
    "nota_por_categoria": ("categoria VARCHAR, nota_media DOUBLE, posicao_pior INTEGER", [
        ("moveis", 3.1, 1),
    ]),
    "recompra": ("pedidos_por_cliente INTEGER, pct_clientes DOUBLE", [
        (1, 97.5), (2, 2.5),
    ]),
    "ticket_medio_por_estado": ("uf VARCHAR, ticket_medio DOUBLE", [("PB", 150.0)]),
    "mix_pagamento": ("tipo VARCHAR, pct_valor DOUBLE", [("boleto", 20.0)]),
    "nota_por_prazo": ("x INTEGER", [(1,)]),
    "vendedores_pareto": ("posicao INTEGER, pct_acumulado DOUBLE", [(1, 40.0)]),
    "tempo_entrega_por_estado": ("x INTEGER", [(1,)]),
    "kpis": (
        "ticket_medio DOUBLE, pct_cancelados DOUBLE, pct_frete DOUBLE, "
        "dias_entrega DOUBLE, nota_media DOUBLE",
        [(137.42, 0.63, 14.2, 12.5, 4.09)],
    ),
    "clientes_por_uf": ("uf VARCHAR, clientes INTEGER", [("SP", 400)]),
}


def _banco_com_marts(caminho, pular=()):
    con = duckdb.connect(str(caminho))
    con.execute("CREATE SCHEMA marts")
    for nome, (definicao, linhas) in MARTS_INVENTADOS.items():
        if nome in pular:
            continue
        con.execute(f"CREATE TABLE marts.{nome} ({definicao})")
        marcas = ", ".join("?" for _ in linhas[0])
        for linha in linhas:
            con.execute(f"INSERT INTO marts.{nome} VALUES ({marcas})", list(linha))
    con.close()


def _apontar_para(monkeypatch, tmp_path, pular=()):
    banco = tmp_path / "olist.duckdb"
    _banco_com_marts(banco, pular=pular)
    monkeypatch.setattr(painel, "ARQUIVO_BANCO", str(banco))
    saida = tmp_path / "relatorio.html"
    monkeypatch.setattr(relatorio, "SAIDA", saida)
    monkeypatch.chdir(tmp_path)  # main() troca de pasta; o monkeypatch desfaz
    return saida


def test_gera_o_arquivo_dentro_de_tmp_path(monkeypatch, tmp_path):
    saida = _apontar_para(monkeypatch, tmp_path)

    relatorio.main()

    assert saida.is_file()
    html = saida.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "Olist · visão da operação" in html


def test_rodar_duas_vezes_muda_so_o_rodape(monkeypatch, tmp_path):
    saida = _apontar_para(monkeypatch, tmp_path)

    relatorio.main()
    primeiro = saida.read_text(encoding="utf-8")
    relatorio.main()
    segundo = saida.read_text(encoding="utf-8")

    # O rodapé tem a hora da execução. Tirando só ele, os dois arquivos são iguais.
    sem_rodape = re.compile(r"<footer>.*?</footer>", re.DOTALL)
    assert sem_rodape.sub("", primeiro) == sem_rodape.sub("", segundo)


def test_mart_faltando_encerra_e_manda_rodar_pipeline_marts(monkeypatch, tmp_path, capsys):
    saida = _apontar_para(monkeypatch, tmp_path, pular=("kpis",))

    with pytest.raises(SystemExit) as encerrou:
        relatorio.main()

    assert encerrou.value.code == 1
    assert "kpis" in capsys.readouterr().err
    assert not saida.exists()


def test_cartoes_mostram_os_valores_formatados(monkeypatch, tmp_path):
    _apontar_para(monkeypatch, tmp_path)
    dados = painel.ler(painel.MARTS)

    html = relatorio.cartoes_html(dados)

    # Ticket 137,42; cancelados 0,63%; frete 14,2%; recompra = 100 - 97,5 = 2,50%;
    # no prazo 93,2%; dias 12,5; nota 4,09.
    esperados = [
        "R$ 137,42", "0,63%", "14,2%", "2,50%", "93,2%", "12,5", "4,09",
    ]
    for valor in esperados:
        assert f'<span class="valor">{valor}</span>' in html
    assert html.count('class="cartao"') == 7


def test_faturamento_recorta_so_o_periodo_da_pagina(monkeypatch, tmp_path):
    # O mart tem setembro/2018, fora do período (jan/2017 a ago/2018): não entra.
    _apontar_para(monkeypatch, tmp_path)
    dados = painel.ler(painel.MARTS)

    faixa2, _, _ = relatorio.montar_figuras(dados)

    assert len(faixa2[0].data[0].x) == 2


def test_montar_figuras_devolve_as_tres_faixas_na_ordem(monkeypatch, tmp_path):
    _apontar_para(monkeypatch, tmp_path)
    dados = painel.ler(painel.MARTS)

    faixa2, faixa3, faixa4 = relatorio.montar_figuras(dados)

    assert len(faixa2) == 1
    assert len(faixa3) == 3
    assert len(faixa4) == 3
    assert faixa2[0].layout.title.text.startswith("01 · Faturamento mensal")


def test_graficos_recebem_ids_que_seguem_a_ordem_do_documento(monkeypatch, tmp_path):
    _apontar_para(monkeypatch, tmp_path)
    dados = painel.ler(painel.MARTS)
    faixa2, faixa3, _ = relatorio.montar_figuras(dados)

    html = relatorio.graficos_html(faixa2 + faixa3, 1)

    assert 'id="g01"' in html
    assert 'id="g04"' in html
    assert 'id="g05"' not in html
