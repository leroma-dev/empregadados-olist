"""Painel da operação Olist: leitura dos marts, formatação e gráficos.

Este módulo não importa streamlit e não recebe conexão: recebe DataFrames e
devolve figuras plotly. O app.py (streamlit) é quem chama estas funções.

SPEC (fonte: pasta spec/, seção "painel.py" da spec de 2026-11-05)

1. LEITURA
   ler(marts) -> dict nome -> DataFrame. Para cada nome, só
   SELECT * FROM marts.<nome>. Nenhuma outra SQL.
   Conexão com duckdb.connect("olist.duckdb", read_only=True), aberta e
   fechada dentro de ler(). Motivo: conexão aberta segura o arquivo, e o
   pipeline.marts não consegue gravar com o painel de pé.
   Mart que não existe fica de fora do dict (não levanta erro): quem chama
   compara com a lista esperada e diz quais faltam. Motivo: a spec pede que
   a página diga quais marts faltam, e checar isso exige não parar no primeiro.

2. NENHUM CÁLCULO
   Proibido aqui e em app.py: agrupar, somar, tirar média, contar, juntar
   tabelas e qualquer conta entre colunas. Permitido: ordenar,
   filtrar linhas, head(n), renomear coluna e formatar texto.
   Motivo: número novo na tela exige um .sql novo em marts. Se faltar algum
   número, pare e diga qual mart está faltando.

3. LAYOUT: fica em app.py.

4. FORMATO: funções puras, sem streamlit e sem banco.
   reais(valor, casas=2)  -> "R$ 1.003.862,14"
   pct(valor, casas=1)    -> "93,2%"
   numero(valor, casas=0) -> "96.470"
   Milhar com ponto, decimal com vírgula, sempre. Sem locale do sistema.
   Motivo: o resultado não pode depender da máquina de quem roda. Por isso a
   formatação usa só o formatador do Python (sem locale) e troca os separadores.
   Uma função por gráfico, recebendo o DataFrame e devolvendo a figura plotly.
   Motivo: o relatório HTML reaproveita as mesmas funções.

5. FILTRO DE PERÍODO: fica em app.py. Recorta só o gráfico de faturamento.

6. CACHE E ERRO: fica em app.py.
   Motivo do cache: ler() abre o arquivo; sem cache, cada interação relê tudo.

CRITÉRIOS DE ACEITE (conferidos em tests/ e na execução do app)
- Os sete cartões mostram: R$ 137,42 · 0,63% · 14,2% · 3,04% · 93,2% · 12,5 · 4,09.
- Faturamento abre com 20 meses (jan/2017 a ago/2018) e, com o filtro até
  as pontas, mostra os 24 meses do mart.
- Top 10 de categorias com health_beauty em cima; nota com office_furniture
  em cima; ticket por UF com PB em cima e SP embaixo.
- Busca pelas operações proibidas (ver item 2) em painel.py e app.py não
  encontra nada.
- Com o painel de pé, uv run python -m pipeline.marts roda sem erro de lock.
"""

import duckdb
import plotly.express as px

# Nomes dos marts que o painel lê, na ordem em que aparecem nos gráficos.
MARTS = [
    "vendas_mensais",
    "top_categorias",
    "entrega_no_prazo",
    "nota_por_categoria",
    "recompra",
    "ticket_medio_por_estado",
    "mix_pagamento",
    "nota_por_prazo",
    "vendedores_pareto",
    "tempo_entrega_por_estado",
    "kpis",
    "clientes_por_uf",
]

ARQUIVO_BANCO = "olist.duckdb"

# Uma cor só em todos os gráficos (spec: "uma cor só").
COR = "#2f6f9f"

MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun",
               "jul", "ago", "set", "out", "nov", "dez"]


def ler(marts):
    """Lê cada mart pedido e devolve {nome: DataFrame}.

    Mart inexistente não entra no dict. A conexão é aberta e fechada aqui,
    então o arquivo fica livre para o pipeline.marts gravar logo depois.
    """
    resultado = {}
    con = duckdb.connect(ARQUIVO_BANCO, read_only=True)
    try:
        for nome in marts:
            try:
                resultado[nome] = con.execute(f"SELECT * FROM marts.{nome}").df()
            except duckdb.CatalogException:
                continue
    finally:
        con.close()
    return resultado


