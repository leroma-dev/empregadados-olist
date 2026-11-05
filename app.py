"""Página do painel da operação Olist.

Execução: uv run streamlit run app.py

A spec completa está na docstring de painel.py. Este arquivo só monta a
página: lê com painel.ler(), recorta a linha do faturamento pelo filtro e
chama as funções de gráfico. Não calcula nada (exceto a conta da Recompra,
permitida pela spec).
"""

from pathlib import Path

import streamlit as st

import painel

st.set_page_config(page_title="Olist · visão da operação", layout="wide")

COMANDO_MARTS = "uv run python -m pipeline.marts"


@st.cache_data
def carregar():
    return painel.ler(painel.MARTS)


def mostrar_faltando(faltando):
    st.error(
        "Faltam dados para o painel: " + ", ".join(faltando)
        + f". Rode: {COMANDO_MARTS}"
    )
    st.stop()


# Sem arquivo, nenhum mart existe: a lista completa é o que falta.
if not Path(painel.ARQUIVO_BANCO).exists():
    mostrar_faltando(painel.MARTS)

dados = carregar()
faltando = [nome for nome in painel.MARTS if nome not in dados]
if faltando:
    mostrar_faltando(faltando)

# --- cabeçalho ------------------------------------------------------------

meses = dados["vendas_mensais"]["mes"].sort_values().tolist()


def mes_de(ano, mes):
    return next(m for m in meses if (m.year, m.month) == (ano, mes))


col_titulo, col_filtro = st.columns([3, 2])
with col_titulo:
    st.title("Olist · visão da operação")
    if st.button("Recarregar dados"):
        carregar.clear()
        st.rerun()
with col_filtro:
    periodo = st.select_slider(
        "Período do faturamento",
        options=meses,
        value=(mes_de(2017, 1), mes_de(2018, 8)),
        format_func=lambda data: painel.rotulo_mes(data),
    )
    st.caption("Os cartões valem para o período inteiro.")

ini, fim = periodo
vendas = dados["vendas_mensais"]
faturamento = vendas[(vendas["mes"] >= ini) & (vendas["mes"] <= fim)]

# --- faixa 1: cartões -----------------------------------------------------

kpis = dados["kpis"].iloc[0]
um_pedido = dados["recompra"]
um_pedido = um_pedido[um_pedido["pedidos_por_cliente"] == 1].iloc[0]
no_prazo = dados["entrega_no_prazo"].iloc[0]

cartoes = st.columns(7)
cartoes[0].metric("Ticket médio · por pedido",
                  painel.reais(kpis["ticket_medio"]))
cartoes[1].metric("Cancelados · % de todos os pedidos",
                  painel.pct(kpis["pct_cancelados"], 2))
cartoes[2].metric("Peso do frete · % do valor",
                  painel.pct(kpis["pct_frete"], 1))
# Única conta da página, permitida pela spec: o mart 05 guarda o complemento.
cartoes[3].metric("Recompra · clientes que voltaram",
                  painel.pct(100 - um_pedido["pct_clientes"], 2))
cartoes[4].metric("No prazo · entregas até a data prevista",
                  painel.pct(no_prazo["pct_no_prazo"], 1))
cartoes[5].metric("Dias até entregar · média",
                  painel.numero(kpis["dias_entrega"], 1))
cartoes[6].metric("Nota média · de 1 a 5",
                  painel.numero(kpis["nota_media"], 2))

# --- faixa 2: faturamento -------------------------------------------------

st.plotly_chart(painel.faturamento_mensal(faturamento), width="stretch")

# --- faixa 3 --------------------------------------------------------------

c1, c2, c3 = st.columns(3)
with c1:
    st.plotly_chart(painel.receita_por_categoria(dados["top_categorias"]),
                    width="stretch")
with c2:
    st.plotly_chart(painel.mix_pagamento(dados["mix_pagamento"]),
                    width="stretch")
with c3:
    st.plotly_chart(painel.ticket_por_uf(dados["ticket_medio_por_estado"]),
                    width="stretch")

# --- faixa 4 --------------------------------------------------------------

c4, c5, c6 = st.columns(3)
with c4:
    st.plotly_chart(painel.clientes_por_uf(dados["clientes_por_uf"]),
                    width="stretch")
with c5:
    st.plotly_chart(painel.nota_por_categoria(dados["nota_por_categoria"]),
                    width="stretch")
with c6:
    st.plotly_chart(
        painel.concentracao_vendedores(dados["vendedores_pareto"]),
        width="stretch",
    )
