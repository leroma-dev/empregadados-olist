CONTEXTO
Estou construindo um pipeline de dados em Python sobre o dataset público da
Olist. Trabalho com spec-driven development: a spec abaixo é a fonte da
verdade e o código é consequência dela. Não acrescente requisito que não
esteja escrito aqui. Se algo estiver ambíguo, pergunte antes de escrever código.

STACK
- Python 3.13, uv, DuckDB (olist.duckdb na raiz do projeto)

O QUE JÁ EXISTE (use, não reimplemente)
pipeline/db.py: conectar(), criar_schema(con, nome)
O schema raw, com nove tabelas, todas as colunas VARCHAR.

ARTEFATO A PRODUZIR
pipeline/transformacao.py, executável com:
  uv run python -m pipeline.transformacao

SPEC

1. ESCOPO
   Lê de raw, escreve em refined. Nunca escreve em raw.
   Tabelas que entram:   [ ]
   Tabelas que ficam de fora, e por quê:   [ ]

2. NOMES
   [ manter os nomes originais / renomear com o mapa abaixo ]
   Mapa coluna_original -> coluna_nova, tabela por tabela:   [ ]

3. TIPOS
   Datas:        [ tipo ]  formato declarado: [ ]
   Dinheiro:     [ tipo ]  motivo: [ ]
   Contagens:    [ tipo ]
   Identificadores que parecem número (CEP, ...):  [ tipo ]  motivo: [ ]

4. CONVERSÃO QUE FALHA
   [ vira nulo / para tudo ]  motivo: [ ]

5. DUPLICATAS
   Chave de cada tabela:   [ ]
   Chave repetida com conteúdo idêntico:   [ ]
   Chave repetida com conteúdo diferente:  [ ]

6. NULOS
   Regra geral:   [ ]
   Exceções, coluna por coluna, com motivo:   [ ]

7. SAÍDA NA TELA
   Por tabela: [ o que mostrar ]
   stdout reconfigurado para utf-8.

REEXECUÇÃO E ERRO (iguais à etapa 1)
   CREATE OR REPLACE, nunca acrescenta.
   Faltando tabela em raw: lista quais, manda rodar a ingestão, sys.exit(1).

CRITÉRIOS DE ACEITE
   [ como você vai saber que funcionou — números, não adjetivos ]

ENTREGA
1. A spec como docstring no topo do arquivo, com o motivo de cada regra.
2. O código, comentado só onde a decisão não é óbvia.
3. Uma lista final do que você assumiu e que não estava na spec.
