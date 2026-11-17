# Prospecto — catálogo ampliado de fontes e oportunidades

## Princípio de arquitetura

O Prospecto separa três tipos de informação:
1. **Registros de entidades**: empresas, estabelecimentos, fornecedores, startups e organizações.
2. **Oportunidades transacionais**: vagas, editais, compras, contratos e pedidos de cotação.
3. **Inteligência agregada**: indicadores setoriais, emprego, faturamento, crescimento, densidade empresarial e geografia econômica.

Não converter estatísticas agregadas em atributos de uma empresa individual. Toda observação deve carregar fonte, URL, data de coleta, período de referência, metodologia, licença/termos, campos sustentados e confiança.

## Fontes identificadas

| Fonte | Papel | Dados úteis | Estado no catálogo |
|---|---|---|---|
| Receita Federal CNPJ | Registro-base | CNAE, situação, endereço, porte, natureza jurídica | Base durável |
| ACATE Associados | Diretório setorial | Associadas, polos, verticais, descrição de soluções | Exportação somente com permissão confirmada |
| Observatório ACATE | Inteligência de mercado | Empresas, empregos, faturamento, produtividade, verticais e regiões | Indicadores agregados |
| Mapa de Empresas MDIC | Estatística pública | Aberturas, baixas, tempo de registro, Inova Simples | Pesquisa |
| IBGE SIDRA | Estatística pública | População, PIB municipal, estrutura econômica e serviços | Planejado: API oficial |
| FIESC Observatório | Inteligência industrial | Emprego, produção, exportação, cadeia produtiva | Planejado: validar exportação/termos |
| JUCESC/SICOS | Registro estadual | Constituição e alterações empresariais | Planejado: validar acesso/API |
| PNCP | Oportunidades B2G | Editais, itens, compradores, prazos e contratos | Planejado: API oficial |
| Carreiras oficiais | Oportunidades C2B | Vagas, cargo, localidade, remoto, prazo e URL | Planejado |
| Rede de Inovação Florianópolis | Ecossistema | Incubadoras, centros, programas e startups | Pesquisa |
| INPI | Sinais de inovação | Marcas, patentes e classes tecnológicas | Planejado |

## ACATE: dois produtos de dados diferentes

- O diretório de associados apresenta mais de 1.500 empresas e filtros por polo e vertical. Ele é uma fonte de entidades candidatas, mas a página pública não foi identificada como API aberta com licença irrestrita de reutilização. O adaptador AcateDirectoryAdapter importa CSV fornecido pelo operador e exige reuse_permission_confirmed=True; não faz scraping.
- O Observatório ACATE é uma fonte de indicadores agregados. O site reporta, entre outros indicadores, 34,2 mil empresas de tecnologia e 102,2 mil colaboradores em SC em 2025, e para Florianópolis cerca de 7,4 mil empresas, 44,8 mil empregos e R$ 14 bilhões em faturamento de tecnologia em 2025. São indicadores de mercado, não uma lista de empresas. Os números devem ser persistidos com a data/período e metodologia exatos da publicação.

Fontes:
- https://www.acate.com.br/associados/
- https://www.observatorioacate.com.br/
- https://www.observatorioacate.com.br/florianopolis/
- https://www.gov.br/pt-br/servicos/obter-dados-estatisticos-no-mapa-de-empresa
- https://sidra.ibge.gov.br/
- https://observatorio.fiesc.com.br/
- https://www.jucesc.sc.gov.br/
- https://pncp.gov.br/
- https://redeinovacao.floripa.br/
- https://www.gov.br/inpi/pt-br

## O que passa a integrar o roadmap

1. **B2G**: PNCP e Compras.gov — oportunidades de venda para órgãos públicos, com itens, prazos, requisitos e contratos.
2. **C2B**: vagas reais em páginas oficiais de carreira e APIs autorizadas; nunca inferir vagas a partir do CNPJ.
3. **Startup/innovation graph**: incubadoras, aceleradoras, fundos, programas, universidades, parques tecnológicos e centros de inovação.
4. **Propriedade intelectual**: marcas e patentes como sinais de inovação e especialização tecnológica, com minimização de dados pessoais.
5. **Cadeias de fornecimento**: FIESC, ComexStat e dados de compras para mapear compradores, fornecedores e dependências setoriais.
6. **Sinais de mercado**: abertura/baixa de empresas, emprego, PIB municipal, ISS setorial, investimentos e crescimento.
7. **Enriquecimento empresarial**: sites oficiais, portfólios e catálogos de produtos/serviços, com evidência individual e revisão de termos.
8. **Dados de relacionamento**: feiras, eventos, associações e comunidades, sem presumir que presença pública equivale a consentimento para contato.

## GAPs de ingestão CNPJ a resolver

A tabela establishments reconhece o layout de estabelecimento, mas a carga atual materializa somente parte dos dados auxiliares:
- companies: atualmente guarda razão social e porte; precisa preservar natureza jurídica, qualificação, capital e ente federativo.
- partners: arquivo de sócios ainda não integrado.
- simples: arquivo de opção Simples/MEI ainda não integrado.
- Tabelas de domínio: CNAE e município existem; Naturezas, Qualificações, Países e Motivos precisam ser adicionadas.
- O catálogo de filtros deve refletir apenas colunas efetivamente ingeridas. Campos pessoais de sócios e contatos cadastrais precisam de política de acesso e finalidade antes de qualquer exposição.
- Preservar CNPJ como string; preparar migração para o identificador alfanumérico sem remover letras.

## Regras de governança

- publicly_visible não implica durable_storage_allowed.
- durable_storage_allowed=null significa desconhecido e bloqueia persistência até revisão.
- Nenhuma fonte autoriza automaticamente outreach.
- Fonte agregada não cria leads individuais.
- Dados externos são não confiáveis; validar URL, schema, tamanho, origem e conteúdo.
- Deduplicação usa CNPJ completo/raiz quando houver; para entidades sem CNPJ, usar identificador da fonte e resolução de identidade conservadora.
- Registrar licença/termos, data de coleta, data de referência, atualização, cobertura e limitações.
- Falha de fonte deve aparecer como parcial; não mascarar indisponibilidade como resultado vazio.