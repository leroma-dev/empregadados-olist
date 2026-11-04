"""Ingestão: lê os nove .csv.gz de raw/ e grava cada um no schema raw do olist.duckdb.

Execução: uv run python -m pipeline.ingestao

SPEC (fonte: spec.md, seção "SPEC DA INGESTÃO")

1. ESCOPO E NOMES
   Schema de destino: raw. Mapa arquivo -> tabela, literal (ver MAPA abaixo).
   Por quê: os nomes em português são o vocabulário que o autor digita de
   memória nos JOINs das próximas aulas.

2. PROIBIÇÕES
   Nenhuma conversão de tipo. Nenhuma linha descartada ou deduplicada.
   Nenhum nome de coluna alterado. Nenhum valor corrigido, preenchido ou
   normalizado. Data continua texto, nulo continua nulo.
   Por quê: a fronteira entre "o dado que chegou" e "o dado que eu decidi"
   precisa existir em algum lugar, e esse lugar é a passagem de raw para
   refined, na etapa 2. Se a correção acontecer aqui, a fronteira some.

3. REEXECUÇÃO
   Rodar dez vezes dá o mesmo resultado que rodar uma: a tabela é recriada
   (CREATE OR REPLACE), nunca acrescentada.

4. LEITURA DO ARQUIVO
   Encoding declarado como utf-8, nunca adivinhado. Os .csv.gz são lidos
   direto, sem descompactar em disco. Campo vazio vira nulo, não string vazia.

5. TIPAGEM
   Toda coluna entra como texto (dtype=str), com inferência desligada.
   Por quê: inferência lê CEP com zero à esquerda como número e o zero some
   sem aviso. A conversão acontece na etapa 2, como decisão registrada.

6. SAÍDA NA TELA
   Uma linha por tabela, com nome qualificado e contagem vinda do banco (não
   do DataFrame), milhar separado por ponto. Uma linha final com o total.
   Por quê: essa saída é o único instrumento de conferência desta etapa.
   stdout em utf-8, porque o autor roda no Prompt de Comando do Windows.

7. ERRO
   Antes de abrir o banco, verifica-se que os nove arquivos existem. Faltando
   qualquer um: lista os que faltam, diz em que pasta procurou e sai com
   sys.exit(1). Não ingere parcialmente.
   Por quê: ingerir oito de nove tabelas em silêncio produz um dashboard
   errado que parece certo.

CRITÉRIOS DE ACEITE
- A execução imprime nove linhas e um total de 1.550.922 registros.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
- SELECT * FROM raw.pedidos devolve todas as colunas como VARCHAR.
- Remover um arquivo da pasta faz o script parar antes de gravar qualquer tabela.
- O script termina sozinho e devolve o terminal: nenhum processo fica de pé.
"""

import sys

import pandas as pd

from pipeline import db

SCHEMA = "raw"

MAPA = [
    ("olist_orders_dataset.csv.gz", "pedidos"),
    ("olist_order_items_dataset.csv.gz", "itens_pedido"),
    ("olist_order_payments_dataset.csv.gz", "pagamentos"),
    ("olist_order_reviews_dataset.csv.gz", "avaliacoes"),
    ("olist_customers_dataset.csv.gz", "clientes"),
    ("olist_sellers_dataset.csv.gz", "vendedores"),
    ("olist_products_dataset.csv.gz", "produtos"),
    ("product_category_name_translation.csv.gz", "traducao_categorias"),
    ("olist_geolocation_dataset.csv.gz", "geolocalizacao"),
]


def milhar(n):
    return f"{n:,}".replace(",", ".")


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    faltando = [arquivo for arquivo, _ in MAPA if not (db.PASTA_RAW / arquivo).is_file()]
    if faltando:
        print(f"Arquivos faltando em {db.PASTA_RAW}:")
        for arquivo in faltando:
            print(f"  - {arquivo}")
        sys.exit(1)

    con = db.conectar()
    try:
        db.criar_schema(con, SCHEMA)
        total = 0
        for arquivo, tabela in MAPA:
            df = pd.read_csv(
                db.PASTA_RAW / arquivo,
                dtype=str,
                encoding="utf-8",
                # Só campo vazio vira nulo. Sem isso o pandas também trata
                # textos como "NA" ou "null" como nulo, o que é normalização.
                keep_default_na=False,
                na_values=[""],
            )
            contagem = db.gravar(con, df, SCHEMA, tabela)
            total += contagem
            print(f"{SCHEMA}.{tabela:<22} {milhar(contagem):>12}")
        print(f"{'Total':<{len(SCHEMA) + 1 + 22}} {milhar(total):>12} registros")
    finally:
        con.close()


if __name__ == "__main__":
    main()
