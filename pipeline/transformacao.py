"""Transformação: lê o schema raw e grava oito tabelas no schema refined do olist.duckdb.

Execução: uv run python -m pipeline.transformacao

SPEC (fonte: spec/transformacao.md, seções 1 a 7, reexecução, erro e critérios de aceite)

1. ESCOPO
   Lê de raw, escreve no schema refined. Nunca escreve em raw.
   Entram oito tabelas: pedidos, itens_pedido, pagamentos, clientes,
   vendedores, produtos, traducao_categorias, avaliacoes.
   Fica de fora:
     geolocalizacao  nenhum mart do curso usa. Não se limpa o que
                     ninguém vai ler.

2. NOMES
   Colunas renomeadas para português, snake_case, com o mapa abaixo,
   completo e literal. Nenhuma coluna fora do mapa; nenhuma descartada.
   Motivo: é o vocabulário que vou digitar de memória nos JOINs da aula 3.

   pedidos
     order_id -> pedido_id                 customer_id -> cliente_id
     order_status -> status                order_purchase_timestamp -> data_compra
     order_approved_at -> data_aprovacao   order_delivered_carrier_date -> data_envio
     order_delivered_customer_date -> data_entrega
     order_estimated_delivery_date -> data_entrega_prevista
   itens_pedido
     order_id -> pedido_id                 order_item_id -> item_seq
     product_id -> produto_id              seller_id -> vendedor_id
     shipping_limit_date -> data_limite_envio
     price -> preco                        freight_value -> frete
   pagamentos
     order_id -> pedido_id                 payment_sequential -> pagamento_seq
     payment_type -> tipo                  payment_installments -> parcelas
     payment_value -> valor
   clientes
     customer_id -> cliente_id             customer_unique_id -> cliente_unico_id
     customer_zip_code_prefix -> cep_prefixo
     customer_city -> cidade               customer_state -> uf
   vendedores
     seller_id -> vendedor_id              seller_zip_code_prefix -> cep_prefixo
     seller_city -> cidade                 seller_state -> uf
   produtos
     product_id -> produto_id              product_category_name -> categoria
     product_name_lenght -> tamanho_nome   product_description_lenght -> tamanho_descricao
     product_photos_qty -> qtd_fotos       product_weight_g -> peso_g
     product_length_cm -> comprimento_cm   product_height_cm -> altura_cm
     product_width_cm -> largura_cm
   traducao_categorias
     product_category_name -> categoria
     product_category_name_english -> categoria_en
   avaliacoes
     review_id -> avaliacao_id             order_id -> pedido_id
     review_score -> nota                  review_comment_title -> titulo
     review_comment_message -> comentario
     review_creation_date -> data_criacao
     review_answer_timestamp -> data_resposta

3. TIPOS
   Datas com hora: TIMESTAMP, formato declarado '%Y-%m-%d %H:%M:%S'
     (data_compra, data_aprovacao, data_envio, data_entrega,
      data_limite_envio, data_resposta).
   data_entrega_prevista: DATE. Motivo: a hora é sempre 00:00:00 nas
     99.441 linhas; guardar a hora seria inventar precisão.
   data_criacao: DATE. Motivo: a hora é 00:00:00 em 99.139 das 99.224
     avaliações; nas outras 85 é 01:00:00, efeito de horário de verão, e
     não um horário de verdade.
   Dinheiro (preco, frete, valor): DECIMAL(10,2). Motivo: DOUBLE não
     representa centavos com exatidão, e soma de dinheiro tem que fechar.
   Contagens e medidas (item_seq, pagamento_seq, parcelas, tamanho_nome,
     tamanho_descricao, qtd_fotos, peso_g, comprimento_cm, altura_cm,
     largura_cm, nota): INTEGER.
   Todo o resto continua VARCHAR — inclusive cep_prefixo. Motivo: 23.995
     clientes têm CEP começando com zero; CEP é identificador, nunca é
     somado, e como número perderia o zero.
   A conversão é feita em SQL pelo DuckDB (strptime, CAST), disparada pelo
   Python. Motivo: o dado já está no banco; não há por que trazê-lo para a
   memória só para converter tipo.

4. CONVERSÃO QUE FALHA
   Para tudo. Use strptime e CAST, que estouram, e nunca try_strptime,
   TRY_CAST ou errors="coerce", que transformam falha em nulo.
   Ao falhar: diga tabela, coluna e um exemplo do valor que não converteu,
   e encerre com sys.exit(1).
   Motivo: um nulo fabricado pela conversão fica indistinguível de um nulo
   verdadeiro do dado, para sempre.

5. DUPLICATAS
   Chave de cada tabela:
     pedidos (pedido_id)            itens_pedido (pedido_id, item_seq)
     pagamentos (pedido_id, pagamento_seq)
     clientes (cliente_id)          vendedores (vendedor_id)
     produtos (produto_id)          traducao_categorias (categoria)
     avaliacoes (avaliacao_id, pedido_id)
       — avaliacao_id sozinho não é chave: o mesmo id aparece em mais
         de um pedido.
   Linha inteira repetida: mantém uma, e conta quantas saíram.
   Chave repetida com conteúdo diferente: para, mostra a chave e as linhas
   conflitantes, sys.exit(1). Não escolhe uma por conta própria.
   Motivo: escolher em silêncio é decidir sem dizer que decidiu.

6. NULOS
   Nenhuma linha é apagada por ter nulo. Nenhum nulo é preenchido.
   Motivo: nas datas de pedidos, o nulo é informação — pedido cancelado
   não tem data de entrega porque não foi entregue. Em produtos, 610 sem
   categoria continuam sem categoria; dar um rótulo para eles é decisão
   de mart (aula 3), não de refined. Em avaliacoes, título e comentário
   nulos continuam nulos: avaliação sem texto é a regra, não a exceção.
   Anomalias de negócio também ficam (ex.: 8 pedidos delivered sem
   data_entrega, 166 com data_envio antes da data_compra, pedidos com
   mais de uma avaliação). refined não corrige fato; quem decide o que
   fazer com ele é a pergunta que o mart responde.

7. SAÍDA NA TELA
   Uma linha por tabela, no formato:
     refined.pedidos            99.441 -> 99.441 linhas  (0 duplicatas)
   Abaixo dela, indentadas, as colunas com nulo e a contagem:
       nulos mantidos: data_aprovacao 160, data_envio 1.783, data_entrega 2.965
   As contagens vêm do banco, milhar separado por ponto. Linha final com o
   total. stdout reconfigurado para utf-8.

REEXECUÇÃO
   CREATE OR REPLACE TABLE, nunca acrescenta. Rodar dez vezes = rodar uma.

ERRO
   Antes de transformar, verifica se as oito tabelas de entrada existem em
   raw. Faltando qualquer uma: lista quais, diz para rodar
   "uv run python -m pipeline.ingestao" e encerra com sys.exit(1).

CRITÉRIOS DE ACEITE
- Oito tabelas em refined; em cada uma, linhas que saem = linhas que entram
  (com este dado, 0 duplicatas em todas). Total: 550.759.
- DESCRIBE refined.pedidos mostra TIMESTAMP nas cinco datas com hora e DATE
  em data_entrega_prevista.
- Nulos depois = nulos antes, coluna por coluna (pedidos: 160 / 1.783 /
  2.965; produtos: 610 em categoria; avaliacoes: 87.656 em titulo,
  58.247 em comentario).
- sum(preco) em refined.itens_pedido bate com sum(CAST(price AS DECIMAL))
  em raw, centavo por centavo.
- cep_prefixo continua com o zero à esquerda: '01151' e não 1151.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
"""

