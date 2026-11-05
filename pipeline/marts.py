"""Marts: lê sql/marts/*.sql e grava cada arquivo como uma tabela no schema marts.

SPEC (fonte: pasta de specs, pedido de 2026-11-04; esclarecimentos do usuário incluídos)

Executa com: uv run python -m pipeline.marts

1. ESCOPO
   Lê de refined, escreve no schema marts. Nunca escreve em raw nem em refined.
   O schema marts é apagado e recriado a cada execução (DROP SCHEMA IF
   EXISTS marts CASCADE). Motivo: um mart cujo arquivo foi apagado não pode
   continuar existindo no banco.

2. UM ARQUIVO, UMA TABELA
   Lê todos os sql/marts/*.sql em ordem alfabética.
   Nome da tabela = nome do arquivo sem a extensão e sem o prefixo numérico:
     sql/marts/01_vendas_mensais.sql -> marts.vendas_mensais
   Executa: CREATE TABLE marts.<nome> AS <conteúdo do arquivo>
   Tira espaços e um ponto e vírgula do final do conteúdo, e nada mais.
   O Python não altera, não monta e não completa a SQL.
   Motivo: a regra de negócio mora inteira no arquivo .sql.
   Esclarecido: nome com caractere fora de [a-z0-9_] (ex.: 01_vendas-mensais.sql)
   vira identificador entre aspas: marts."vendas-mensais". Nome simples não leva aspas.

3. SAÍDA NA TELA
   Uma linha por mart, com a contagem vinda do banco, milhar com ponto:
     ✓ marts.vendas_mensais        24 linhas
   Linha final com o número de marts e o total de linhas.
   stdout reconfigurado para utf-8.
   Esclarecido: as linhas ✓ só são impressas depois do COMMIT. Motivo: uma
   linha "✓" de um mart que foi desfeito por um erro mentiria para quem lê.

4. ERRO
   Antes de tudo: se faltar qualquer uma das oito tabelas em refined,
   lista quais, diz para rodar "uv run python -m pipeline.transformacao"
   e encerra com sys.exit(1).
   Se um .sql falhar: mostra o nome do arquivo e a mensagem do DuckDB,
   não executa os seguintes, sys.exit(1).
   Se um mart voltar com zero linhas: mostra o nome e encerra com
   sys.exit(1). Motivo: mart vazio é quase sempre um JOIN que não casou,
   e um dashboard vazio parece um negócio parado.
   Se sql/marts/ não tiver nenhum arquivo: avisa e sys.exit(1).
   Antes de executar qualquer SQL: arquivo sem prefixo NN_ ou dois
   arquivos que dão o mesmo nome de tabela -> lista quais e sys.exit(1).
   Esclarecido: o prefixo é exatamente dois dígitos (00_ a 99_).
   Esclarecido: as mensagens de erro (✗ arquivo: mensagem) vão para stderr.
   Tudo roda numa transação só: se qualquer passo falhar (inclusive o
   mart vazio), o schema marts volta a ser o da última execução que deu
   certo. Motivo: um schema pela metade quebra o dashboard sem avisar.

CRITÉRIOS DE ACEITE
- Com um arquivo sql/marts/00_teste.sql contendo "SELECT 1 AS x", cria
  marts.teste com 1 linha.
- Apagar o arquivo e rodar de novo faz marts.teste desaparecer.
- Um arquivo com erro de sintaxe para tudo, com o nome do arquivo na tela,
  e marts continua exatamente como estava antes da execução.
- Um arquivo teste.sql, sem prefixo, para antes de executar qualquer SQL.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
"""

import re
import sys
from pathlib import Path

import duckdb

from pipeline import db
from pipeline.transformacao import TABELAS

PASTA_MARTS = Path(__file__).resolve().parent.parent / "sql" / "marts"
SCHEMA_ENTRADA = "refined"
SCHEMA_SAIDA = "marts"

PADRAO_ARQUIVO = re.compile(r"^([0-9]{2})_(.+)\.sql$")
NOME_SIMPLES = re.compile(r"^[a-z_][a-z0-9_]*$")


