"""Módulo de conexão com o olist.duckdb, importado pelas etapas do pipeline.

SPEC (fonte: spec.md, seção "SPEC DO pipeline/db.py")

Expõe exatamente: PASTA_RAW, conectar(), criar_schema(con, nome), gravar(con, df, schema, tabela).

D1. CAMINHOS
    PASTA_RAW e o olist.duckdb são resolvidos a partir da localização deste
    arquivo (a pasta acima de pipeline/), nunca do diretório corrente.
    Por quê: rodar o script de outra pasta não pode criar um olist.duckdb
    vazio no lugar errado, que parece ingestão quebrada.

D2. TRÊS FUNÇÕES E UMA CONSTANTE, NADA MAIS
    Este módulo não lê CSV, não conhece nome de tabela, não imprime nada e
    não converte tipo. Quem decide tudo isso é cada etapa.
    Por quê: as aulas 2, 3 e 4 importam este arquivo. Regra de negócio
    escondida aqui valeria para todas as etapas sem aparecer em nenhuma spec.

D3. gravar
    Recria a tabela (CREATE OR REPLACE TABLE schema.tabela) com as colunas e
    tipos do DataFrame, sem alterar nada: coluna str vira VARCHAR, nulo
    continua NULL. Não deixa view ou tabela temporária para trás.
    Devolve SELECT count(*) da tabela recém-gravada, lido do banco.
    Por quê: a contagem que aparece na tela tem que ser a do que foi gravado,
    não a do que estava na memória.

D4. CONEXÃO
    conectar() devolve a conexão aberta; quem chama é quem fecha.
    Não há conexão global neste módulo.

CRITÉRIOS DE ACEITE
- Importar pipeline.db não abre banco nem cria arquivo.
- conectar() chamado de outra pasta cria o olist.duckdb na raiz do projeto.
- gravar() com DataFrame de 3 linhas devolve 3, também na segunda execução.
"""

from pathlib import Path

import duckdb

PASTA_RAW = Path(__file__).resolve().parent.parent / "raw"


def conectar():
    banco = Path(__file__).resolve().parent.parent / "olist.duckdb"
    return duckdb.connect(str(banco))


def criar_schema(con, nome):
    # .fetchall() consome o resultado do DDL; no duckdb 2.x uma conexão com
    # resultado pendente recusa o comando seguinte.
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{nome}"').fetchall()


def gravar(con, df, schema, tabela):
    con.register("_df_gravar", df)
    try:
        con.execute(
            f'CREATE OR REPLACE TABLE "{schema}"."{tabela}" AS SELECT * FROM _df_gravar'
        ).fetchall()
    finally:
        con.unregister("_df_gravar")
    return con.execute(f'SELECT count(*) FROM "{schema}"."{tabela}"').fetchall()[0][0]