import sys

import duckdb

from pipeline import db

SCHEMA_ENTRADA = "raw"
SCHEMA_SAIDA = "refined"
FORMATO_DATA_HORA = "%Y-%m-%d %H:%M:%S"

# Os SELECTs abaixo são a transformação. Cada um lê de raw e devolve as colunas
# de refined já renomeadas e tipadas. Nenhum apaga linha nem preenche nulo.

SELECT_PEDIDOS = """
SELECT
    "order_id" AS pedido_id,
    "customer_id" AS cliente_id,
    "order_status" AS status,
    strptime("order_purchase_timestamp", '%Y-%m-%d %H:%M:%S') AS data_compra,
    strptime("order_approved_at", '%Y-%m-%d %H:%M:%S') AS data_aprovacao,
    strptime("order_delivered_carrier_date", '%Y-%m-%d %H:%M:%S') AS data_envio,
    strptime("order_delivered_customer_date", '%Y-%m-%d %H:%M:%S') AS data_entrega,
    CAST(strptime("order_estimated_delivery_date", '%Y-%m-%d %H:%M:%S') AS DATE)
        AS data_entrega_prevista
FROM raw.pedidos
"""

SELECT_ITENS_PEDIDO = """
SELECT
    "order_id" AS pedido_id,
    CAST("order_item_id" AS INTEGER) AS item_seq,
    "product_id" AS produto_id,
    "seller_id" AS vendedor_id,
    strptime("shipping_limit_date", '%Y-%m-%d %H:%M:%S') AS data_limite_envio,
    CAST("price" AS DECIMAL(10,2)) AS preco,
    CAST("freight_value" AS DECIMAL(10,2)) AS frete
FROM raw.itens_pedido
"""