# --- formato --------------------------------------------------------------

def numero(valor, casas=0):
    # O formatador do Python usa "," de milhar e "." de decimal; trocamos
    # pelos separadores pt-BR sem depender de locale.
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def reais(valor, casas=2):
    return "R$ " + numero(valor, casas)


def pct(valor, casas=1):
    return numero(valor, casas) + "%"


def rotulo_mes(data):
    """jan/2017. Texto puro, sem locale."""
    return f"{MESES_ABREV[data.month - 1]}/{data.year}"


# --- gráficos -------------------------------------------------------------
# Todos devolvem figura plotly com título "NN · nome" (NN = número do mart).

def _estilo(fig, titulo, eixo_x, eixo_y):
    fig.update_layout(
        title=titulo,
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
        xaxis_title=eixo_x,
        yaxis_title=eixo_y,
        showlegend=False,
    )
    return fig


def _barras_horizontais(df, x, y, titulo, eixo_x, eixo_y=""):
    """Barras horizontais com o primeiro da tabela em cima (sem reordenar)."""
    fig = px.bar(df, x=x, y=y, orientation="h")
    fig.update_traces(marker_color=COR)
    # Plotly põe a primeira categoria embaixo por padrão; invertemos o eixo.
    fig.update_yaxes(categoryorder="array", categoryarray=list(df[y]),
                     autorange="reversed")
    return _estilo(fig, titulo, eixo_x, eixo_y)


def faturamento_mensal(df):
    """01 · Faturamento mensal. Linha com marcadores."""
    fig = px.line(df, x="mes", y="receita", markers=True)
    fig.update_traces(line_color=COR, marker_color=COR)
    return _estilo(fig, "01 · Faturamento mensal", "mês", "receita (R$)")


def receita_por_categoria(df):
    """02 · Receita por categoria. Top 10, maior em cima."""
    top = df.sort_values("receita", ascending=False).head(10)
    return _barras_horizontais(top, "receita", "categoria",
                               "02 · Receita por categoria",
                               "receita (R$)", "categoria")


def mix_pagamento(df):
    """07 · Mix de pagamento. Barras por pct_valor."""
    fig = px.bar(df, x="tipo", y="pct_valor")
    fig.update_traces(marker_color=COR)
    return _estilo(fig, "07 · Mix de pagamento",
                   "tipo de pagamento", "% do valor pago")


def ticket_por_uf(df):
    """06 · Ticket médio por UF. Barras horizontais, maior em cima."""
    ordenado = df.sort_values("ticket_medio", ascending=False)
    return _barras_horizontais(ordenado, "ticket_medio", "uf",
                               "06 · Ticket médio por UF",
                               "ticket médio (R$)", "UF")


def clientes_por_uf(df):
    """12 · Clientes por UF. Barras horizontais, maior em cima."""
    ordenado = df.sort_values("clientes", ascending=False)
    return _barras_horizontais(ordenado, "clientes", "uf",
                               "12 · Clientes por UF",
                               "clientes (pessoas)", "UF")


def nota_por_categoria(df):
    """04 · Nota por categoria. As 10 primeiras por posicao_pior, pior em cima."""
    piores = df.sort_values("posicao_pior").head(10)
    fig = px.scatter(piores, x="nota_media", y="categoria")
    fig.update_traces(marker={"color": COR, "size": 10})
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=list(piores["categoria"]),
        autorange="reversed",
    )
    return _estilo(fig, "04 · Nota por categoria",
                   "nota média (1 a 5)", "categoria")


def concentracao_vendedores(df):
    """09 · Concentração de vendedores. Linha de pct_acumulado por posição.

    A linha tracejada em 80 marca 80% da receita acumulada.
    """
    fig = px.line(df, x="posicao", y="pct_acumulado")
    fig.update_traces(line_color=COR)
    fig.add_hline(y=80, line_dash="dash", line_color="#888888")
    return _estilo(fig, "09 · Concentração de vendedores",
                   "vendedores, do maior para o menor (posição)",
                   "% da receita acumulada")
