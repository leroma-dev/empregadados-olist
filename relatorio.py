"""Relatório HTML da operação Olist: gera relatorio.html na raiz.

Execução: uv run python relatorio.py

A spec de formato e de gráficos está na docstring de painel.py; a spec deste
arquivo está em spec/05_relatorio_html.md. Este script não importa streamlit:
lê com painel.ler(), formata com painel.reais/pct/numero e monta os gráficos
com as funções de painel.py. Mesmas quatro faixas e mesma ordem do app.py.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import painel

RAIZ = Path(__file__).resolve().parent
SAIDA = RAIZ / "relatorio.html"

# Período padrão do faturamento no app.py (sem filtro).
INICIO = datetime(2017, 1, 1)
FIM = datetime(2018, 8, 1)

CSS = """
:root { --cor: #2f6f9f; --fundo: #f5f6f8; --texto: #1d2733; --borda: #d9dee5; }
* { box-sizing: border-box; }
body { margin: 0; padding: 16px; background: var(--fundo); color: var(--texto);
       font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size: 1.6rem; margin: 0 0 16px; }
section { margin-bottom: 16px; }
.cartoes { display: grid; gap: 12px;
           grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
.cartao { background: #fff; border: 1px solid var(--borda); border-radius: 8px;
          padding: 12px; }
.cartao .rotulo { display: block; font-size: 0.8rem; color: #5b6777; }
.cartao .valor { display: block; font-size: 1.4rem; font-weight: 600;
                 margin-top: 6px; color: var(--cor); }
.graficos { display: grid; gap: 12px;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
.graficos > div { background: #fff; border: 1px solid var(--borda);
                  border-radius: 8px; min-width: 0; overflow: hidden; }
footer { font-size: 0.85rem; color: #5b6777; margin-top: 24px; }
"""


def cartoes_html(dados):
    """Os sete cartões da faixa 1, com os mesmos valores do app.py."""
    kpis = dados["kpis"].iloc[0]
    um_pedido = dados["recompra"]
    um_pedido = um_pedido[um_pedido["pedidos_por_cliente"] == 1].iloc[0]
    no_prazo = dados["entrega_no_prazo"].iloc[0]

    # Mesma conta da página (única permitida pela spec): o mart 05 guarda o
    # complemento, então a recompra é 100 menos a fatia de clientes com 1 pedido.
    cartoes = [
        ("Ticket médio · por pedido", painel.reais(kpis["ticket_medio"])),
        ("Cancelados · % de todos os pedidos", painel.pct(kpis["pct_cancelados"], 2)),
        ("Peso do frete · % do valor", painel.pct(kpis["pct_frete"], 1)),
        (
            "Recompra · clientes que voltaram",
            painel.pct(100 - um_pedido["pct_clientes"], 2),
        ),
        (
            "No prazo · entregas até a data prevista",
            painel.pct(no_prazo["pct_no_prazo"], 1),
        ),
        ("Dias até entregar · média", painel.numero(kpis["dias_entrega"], 1)),
        ("Nota média · de 1 a 5", painel.numero(kpis["nota_media"], 2)),
    ]
    itens = "\n".join(
        f'    <div class="cartao"><span class="rotulo">{rotulo}</span>'
        f'<span class="valor">{valor}</span></div>'
        for rotulo, valor in cartoes
    )
    return f'<section class="cartoes">\n{itens}\n</section>'


def graficos_html(figuras, primeiro):
    """Grade de gráficos. div_id fixo (g01, g02...) para o arquivo não mudar
    a cada execução. Só o primeiro gráfico do documento traz o plotly (CDN)."""
    partes = []
    for i, fig in enumerate(figuras):
        numero_do_grafico = primeiro + i
        html = fig.to_html(
            full_html=False,
            # include_plotlyjs="cdn" if numero_do_grafico == 1 else False,
            include_plotlyjs="true" if numero_do_grafico == 1 else False,
            div_id=f"g{numero_do_grafico:02d}",
            config={"responsive": True},
        )
        partes.append(f"  <div>{html}</div>")
    corpo = "\n".join(partes)
    return f'<section class="graficos">\n{corpo}\n</section>'


def montar_figuras(dados):
    """Faixas 2 a 4, na ordem do app.py. Devolve (faixa2, faixa3, faixa4)."""
    vendas = dados["vendas_mensais"]
    faturamento = vendas[(vendas["mes"] >= INICIO) & (vendas["mes"] <= FIM)]
    fig_fat = painel.faturamento_mensal(faturamento)
    fig_fat.update_layout(
        title=f"01 · Faturamento mensal · "
        f"{painel.rotulo_mes(INICIO)} a {painel.rotulo_mes(FIM)}"
    )
    faixa2 = [fig_fat]
    faixa3 = [
        painel.receita_por_categoria(dados["top_categorias"]),
        painel.mix_pagamento(dados["mix_pagamento"]),
        painel.ticket_por_uf(dados["ticket_medio_por_estado"]),
    ]
    faixa4 = [
        painel.clientes_por_uf(dados["clientes_por_uf"]),
        painel.nota_por_categoria(dados["nota_por_categoria"]),
        painel.concentracao_vendedores(dados["vendedores_pareto"]),
    ]
    return faixa2, faixa3, faixa4


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    # painel.ler() abre "olist.duckdb" pelo caminho relativo: vamos para a raiz.
    os.chdir(RAIZ)

    dados = painel.ler(painel.MARTS)
    faltando = [nome for nome in painel.MARTS if nome not in dados]
    if faltando:
        print(
            "Faltam dados para o relatório: "
            + ", ".join(faltando)
            + ". Rode: uv run python -m pipeline.marts",
            file=sys.stderr,
        )
        sys.exit(1)

    faixa2, faixa3, faixa4 = montar_figuras(dados)

    # Ids g01..g07 seguem a ordem do documento; o plotly.js vem do CDN
    # só no g01, que é o primeiro gráfico da página.
    corpo = "\n".join(
        [
            "<h1>Olist · visão da operação</h1>",
            cartoes_html(dados),
            graficos_html(faixa2, 1),
            graficos_html(faixa3, 1 + len(faixa2)),
            graficos_html(faixa4, 1 + len(faixa2) + len(faixa3)),
        ]
    )

    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")
    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Olist · visão da operação</title>
<style>{CSS}</style>
</head>
<body>
{corpo}
<footer>Dados de {gerado}</footer>
</body>
</html>
"""
    SAIDA.write_text(html, encoding="utf-8")
    print(f"{SAIDA}")
    print(f"{len(html.encode('utf-8')) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