SELECT_PAGAMENTOS = """
SELECT
    "order_id" AS pedido_id,
    CAST("payment_sequential" AS INTEGER) AS pagamento_seq,
    "payment_type" AS tipo,
    CAST("payment_installments" AS INTEGER) AS parcelas,
    CAST("payment_value" AS DECIMAL(10,2)) AS valor
FROM raw.pagamentos
"""

SELECT_CLIENTES = """
SELECT
    "customer_id" AS cliente_id,
    "customer_unique_id" AS cliente_unico_id,
    "customer_zip_code_prefix" AS cep_prefixo,
    "customer_city" AS cidade,
    "customer_state" AS uf
FROM raw.clientes
"""

SELECT_VENDEDORES = """
SELECT
    "seller_id" AS vendedor_id,
    "seller_zip_code_prefix" AS cep_prefixo,
    "seller_city" AS cidade,
    "seller_state" AS uf
FROM raw.vendedores
"""

SELECT_PRODUTOS = """
SELECT
    "product_id" AS produto_id,
    "product_category_name" AS categoria,
    CAST("product_name_lenght" AS INTEGER) AS tamanho_nome,
    CAST("product_description_lenght" AS INTEGER) AS tamanho_descricao,
    CAST("product_photos_qty" AS INTEGER) AS qtd_fotos,
    CAST("product_weight_g" AS INTEGER) AS peso_g,
    CAST("product_length_cm" AS INTEGER) AS comprimento_cm,
    CAST("product_height_cm" AS INTEGER) AS altura_cm,
    CAST("product_width_cm" AS INTEGER) AS largura_cm
FROM raw.produtos
"""

SELECT_TRADUCAO_CATEGORIAS = """
SELECT
    "product_category_name" AS categoria,
    "product_category_name_english" AS categoria_en
FROM raw.traducao_categorias
"""

SELECT_AVALIACOES = """
SELECT
    "review_id" AS avaliacao_id,
    "order_id" AS pedido_id,
    CAST("review_score" AS INTEGER) AS nota,
    "review_comment_title" AS titulo,
    "review_comment_message" AS comentario,
    CAST(strptime("review_creation_date", '%Y-%m-%d %H:%M:%S') AS DATE) AS data_criacao,
    strptime("review_answer_timestamp", '%Y-%m-%d %H:%M:%S') AS data_resposta
FROM raw.avaliacoes
"""

