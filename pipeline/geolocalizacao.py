"""Geolocalização: lê raw.geolocalizacao e grava refined.geolocalizacao no olist.duckdb.

Execução: uv run python -m pipeline.geolocalizacao

SPEC (fonte: spec/geolocalizacao.md, seções 1, 3, 5 e 6; regras de erro, saída e
reexecução herdadas de spec/transformacao.md, conforme a própria spec pede)

1. ESCOPO
   Lê de raw.geolocalizacao e grava refined.geolocalizacao. Nunca escreve em raw.
   Script separado de transformacao.py: a tabela não entra no conjunto das oito.
   Os critérios da transformação continuam valendo (conversão que falha, saída
   na tela, reexecução, erro quando a entrada falta).

2. NOMES (não estava na spec; assumido, ver lista final)
   geolocation_zip_code_prefix -> cep_prefixo
   geolocation_lat              -> latitude
   geolocation_lng              -> longitude
   geolocation_city             -> cidade
   geolocation_state            -> uf
   Motivo: latitude/longitude são os nomes que a seção 3 da spec usa; cep, cidade
   e uf seguem o vocabulário de clientes e vendedores em refined.

3. TIPOS
   latitude, longitude: DOUBLE. Motivo: medida contínua, nunca somada como dinheiro;
     0 falhas de CAST nas 1.000.163 linhas.
   cep_prefixo: VARCHAR. Motivo: 245.733 linhas começam com zero; CEP é
     identificador, nunca é somado, e como número perderia o zero.
   cidade, uf: VARCHAR, sem alteração.
   A conversão é feita em SQL pelo DuckDB (CAST), disparada pelo Python.

4. CONVERSÃO QUE FALHA (herdada de transformacao.md, seção 4)
   CAST estoura; nunca TRY_CAST nem errors="coerce". Ao falhar: diz tabela,
   coluna e um exemplo do valor, e encerra com sys.exit(1).
   Motivo: um nulo fabricado pela conversão fica indistinguível de um nulo real.

5. DUPLICATAS
   Grão: um ponto observado (cep_prefixo, latitude, longitude, cidade, uf).
   cep_prefixo NÃO é chave: 19.015 CEPs, até 1.146 linhas no mesmo CEP.
   A chave é a linha inteira, então não há chave repetida com conteúdo diferente
   (a checagem de conflito da transformação não se aplica aqui).
   Linha inteira repetida: mantém uma. 1.000.163 -> 738.332 (261.831 saem).
   Não agrega para um ponto por CEP. Motivo: média, mediana ou moda é a resposta
   a uma pergunta, e pergunta é trabalho de mart.

6. NULOS E ANOMALIAS
   Nenhuma linha é apagada por ter nulo; nenhum nulo é preenchido. Hoje são 0 nulos.
   Ficam, sem correção:
     42 linhas fora da caixa lat -33,75..5,27 / lng -73,99..-34,79;
     8 CEPs com duas UFs;
     cidade com e sem acento ('sao paulo' e 'são paulo').
   Motivo: refined não corrige fato.

7. SAÍDA NA TELA
   Uma linha por tabela, no formato:
     refined.geolocalizacao     1.000.163 -> 738.332 linhas  (261.831 duplicatas)
   Contagens vindas do banco, milhar com ponto. stdout reconfigurado para utf-8.

REEXECUÇÃO
   CREATE OR REPLACE TABLE, nunca acrescenta. Rodar dez vezes = rodar uma.

ERRO
   Se raw.geolocalizacao não existir, diz para rodar
   "uv run python -m pipeline.ingestao" e encerra com sys.exit(1).

AVISO A QUEM CONSOME
   JOIN direto com clientes multiplica linhas (99.441 -> 15.083.455).
   Quem consome deve reduzir a um ponto por CEP antes, num mart, com a regra escrita.

CRITÉRIOS DE ACEITE
- refined.geolocalizacao tem 738.332 linhas; raw continua com 1.000.163.
- DESCRIBE: latitude e longitude DOUBLE; cep_prefixo VARCHAR com zero à esquerda.
- Nulos depois = nulos antes (0 em cada coluna).
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
"""

import sys

import duckdb

from pipeline import db

SCHEMA_ENTRADA = "raw"
SCHEMA_SAIDA = "refined"
TABELA = "geolocalizacao"

# Transformação literal: lê de raw e devolve as colunas já renomeadas e tipadas.
# Não apaga linha nem preenche nulo.
SELECT_GEOLOCALIZACAO = """
SELECT
    "geolocation_zip_code_prefix" AS cep_prefixo,
    CAST("geolocation_lat" AS DOUBLE) AS latitude,
    CAST("geolocation_lng" AS DOUBLE) AS longitude,
    "geolocation_city" AS cidade,
    "geolocation_state" AS uf
FROM raw.geolocalizacao
"""

COLUNAS_RAW = [
    "geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
    "geolocation_city", "geolocation_state",
]

# Colunas convertidas: (coluna em raw, coluna em refined, tipo). Usado só para
# localizar a coluna que falhou.
TIPADAS = [
    ("geolocation_lat", "latitude", "DOUBLE"),
    ("geolocation_lng", "longitude", "DOUBLE"),
]

# Chave de duplicatas é a linha inteira (ver docstring, seção 5).
CHAVE = ["cep_prefixo", "latitude", "longitude", "cidade", "uf"]


def milhar(n):
    return f"{n:,}".replace(",", ".")


def quoted(nome):
    return f'"{nome}"'


def expressao(ref, tipo):
    # Mesma conversão do SELECT literal: CAST, que estoura.
    return f"CAST({ref} AS {tipo})"


