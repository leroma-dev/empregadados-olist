"""Explorar o olist.duckdb pelo navegador, com a UI oficial do DuckDB.

Execução: uv run python ui.py   (a ingestão precisa ter rodado antes)

SPEC (fonte: spec.md, seção "SPEC DO ui.py")

U1. O QUE FAZ
    Abre o olist.duckdb da raiz do projeto, instala e carrega a extensão ui
    (INSTALL ui; LOAD ui;) e chama CALL start_ui(), que sobe o servidor em
    http://localhost:4213 e abre o navegador.

U2. FICA DE PÉ ATÉ CTRL+C
    A extensão serve enquanto a conexão estiver viva. O script mantém o
    processo rodando, imprime a URL e a instrução "Ctrl+C para encerrar", e no
    Ctrl+C fecha a conexão e sai limpo, sem traceback.
    Por quê: o arquivo .duckdb aceita um único processo escrevendo. Com o ui.py
    de pé, a ingestão falha com "Could not set lock on file". Saber como
    desligar o servidor faz parte da ferramenta.

U3. NÃO CRIA BANCO
    Se olist.duckdb não existir, diz que é preciso rodar a ingestão antes e sai
    com sys.exit(1). Por isso NÃO usa conectar() de pipeline/db.py, que cria o
    arquivo quando ele falta: um banco vazio aberto no navegador parece
    ingestão quebrada.

U4. SEPARAÇÃO
    ui.py não importa pipeline/ingestao.py, e a ingestão não importa ui.py. A
    ingestão não sobe servidor, não abre navegador e não depende da extensão ui.

U5. SAÍDA NA TELA
    stdout reconfigurado para utf-8, pelo mesmo motivo da ingestão (Prompt de
    Comando do Windows).

CRITÉRIOS DE ACEITE
- uv run python ui.py abre o navegador em localhost:4213 e o schema raw aparece
  com as nove tabelas.
- Ctrl+C devolve o terminal sem traceback, e logo depois a ingestão roda sem
  erro de lock.
- Renomear olist.duckdb faz o ui.py parar com a mensagem, sem criar arquivo novo.
"""

import sys
import time
from pathlib import Path

import duckdb


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    banco = Path(__file__).resolve().parent / "olist.duckdb"
    # Checar antes de conectar: duckdb.connect() criaria o arquivo vazio.
    if not banco.is_file():
        print(f"Banco não encontrado: {banco}")
        print("Rode a ingestão antes: uv run python -m pipeline.ingestao")
        sys.exit(1)

    con = duckdb.connect(str(banco))
    try:
        # con.execute("UPDATE EXTENSIONS")
        # con.execute("FORCE INSTALL ui").fetchall()
        con.execute("INSTALL ui").fetchall()
        con.execute("LOAD ui").fetchall()
        con.execute("CALL start_ui()").fetchall()
        print("UI do DuckDB em http://localhost:4213")
        print("Ctrl+C para encerrar")
        # A extensão serve enquanto esta conexão estiver aberta.
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