# Para cada tabela:
#   select         o SELECT literal acima
#   chave          chave de duplicatas (seção 5 da spec)
#   colunas_raw    colunas de raw que o SELECT lê; devem ser exatamente as do banco
#   tipadas        (coluna em raw, coluna em refined, tipo) das colunas que são
#                  convertidas. Usado só para localizar a coluna que falhou.
TABELAS = {
    "pedidos": {
        "select": SELECT_PEDIDOS,
        "chave": ["pedido_id"],
        "colunas_raw": [
            "order_id", "customer_id", "order_status", "order_purchase_timestamp",
            "order_approved_at", "order_delivered_carrier_date",
            "order_delivered_customer_date", "order_estimated_delivery_date",
        ],
        "tipadas": [
            ("order_purchase_timestamp", "data_compra", "TIMESTAMP"),
            ("order_approved_at", "data_aprovacao", "TIMESTAMP"),
            ("order_delivered_carrier_date", "data_envio", "TIMESTAMP"),
            ("order_delivered_customer_date", "data_entrega", "TIMESTAMP"),
            ("order_estimated_delivery_date", "data_entrega_prevista", "DATE"),
        ],
    },
    "itens_pedido": {
        "select": SELECT_ITENS_PEDIDO,
        "chave": ["pedido_id", "item_seq"],
        "colunas_raw": [
            "order_id", "order_item_id", "product_id", "seller_id",
            "shipping_limit_date", "price", "freight_value",
        ],
        "tipadas": [
            ("order_item_id", "item_seq", "INTEGER"),
            ("shipping_limit_date", "data_limite_envio", "TIMESTAMP"),
            ("price", "preco", "DECIMAL(10,2)"),
            ("freight_value", "frete", "DECIMAL(10,2)"),
        ],
    },
    "pagamentos": {
        "select": SELECT_PAGAMENTOS,
        "chave": ["pedido_id", "pagamento_seq"],
        "colunas_raw": [
            "order_id", "payment_sequential", "payment_type",
            "payment_installments", "payment_value",
        ],
        "tipadas": [
            ("payment_sequential", "pagamento_seq", "INTEGER"),
            ("payment_installments", "parcelas", "INTEGER"),
            ("payment_value", "valor", "DECIMAL(10,2)"),
        ],
    },
    "clientes": {
        "select": SELECT_CLIENTES,
        "chave": ["cliente_id"],
        "colunas_raw": [
            "customer_id", "customer_unique_id", "customer_zip_code_prefix",
            "customer_city", "customer_state",
        ],
        "tipadas": [],
    },
    "vendedores": {
        "select": SELECT_VENDEDORES,
        "chave": ["vendedor_id"],
        "colunas_raw": [
            "seller_id", "seller_zip_code_prefix", "seller_city", "seller_state",
        ],
        "tipadas": [],
    },
    "produtos": {
        "select": SELECT_PRODUTOS,
        "chave": ["produto_id"],
        "colunas_raw": [
            "product_id", "product_category_name", "product_name_lenght",
            "product_description_lenght", "product_photos_qty", "product_weight_g",
            "product_length_cm", "product_height_cm", "product_width_cm",
        ],
        "tipadas": [
            ("product_name_lenght", "tamanho_nome", "INTEGER"),
            ("product_description_lenght", "tamanho_descricao", "INTEGER"),
            ("product_photos_qty", "qtd_fotos", "INTEGER"),
            ("product_weight_g", "peso_g", "INTEGER"),
            ("product_length_cm", "comprimento_cm", "INTEGER"),
            ("product_height_cm", "altura_cm", "INTEGER"),
            ("product_width_cm", "largura_cm", "INTEGER"),
        ],
    },
    "traducao_categorias": {
        "select": SELECT_TRADUCAO_CATEGORIAS,
        "chave": ["categoria"],
        "colunas_raw": ["product_category_name", "product_category_name_english"],
        "tipadas": [],
    },
    "avaliacoes": {
        "select": SELECT_AVALIACOES,
        "chave": ["avaliacao_id", "pedido_id"],
        "colunas_raw": [
            "review_id", "order_id", "review_score", "review_comment_title",
            "review_comment_message", "review_creation_date",
            "review_answer_timestamp",
        ],
        "tipadas": [
            ("review_score", "nota", "INTEGER"),
            ("review_creation_date", "data_criacao", "DATE"),
            ("review_answer_timestamp", "data_resposta", "TIMESTAMP"),
        ],
    },
}


