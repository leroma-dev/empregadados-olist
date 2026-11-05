1. ESCOPO
   raw.geolocalizacao -> refined.geolocalizacao. Script separado; os
   critérios da transformação (550.759 linhas) continuam valendo.

3. TIPOS
   latitude, longitude: DOUBLE. Motivo: medida contínua, nunca somada
     como dinheiro; 0 falhas de CAST nas 1.000.163 linhas.
   cep_prefixo: VARCHAR. Motivo: 245.733 linhas começam com zero.

5. DUPLICATAS
   Grão: um ponto observado (cep, lat, lng, cidade, uf).
   cep_prefixo NÃO é chave: 19.015 CEPs, até 1.146 linhas no mesmo CEP.
   Linha inteira repetida: mantém uma. 1.000.163 -> 738.332 (261.831 saem).
   Não agrega para um ponto por CEP. Motivo: média, mediana ou moda é a
   resposta a uma pergunta, e pergunta é trabalho de mart.

6. NULOS E ANOMALIAS
   0 nulos nas cinco colunas. Se aparecer, mantém.
   Ficam, sem correção:
     42 linhas fora da caixa lat -33,75..5,27 / lng -73,99..-34,79;
     8 CEPs com duas UFs;
     cidade com e sem acento ('sao paulo' e 'são paulo').
   Motivo: refined não corrige fato.

AVISO A QUEM CONSOME
   JOIN direto com clientes multiplica linhas (99.441 -> 15.083.455).
   Reduza a um ponto por CEP antes, num mart, com a regra escrita.