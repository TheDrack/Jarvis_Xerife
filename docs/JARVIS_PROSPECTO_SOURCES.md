# Jarvis Prospecto — fontes de dados pesquisadas

**Status:** catálogo multi-fonte criado; adaptadores locais para Receita Federal, importação autorizada do diretório ACATE e snapshots de indicadores agregados do Observatório ACATE.
**Escopo:** de onde vêm as empresas do pipeline, o que cada fonte permite armazenar e quanto custa.

## Catálogo multi-fonte implementado

O catálogo declarativo está em config/prospecting/sources.json e é validado por ProspectSourceCatalog/load_source_catalog. Cada fonte declara tipo, método de aquisição, status, cobertura, dimensões, capacidade de gerar entidades ou indicadores e permissão de armazenamento. Null/unknown não equivale a permissão.

Fontes catalogadas:
- Receita Federal CNPJ: registro de empresas e estabelecimentos.
- ACATE Associados: diretório setorial; importação CSV somente com confirmação explícita de permissão.
- Observatório ACATE: indicadores agregados; adaptador de snapshot JSON preserva período, metodologia, publicação e origem.
- Mapa de Empresas/MDIC e IBGE SIDRA: estatística pública.
- FIESC, JUCESC/SICOS: inteligência industrial e registros estaduais em validação.
- PNCP: editais, itens, atas e contratos públicos.
- Carreiras oficiais: vagas C2B.
- Rede de Inovação Florianópolis: incubadoras, centros e programas.
- INPI: marcas, patentes e programas de computador.
- Comex Stat: comércio exterior por NCM, município, país, UF e valor.
- FAPESC/FINEP: chamadas de fomento e financiamento.
- CEIS/CNEP: diligência e risco de fornecedores.

Arquivos e contratos:
- config/prospecting/sources.json
- app/domain/prospecting/source_registry.py
- app/domain/prospecting/market_intelligence.py
- app/adapters/infrastructure/prospecting/acate_directory.py
- app/adapters/infrastructure/prospecting/acate_observatory.py

O diretório ACATE e o Observatório não são intercambiáveis: o primeiro pode gerar registros de organizações somente após autorização de reutilização; o segundo gera métricas agregadas, nunca leads individuais.

## Decisão

| Papel | Fonte | Por quê |
|---|---|---|
| Base durável de discovery | Dados Abertos do CNPJ — Receita Federal | Gratuita, oficial, mensal, licença CC-BY, com CNAE, endereço e situação por estabelecimento. É a única fonte que sustenta um banco de empresas sem violar termos. |
| Verificação e enriquecimento pontual | BrasilAPI, CNPJ.ws (pública), CNPJá (open) | Sem chave, 3–5 requisições por minuto. Servem para checar um CNPJ específico, não para montar base em massa. |
| Enriquecimento em lote (quando houver verba) | Casa dos Dados, CNPJ.ws pago, Serpro | Contatos, Simples/MEI e quadro societário com preço e limite publicados. |
| **Não usar como base** | Google Places | Os termos proíbem pré-carregar, cachear ou armazenar nomes, endereços e telefones; só `place_id` é durável e coordenadas por até 30 dias. |

## O que a base oficial entrega e o que ela não entrega

Entrega, por estabelecimento: CNPJ completo, matriz/filial, nome fantasia, situação cadastral e data, data de início, CNAE principal e secundários, endereço completo, CEP, UF, município (código da Receita), telefone(s) e e-mail cadastrados. Por empresa: razão social, natureza jurídica, capital social e **porte** (MEI/ME/EPP/Demais). Tabelas de domínio (`Cnaes`, `Municipios`, `Naturezas`, `Qualificacoes`, `Paises`, `Motivos`) traduzem os códigos.

Não entrega: **quantidade de funcionários**, **faturamento**, **site** e **coordenadas geográficas**. Consequências práticas:

- O critério de porte do ICP não pode usar `employee_count` com essa fonte; hoje ele fica `unknown` e o prospect sai marcado para verificação. Usar o campo `porte` como substituto exige nova decisão de contrato (não fazer isso silenciosamente).
- Site e redes sociais precisam de enriquecimento por CNPJ ou verificação por busca — nunca de Places persistido.
- Qualquer serviço que exiba "funcionários" ou "faturamento" a partir do CNPJ está **estimando**, não publicando dado oficial.

## Números e termos verificados

| Fonte | Custo | Limite | Licença/termos |
|---|---|---|---|
| Receita Federal — Dados Abertos CNPJ | R$ 0 | ~7,8 GB compactados/mês; 37 arquivos; ~73 milhões de estabelecimentos | CC-BY (atribuição obrigatória) |
| BrasilAPI | R$ 0 | uso razoável, sem limite publicado | pública |
| CNPJ.ws pública | R$ 0 | 3 req/min por IP | pública |
| CNPJá open | R$ 0 | 5 req/min por IP | pública |
| Casa dos Dados | R$ 0,01/CNPJ; planos de R$ 29,90 (5 mil) a R$ 749,90 | conforme plano | comercial |
| CNPJ.ws pago | planos mensais | até 2.000 req/min | comercial |
| Serpro | cobrança por consulta | OAuth2 | oficial, contrato |