def milhar(n):
    return f"{n:,}".replace(",", ".")


def quoted(nome):
    return f'"{nome}"'


def expressao(ref, tipo):
    # Usado só no caminho de erro, para achar a coluna e o valor que falhou.
    # Mesma conversão do SELECT literal: strptime e CAST, que estouram.
    if tipo == "TIMESTAMP":
        return f"strptime({ref}, '{FORMATO_DATA_HORA}')"
    if tipo == "DATE":
        return f"CAST(strptime({ref}, '{FORMATO_DATA_HORA}') AS DATE)"
    return f"CAST({ref} AS {tipo})"


def tabelas_faltando(con):
    existentes = {
        linha[0]
        for linha in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [SCHEMA_ENTRADA],
        ).fetchall()
    }
    return [t for t in TABELAS if t not in existentes]


def verificar_mapa(con, tabela, colunas_raw):
    # O SELECT literal tem que ler exatamente as colunas de raw: sem coluna
    # solta (que seria descartada em silêncio) e sem coluna faltando.
    no_raw = {
        linha[0]
        for linha in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ?",
            [SCHEMA_ENTRADA, tabela],
        ).fetchall()
    }
    esperadas = set(colunas_raw)
    fora = sorted(no_raw - esperadas)
    faltam = sorted(esperadas - no_raw)
    if fora or faltam:
        print(f"ERRO: raw.{tabela} não bate com o SELECT da transformação.")
        if fora:
            print(f"  colunas no raw fora do mapa: {', '.join(fora)}")
        if faltam:
            print(f"  colunas do mapa ausentes no raw: {', '.join(faltam)}")
        sys.exit(1)


def primeiro_valor_que_falha(con, tabela, origem, tipo):
    # Só roda no caminho de erro, para mostrar um exemplo.
    valores = con.execute(
        f"SELECT DISTINCT {quoted(origem)} FROM {SCHEMA_ENTRADA}.{quoted(tabela)} "
        f"WHERE {quoted(origem)} IS NOT NULL ORDER BY 1"
    ).fetchall()
    consulta = f"SELECT {expressao(quoted('v'), tipo)} FROM (SELECT ? AS v)"
    for (valor,) in valores:
        try:
            con.execute(consulta, [valor]).fetchall()
        except duckdb.Error:
            return valor
    return None


def reportar_falha(con, tabela, erro):
    # O SELECT literal estourou. Acha a coluna e um valor que não converte.
    for origem, destino, tipo in TABELAS[tabela]["tipadas"]:
        try:
            con.execute(
                f"SELECT count({expressao(quoted(origem), tipo)}) "
                f"FROM {SCHEMA_ENTRADA}.{quoted(tabela)}"
            ).fetchall()
        except duckdb.Error as erro_coluna:
            exemplo = primeiro_valor_que_falha(con, tabela, origem, tipo)
            print(f"ERRO de conversão: {SCHEMA_ENTRADA}.{tabela}.{origem} -> {destino} ({tipo})")
            print(f"  valor que não converteu: {exemplo!r}")
            print(f"  detalhe do DuckDB: {erro_coluna}")
            sys.exit(1)
    print(f"ERRO de conversão em {SCHEMA_ENTRADA}.{tabela}: {erro}")
    sys.exit(1)