def tabela_existe(con):
    return con.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = ? AND table_name = ?",
        [SCHEMA_ENTRADA, TABELA],
    ).fetchone()[0] > 0


def verificar_mapa(con):
    # O SELECT literal tem que ler exatamente as colunas de raw: sem coluna solta
    # (que seria descartada em silêncio) e sem coluna faltando.
    no_raw = {
        linha[0]
        for linha in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ?",
            [SCHEMA_ENTRADA, TABELA],
        ).fetchall()
    }
    esperadas = set(COLUNAS_RAW)
    fora = sorted(no_raw - esperadas)
    faltam = sorted(esperadas - no_raw)
    if fora or faltam:
        print(f"ERRO: raw.{TABELA} não bate com o SELECT da transformação.")
        if fora:
            print(f"  colunas no raw fora do mapa: {', '.join(fora)}")
        if faltam:
            print(f"  colunas do mapa ausentes no raw: {', '.join(faltam)}")
        sys.exit(1)


def primeiro_valor_que_falha(con, origem, tipo):
    # Só roda no caminho de erro, para mostrar um exemplo.
    valores = con.execute(
        f"SELECT DISTINCT {quoted(origem)} FROM {SCHEMA_ENTRADA}.{quoted(TABELA)} "
        f"WHERE {quoted(origem)} IS NOT NULL ORDER BY 1"
    ).fetchall()
    consulta = f"SELECT {expressao(quoted('v'), tipo)} FROM (SELECT ? AS v)"
    for (valor,) in valores:
        try:
            con.execute(consulta, [valor]).fetchall()
        except duckdb.Error:
            return valor
    return None


def reportar_falha(con, erro):
    # O SELECT literal estourou. Acha a coluna e um valor que não converte.
    for origem, destino, tipo in TIPADAS:
        try:
            con.execute(
                f"SELECT count({expressao(quoted(origem), tipo)}) "
                f"FROM {SCHEMA_ENTRADA}.{quoted(TABELA)}"
            ).fetchall()
        except duckdb.Error as erro_coluna:
            exemplo = primeiro_valor_que_falha(con, origem, tipo)
            print(f"ERRO de conversão: {SCHEMA_ENTRADA}.{TABELA}.{origem} -> {destino} ({tipo})")
            print(f"  valor que não converteu: {exemplo!r}")
            print(f"  detalhe do DuckDB: {erro_coluna}")
            sys.exit(1)
    print(f"ERRO de conversão em {SCHEMA_ENTRADA}.{TABELA}: {erro}")
    sys.exit(1)


def preparar(con):
    # Materializa o SELECT literal em tabela temporária e conta as linhas sem repetição.
    # Não grava refined: a gravação só acontece depois que tudo passa.
    try:
        con.execute(f"CREATE OR REPLACE TEMP TABLE tmp_{TABELA} AS {SELECT_GEOLOCALIZACAO}")
    except duckdb.Error as erro:
        reportar_falha(con, erro)

    entrada = con.execute(
        f"SELECT count(*) FROM {SCHEMA_ENTRADA}.{quoted(TABELA)}"
    ).fetchone()[0]
    saida = con.execute(
        f"SELECT count(*) FROM (SELECT DISTINCT * FROM tmp_{TABELA})"
    ).fetchone()[0]
    return {"entrada": entrada, "saida": saida, "duplicatas": entrada - saida}


def gravar(con):
    chave_sql = ", ".join(CHAVE)
    con.execute(
        f"CREATE OR REPLACE TABLE {SCHEMA_SAIDA}.{quoted(TABELA)} AS "
        f"SELECT DISTINCT * FROM tmp_{TABELA} ORDER BY {chave_sql}"
    )
    return con.execute(
        f"SELECT count(*) FROM {SCHEMA_SAIDA}.{quoted(TABELA)}"
    ).fetchone()[0]


def nulos_mantidos(con):
    # nulos = total - count(coluna): count ignora nulo. Contagem vinda do banco.
    colunas = [
        linha[0]
        for linha in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
            [SCHEMA_SAIDA, TABELA],
        ).fetchall()
    ]
    expr = ", ".join(f"count(*) - count({quoted(c)})" for c in colunas)
    valores = con.execute(f"SELECT {expr} FROM {SCHEMA_SAIDA}.{quoted(TABELA)}").fetchone()
    return [(c, n) for c, n in zip(colunas, valores) if n > 0]


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    con = db.conectar()
    try:
        if not tabela_existe(con):
            print(f"Tabela {SCHEMA_ENTRADA}.{TABELA} não encontrada.")
            print('Rode "uv run python -m pipeline.ingestao" antes desta etapa.')
            sys.exit(1)

        verificar_mapa(con)

        # Fase 1: materializa e conta. Qualquer falha sai aqui, antes de refined ser tocado.
        contagem = preparar(con)

        # Fase 2: grava refined.
        db.criar_schema(con, SCHEMA_SAIDA)
        saida = gravar(con)
        nome = f"{SCHEMA_SAIDA}.{TABELA}"
        print(
            f"{nome:<28} {milhar(contagem['entrada']):>7} -> {milhar(saida):>7} linhas  "
            f"({milhar(contagem['duplicatas'])} duplicatas)"
        )
        nulos = nulos_mantidos(con)
        if nulos:
            texto = ", ".join(f"{col} {milhar(n)}" for col, n in nulos)
            print(f"    nulos mantidos: {texto}")
        print(f"Total: {milhar(saida)} linhas")
    finally:
        con.close()


if __name__ == "__main__":
    main()