def milhar(n):
    return f"{n:,}".replace(",", ".")


def plural(n, singular, plural_):
    return singular if n == 1 else plural_


def sair(mensagem):
    print(mensagem, file=sys.stderr)
    sys.exit(1)


def identificador(nome):
    # Nome simples sai sem aspas, como na spec. Qualquer outro vai entre aspas.
    if NOME_SIMPLES.match(nome):
        return nome
    return '"' + nome.replace('"', '""') + '"'


def checar_refined(con):
    existentes = {
        linha[0]
        for linha in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [SCHEMA_ENTRADA],
        ).fetchall()
    }
    faltando = [t for t in TABELAS if t not in existentes]
    if faltando:
        print(
            f"Faltam em {SCHEMA_ENTRADA}: {', '.join(faltando)}",
            file=sys.stderr,
        )
        sair('Rode "uv run python -m pipeline.transformacao" antes.')


def listar_marts():
    """Devolve [(nome_da_tabela, caminho)] em ordem alfabética, ou encerra."""
    arquivos = sorted(PASTA_MARTS.glob("*.sql"))
    if not arquivos:
        sair(f"Nenhum arquivo .sql em {PASTA_MARTS}.")

    sem_prefixo = []
    marts = []
    for arquivo in arquivos:
        casamento = PADRAO_ARQUIVO.match(arquivo.name)
        if casamento is None:
            sem_prefixo.append(arquivo.name)
        else:
            marts.append((casamento.group(2), arquivo))
    if sem_prefixo:
        print("Arquivos sem prefixo NN_:", file=sys.stderr)
        for nome in sem_prefixo:
            print(f"  {nome}", file=sys.stderr)
        sair("Nada foi executado.")

    origens = {}
    for nome, arquivo in marts:
        origens.setdefault(nome, []).append(arquivo.name)
    repetidos = {nome: arqs for nome, arqs in origens.items() if len(arqs) > 1}
    if repetidos:
        print("Arquivos com o mesmo nome de tabela:", file=sys.stderr)
        for nome, arqs in repetidos.items():
            print(f"  {nome}: {', '.join(arqs)}", file=sys.stderr)
        sair("Nada foi executado.")

    return marts


def construir(con, marts):
    """Recria o schema marts dentro da transação aberta.

    Devolve (resultados, erro). erro é None se tudo deu certo; senão é a
    linha a mostrar, e quem chamou faz o ROLLBACK.
    """
    db.criar_schema(con, SCHEMA_SAIDA)  # nada além do DROP acima
    resultados = []
    for nome, arquivo in marts:
        sql = arquivo.read_text(encoding="utf-8").strip().removesuffix(";").rstrip()
        tabela = f"{SCHEMA_SAIDA}.{identificador(nome)}"
        try:
            con.execute(f"CREATE TABLE {tabela} AS {sql}").fetchall()
            n = con.execute(f"SELECT count(*) FROM {tabela}").fetchall()[0][0]
        except duckdb.Error as erro:
            return resultados, f"✗ {arquivo.name}: {erro}"
        if n == 0:
            return resultados, f"✗ marts.{nome}: zero linhas"
        resultados.append((nome, n))
    return resultados, None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    con = db.conectar()
    try:
        checar_refined(con)
        marts = listar_marts()

        con.execute("BEGIN TRANSACTION").fetchall()
        con.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_SAIDA} CASCADE").fetchall()
        resultados, erro = construir(con, marts)
        if erro:
            con.execute("ROLLBACK").fetchall()
            sair(erro)
        con.execute("COMMIT").fetchall()
    finally:
        con.close()

    # Impresso só depois do COMMIT, para não mostrar ✓ de algo desfeito.
    for nome, n in resultados:
        print(f"✓ {'marts.' + nome:<30} {milhar(n)} {plural(n, 'linha', 'linhas')}")
    total = sum(n for _, n in resultados)
    print(
        f"{len(resultados)} {plural(len(resultados), 'mart', 'marts')}, "
        f"{milhar(total)} {plural(total, 'linha', 'linhas')}"
    )


if __name__ == "__main__":
    main()
