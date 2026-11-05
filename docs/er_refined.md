# Diagrama entidade-relacionamento: schema refined

Schema `refined` do olist.duckdb: oito tabelas, com colunas renomeadas para português e tipadas
conforme `spec/transformacao.md`. A tabela `geolocalizacao`, que existe no `raw`, está fora do
`refined` por decisão da spec (seção 1: nenhum mart do curso usa).

```mermaid
erDiagram
    pedidos {
        varchar pedido_id PK
        varchar cliente_id FK
        varchar status
        timestamp data_compra
        timestamp data_aprovacao
        timestamp data_envio
        timestamp data_entrega
        date data_entrega_prevista
    }
    itens_pedido {
        varchar pedido_id PK, FK
        integer item_seq PK
        varchar produto_id FK
        varchar vendedor_id FK
        timestamp data_limite_envio
        decimal preco
        decimal frete
    }
    pagamentos {
        varchar pedido_id PK, FK
        integer pagamento_seq PK
        varchar tipo
        integer parcelas
        decimal valor
    }
    avaliacoes {
        varchar avaliacao_id PK
        varchar pedido_id PK, FK
        integer nota
        varchar titulo
        varchar comentario
        date data_criacao
        timestamp data_resposta
    }
    clientes {
        varchar cliente_id PK
        varchar cliente_unico_id
        varchar cep_prefixo
        varchar cidade
        varchar uf
    }
    vendedores {
        varchar vendedor_id PK
        varchar cep_prefixo
        varchar cidade
        varchar uf
    }
    produtos {
        varchar produto_id PK
        varchar categoria FK
        integer tamanho_nome
        integer tamanho_descricao
        integer qtd_fotos
        integer peso_g
        integer comprimento_cm
        integer altura_cm
        integer largura_cm
    }
    traducao_categorias {
        varchar categoria PK
        varchar categoria_en
    }
    geolocalizacao_AUSENTE {
        varchar cep_prefixo "ausente no refined, por decisão da spec"
    }

    clientes ||--|| pedidos : "faz (1 pedido por cliente_id)"
    pedidos ||--o{ itens_pedido : "contém"
    pedidos ||--o{ pagamentos : "é pago em"
    pedidos ||--o{ avaliacoes : "recebe"
    produtos ||--o{ itens_pedido : "vendido em"
    vendedores ||--o{ itens_pedido : "vende"
    traducao_categorias ||--o{ produtos : "traduz categoria"
    clientes }o..o{ geolocalizacao_AUSENTE : "CEP: ligação perdida"
    vendedores }o..o{ geolocalizacao_AUSENTE : "CEP: ligação perdida"
```

## Tabelas do raw que faltam no refined

| Tabela do raw | Status no refined | Motivo |
|---|---|---|
| `geolocalizacao` (1.000.163 linhas) | **Ausente** | Spec, seção 1: nenhum mart do curso usa. |

As outras oito tabelas do `raw` estão no `refined`, com o mesmo número de colunas e nomes em português.

## Consequência do que falta

Em `raw`, `clientes.cep_prefixo` e `vendedores.cep_prefixo` tinham ligação lógica com `geolocalizacao`, sem chave estrangeira. No `refined`, essa ligação não existe mais: não há como cruzar CEP com latitude e longitude. O diagrama mostra a ligação como perdida.

## Chaves e cardinalidades (verificadas no refined)

As chaves são as da spec, seção 5. Nenhuma tabela tem chave estrangeira declarada; as relações são as que os dados sustentam, as mesmas verificadas no `raw`.

- `pedidos (pedido_id)`, `clientes (cliente_id)`, `produtos (produto_id)`, `vendedores (vendedor_id)`, `traducao_categorias (categoria)`
- `itens_pedido (pedido_id, item_seq)`, `pagamentos (pedido_id, pagamento_seq)`, `avaliacoes (avaliacao_id, pedido_id)`

Tipos: `DECIMAL(10,2)` para `preco`, `frete` e `valor`; `INTEGER` para as contagens e medidas; `TIMESTAMP` para as cinco datas com hora em `pedidos` e as demais datas com hora; `DATE` para `data_entrega_prevista` e `data_criacao`; `cep_prefixo` continua `VARCHAR`.