Para os primeiros R$ 1.000 a recomendação é **R$ 0 de custo de dados**: base da Receita + APIs gratuitas para conferência pontual. Plano pago só quando houver cliente pagando por volume.

## Como o adaptador funciona

`app/adapters/infrastructure/prospecting/cnpj_open_data.py` implementa o contrato `DiscoveryProvider` lendo os CSVs oficiais extraídos localmente:

```python
from app.domain.prospecting.discovery import DiscoveryQuery
from app.adapters.infrastructure.prospecting import CnpjOpenDataAdapter, CnpjOpenDataFiles

adapter = CnpjOpenDataAdapter(
    CnpjOpenDataFiles(
        establishments=Path("Estabelecimentos0.csv"),
        companies=Path("Empresas0.csv"),
        municipalities=Path("Municipios.csv"),
        cnaes=Path("Cnaes.csv"),
    )
)
result = adapter.discover(
    DiscoveryQuery(uf="SC", municipalities=("São José",), cnae_prefixes=("4120",), limit=200)
)
```

Regras aplicadas pelo adaptador:

- Filtra por UF, município (comparação sem acento/caixa), prefixo de CNAE e situação ativa (código `02`).
- Mantém **uma linha por empresa** (raiz do CNPJ): o primeiro estabelecimento encontrado é preservado, o que na ordenação oficial é a matriz.
- Cada empresa sai com uma `ProspectEvidence` apontando para o conjunto oficial, com a licença CC-BY preenchida — a atribuição é obrigatória na entrega ao cliente.
- Conta linhas lidas, casadas e malformadas, e sinaliza `truncated` quando o limite da consulta é atingido. Falha de arquivo é erro explícito, não resultado vazio.
- O DuckDB preserva as colunas de telefone/e-mail do arquivo oficial, mas o domínio e as respostas MCP não devolvem os valores. A consulta pode filtrar apenas pela presença de telefone/e-mail/fax. O arquivo DuckDB deve permanecer em armazenamento privado do host; não exportar contatos nem iniciar outreach sem política de finalidade, retenção, acesso e oposição.

## Limites operacionais conhecidos

- A varredura em Python puro percorre dezenas de milhões de linhas: serve para carga mensal, não para consulta interativa. Para consulta repetida, materializar os mesmos CSVs em DuckDB ou PostgreSQL uma vez.
- O endereço dos arquivos já mudou (o antigo `dadosabertos.rfb.gov.br` saiu do ar); mantenha a URL configurável e valide os arquivos antes de substituir a carga anterior.
- O CSV oficial não traz cabeçalho. As posições usadas estão no layout oficial em `gov.br/receitafederal/dados/cnpj-metadados.pdf`; ler sem o layout desloca colunas silenciosamente.
- Espelhos em Parquet (por exemplo o dataset `cnpjaberto` no Hugging Face) servem para análise local mais barata, mas são espelho de terceiro: para entrega comercial, cite a Receita como fonte.

## Limites legais e de privacidade

- CC-BY exige atribuição à Receita Federal em qualquer planilha entregue.
- Não fazer scraping de diretórios ou redes sociais para contornar termos; Places não pode virar tabela própria.
- Contato pessoal (nome, telefone, e-mail individual) continua fora do domínio: incluir exige finalidade, base legal, minimização, retenção e opt-out documentados, além de canal de oposição.
- Dados de contato de pessoa jurídica cadastrados na Receita ainda exigem finalidade comercial declarada e respeito a pedido de não contato (`DO_NOT_CONTACT` é terminal no domínio). No Prospecto, os valores não são expostos; filtros de presença não revelam o destino.

## Próximos passos sugeridos

1. Orquestração sem banco: `DiscoveryQuery` → `qualify_prospect` → `build_deliverable_csv` num comando único.
2. Mapear o campo `porte` para um critério de porte do ICP, com decisão explícita de contrato.
3. Enriquecer site/telefone somente após definir a política de contato e o canal de opt-out.


## Filtros CNPJ ampliados

DiscoveryQuery agora prevê filtros opcionais para:
- Matriz/filial e situação cadastral;
- Bairro e CEP;
- Data de início da atividade;
- Porte cadastral, natureza jurídica e faixa de capital social;
- Opção pelo Simples e MEI (exigem que o arquivo auxiliar Simples tenha sido ingerido);
- CNAE principal e secundário.

O materializador preserva os sete campos do arquivo Empresas (razão social, natureza jurídica, qualificação do responsável, capital social, porte e ente federativo, além da raiz CNPJ) e pode carregar Simples, Naturezas, Qualificações, Países e Motivos como tabelas auxiliares. Dados pessoais de sócios não são ingeridos nesta etapa; contatos cadastrais continuam sem exposição no domínio comercial.

O catálogo de filtros só deve habilitar filtros auxiliares quando a respectiva tabela tiver sido carregada. A ausência de dados não pode ser interpretada como ausência de empresas elegíveis.


## Filtros de presença sem expor contato

O DuckDB permite filtrar has_phone, has_email e has_fax. O resultado de ProspectCompany não inclui os números nem o e-mail. A finalidade desse filtro é medir a completude cadastral e priorizar enriquecimento/revisão, não autorizar disparo automático. O CSV/manifesto comercial não recebe os valores brutos.
