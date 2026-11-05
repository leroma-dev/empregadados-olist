# Diagrama entidade-relacionamento: schema raw (colunas completas)

Schema `raw` do olist.duckdb: nove tabelas, todas as colunas em `VARCHAR`.
O `raw` não declara chaves. As marcações PK e FK abaixo vêm da verificação nos dados.

```mermaid
erDiagram
    pedidos {
        varchar order_id PK
        varchar customer_id FK
        varchar order_status
        varchar order_purchase_timestamp
        varchar order_approved_at
        varchar order_delivered_carrier_date
        varchar order_delivered_customer_date
        varchar order_estimated_delivery_date
    }
    itens_pedido {
        varchar order_id PK, FK
        varchar order_item_id PK
        varchar product_id FK
        varchar seller_id FK
        varchar shipping_limit_date
        varchar price
        varchar freight_value
    }
    pagamentos {
        varchar order_id PK, FK
        varchar payment_sequential PK
        varchar payment_type
        varchar payment_installments
        varchar payment_value
    }
    avaliacoes {
        varchar review_id PK
        varchar order_id PK, FK
        varchar review_score
        varchar review_comment_title
        varchar review_comment_message
        varchar review_creation_date
        varchar review_answer_timestamp
    }
    clientes {
        varchar customer_id PK
        varchar customer_unique_id
        varchar customer_zip_code_prefix
        varchar customer_city
        varchar customer_state
    }
    vendedores {
        varchar seller_id PK
        varchar seller_zip_code_prefix
        varchar seller_city
        varchar seller_state
    }
    produtos {
        varchar product_id PK
        varchar product_category_name FK
        varchar product_name_lenght
        varchar product_description_lenght
        varchar product_photos_qty
        varchar product_weight_g
        varchar product_length_cm
        varchar product_height_cm
        varchar product_width_cm
    }
    traducao_categorias {
        varchar product_category_name PK
        varchar product_category_name_english
    }
    geolocalizacao {
        varchar geolocation_zip_code_prefix
        varchar geolocation_lat
        varchar geolocation_lng
        varchar geolocation_city
        varchar geolocation_state
    }

    clientes ||--|| pedidos : "faz (1 pedido por customer_id)"
    pedidos ||--o{ itens_pedido : "contém"
    pedidos ||--o{ pagamentos : "é pago em"
    pedidos ||--o{ avaliacoes : "recebe"
    produtos ||--o{ itens_pedido : "vendido em"
    vendedores ||--o{ itens_pedido : "vende"
    traducao_categorias ||--o{ produtos : "traduz categoria"
    clientes }o..o{ geolocalizacao : "CEP (lógico, não é FK)"
    vendedores }o..o{ geolocalizacao : "CEP (lógico, não é FK)"
```

## Chaves e relações verificadas

| Relação | Órfãos no filho | Pais sem filho | Máx. filhos por pai |
|---|---|---|---|
| pedidos → clientes (`customer_id`) | 0 | 0 | 1 |
| itens_pedido → pedidos (`order_id`) | 0 | 775 | 21 |
| pagamentos → pedidos (`order_id`) | 0 | 1 | 29 |
| avaliacoes → pedidos (`order_id`) | 0 | 768 | 3 |
| itens_pedido → produtos (`product_id`) | 0 | 0 | 527 |
| itens_pedido → vendedores (`seller_id`) | 0 | 0 | 2033 |
| produtos → traducao_categorias | 13 | 0 | 3029 |
| clientes / vendedores → geolocalizacao (CEP) | 278 / 7 | — | — |

As chaves únicas confirmadas: `pedidos.order_id`, `clientes.customer_id`, `produtos.product_id`, `vendedores.seller_id`, `traducao_categorias.product_category_name`, `itens_pedido (order_id, order_item_id)`, `pagamentos (order_id, payment_sequential)`.

`avaliacoes.review_id` não é chave sozinho: 98.410 valores distintos em 99.224 linhas. A chave que a spec define é `(avaliacao_id, pedido_id)`.

Os CEPs de `clientes` e `vendedores` não batem todos com `geolocalizacao`, então essa ligação é lógica e não uma chave estrangeira.