def preparar(con, tabela, select, chave):
    # Materializa o SELECT literal em tabela temporária e checa duplicatas nela.
    # Não grava refined: a gravação só acontece depois que as oito passam.
    try:
        con.execute(f"CREATE OR REPLACE TEMP TABLE tmp_{tabela} AS {select}")
    except duckdb.Error as erro:
        reportar_falha(con, tabela, erro)

    entrada = con.execute(f"SELECT count(*) FROM {SCHEMA_ENTRADA}.{quoted(tabela)}").fetchone()[0]
    sem_repeticao = f"(SELECT DISTINCT * FROM tmp_{tabela})"
    saida = con.execute(f"SELECT count(*) FROM {sem_repeticao}").fetchone()[0]

    chave_sql = ", ".join(chave)
    conflitos = con.execute(
        f"SELECT {chave_sql} FROM {sem_repeticao} "
        f"GROUP BY {chave_sql} HAVING count(*) > 1 ORDER BY {chave_sql}"
    ).fetchall()
    if conflitos:
        primeira = conflitos[0]
        condicao = " AND ".join(f"{k} IS NOT DISTINCT FROM ?" for k in chave)
        linhas = con.execute(
            f"SELECT * FROM {sem_repeticao} WHERE {condicao} ORDER BY ALL",
            list(primeira),
        ).fetchall()
        chave_txt = ", ".join(f"{k}={v!r}" for k, v in zip(chave, primeira))
        print(f"ERRO: chave repetida com conteúdo diferente em {SCHEMA_SAIDA}.{tabela}")
        print(f"  chave: {chave_txt}  ({len(conflitos)} chave(s) em conflito no total)")
        for linha in linhas:
            print(f"  {linha}")
        sys.exit(1)

    return {"entrada": entrada, "saida": saida, "duplicatas": entrada - saida}


def gravar(con, tabela, chave):
    con.execute(
        f"CREATE OR REPLACE TABLE {SCHEMA_SAIDA}.{quoted(tabela)} AS "
        f"SELECT DISTINCT * FROM tmp_{tabela} ORDER BY {', '.join(chave)}"
    )
    return con.execute(f"SELECT count(*) FROM {SCHEMA_SAIDA}.{quoted(tabela)}").fetchone()[0]


def nulos_mantidos(con, tabela):
    # nulos = total - count(coluna): count ignora nulo. Contagem vinda do banco.
    colunas = [
        linha[0]
        for linha in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
            [SCHEMA_SAIDA, tabela],
        ).fetchall()
    ]
    expr = ", ".join(f"count(*) - count({quoted(c)})" for c in colunas)
    valores = con.execute(f"SELECT {expr} FROM {SCHEMA_SAIDA}.{quoted(tabela)}").fetchone()
    return [(c, n) for c, n in zip(colunas, valores) if n > 0]


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    con = db.conectar()
    try:
        faltando = tabelas_faltando(con)
        if faltando:
            print(f"Tabelas faltando em {SCHEMA_ENTRADA}: {', '.join(faltando)}")
            print('Rode "uv run python -m pipeline.ingestao" antes desta etapa.')
            sys.exit(1)

        for tabela, spec in TABELAS.items():
            verificar_mapa(con, tabela, spec["colunas_raw"])

        # Fase 1: materializa, valida e checa duplicatas de todas as oito.
        # Qualquer falha sai aqui, antes de refined ser tocado.
        contagens = {}
        for tabela, spec in TABELAS.items():
            contagens[tabela] = preparar(con, tabela, spec["select"], spec["chave"])

        # Fase 2: grava refined.
        db.criar_schema(con, SCHEMA_SAIDA)
        total = 0
        for tabela, spec in TABELAS.items():
            contagem = contagens[tabela]
            saida = gravar(con, tabela, spec["chave"])
            total += saida
            nome = f"{SCHEMA_SAIDA}.{tabela}"
            print(
                f"{nome:<28} {milhar(contagem['entrada']):>7} -> {milhar(saida):>7} linhas  "
                f"({milhar(contagem['duplicatas'])} duplicatas)"
            )
            nulos = nulos_mantidos(con, tabela)
            if nulos:
                texto = ", ".join(f"{col} {milhar(n)}" for col, n in nulos)
                print(f"    nulos mantidos: {texto}")
        print(f"Total: {milhar(total)} linhas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
