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
| INPI | Sinais de inovação | Marcas, patentes e classes tecnológicas | Planejado |\n| Comex Stat / MDIC | Comércio exterior | NCM, município, país, UF, valor FOB, peso e fluxo | Pesquisa agregada |\n| FAPESC / FINEP | Fomento | Editais, elegibilidade, prazos e linhas de apoio | Pesquisa / planejado |\n| CEIS / CNEP | Compliance | Sanções e impedimentos de fornecedores | Planejado |

## ACATE: dois produtos de dados diferentes

- O diretório de associados apresenta mais de 1.500 empresas e filtros por polo e vertical. Ele é uma fonte de entidades candidatas, mas a página pública não foi identificada como API aberta com licença irrestrita de reutilização. O adaptador AcateDirectoryAdapter importa CSV fornecido pelo operador e exige reuse_permission_confirmed=True; não faz scraping.
- O Observatório ACATE é uma fonte de indicadores agregados. Na publicação consultada, SC aparece com 34,2 mil empresas de tecnologia e cerca de 102 mil colaboradores em 2025. Florianópolis aparece com 7,4 mil empresas, 44,8 mil empregos, R$ 14 bilhões de faturamento, crescimento de 9,4% e R$ 178 milhões de ISS do setor em 2025; o painel também reporta mais de R$ 787 milhões em investimentos captados por startups e empresas locais. A participação do setor no PIB municipal é 21%, com referência a 2023. São indicadores de mercado, não uma lista de empresas; cada métrica precisa preservar o seu período específico e a metodologia publicada.

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

## GAPs e hipóteses que os indicadores permitem investigar

- **Concentração de receita e porte:** o Observatório publica distribuição por faixas de faturamento; cruzar essas faixas agregadas com o porte cadastral do CNPJ para localizar segmentos de micro e pequenas empresas. Não atribuir faturamento estimado a uma empresa individual.
- **Desalinhamento entre emprego e receita:** comparar empresas/empregos/faturamento por vertical para encontrar segmentos com alta intensidade de mão de obra e menor faturamento por trabalhador.
- **Concentração geográfica:** comparar Florianópolis, São José, Blumenau, Joinville e demais polos para identificar oferta e crescimento fora da capital.
- **Especialização por vertical:** cruzar CNAEs com as verticais ACATE (AgTech, Construtech, Edtech, Energia, Fintech, Manufatura 4.0, Peopletech, Saúde, Security Tech, Smart Cities e Varejo). CNAE é proxy cadastral; a vertical exige evidência adicional.
- **Capital e inovação:** usar investimento, chamadas FAPESC/FINEP, marcas e patentes como sinais de atividade e oportunidade, sem inferir necessidade de contratação.
- **Mercado público:** cruzar especialidades de fornecedores com editais e itens PNCP, identificando oportunidades B2G por categoria e prazo.
- **Exportação/importação:** Comex Stat permite observar fluxos por NCM, município e país; serve para dimensionar cadeias e dependência externa, não para identificar o CNPJ do operador sem fonte específica.

Essas análises são hipóteses a validar, não recomendações automáticas de compra nem prova de demanda.

## O que passa a integrar o roadmap

1. **B2G**: PNCP e Compras.gov — oportunidades de venda para órgãos públicos, com itens, prazos, requisitos e contratos.
2. **C2B**: vagas reais em páginas oficiais de carreira e APIs autorizadas; nunca inferir vagas a partir do CNPJ.
3. **Startup/innovation graph**: incubadoras, aceleradoras, fundos, programas, universidades, parques tecnológicos e centros de inovação.
4. **Propriedade intelectual**: marcas e patentes como sinais de inovação e especialização tecnológica, com minimização de dados pessoais.
5. **Cadeias de fornecimento**: FIESC, ComexStat e dados de compras para mapear compradores, fornecedores e dependências setoriais.
6. **Sinais de mercado**: abertura/baixa de empresas, emprego, PIB municipal, ISS setorial, investimentos e crescimento.
7. **Enriquecimento empresarial**: sites oficiais, portfólios e catálogos de produtos/serviços, com evidência individual e revisão de termos.
8. **Dados de relacionamento**: feiras, eventos, associações e comunidades, sem presumir que presença pública equivale a consentimento para contato.

## Cobertura CNPJ implementada e lacunas remanescentes

O materializador agora preserva os sete campos do arquivo Empresas e ingere, quando fornecidos, os arquivos Simples/MEI, Naturezas, Qualificações, Países e Motivos. A busca DuckDB expõe filtros por situação, matriz/filial, bairro, CEP, abertura, porte, natureza, capital, país, motivo, situação especial, presença de telefone/e-mail/fax e opção Simples/MEI.

Lacunas remanescentes:
- O arquivo de Sócios não é ingerido nesta etapa porque contém dados pessoais; qualquer uso futuro precisa de finalidade, minimização, controle de acesso e retenção próprios.
- Campos de contato são mantidos apenas no store local para filtros de presença; os valores não são devolvidos pelo domínio/MCP.
- Filtros avançados exigem DuckDB. O adaptador de leitura direta dos CSVs falha explicitamente se receber filtros que não consegue aplicar.
- O CNPJ alfanumérico exige uma migração coordenada do parser, chave, store, lookup, schemas MCP e fixtures. A normalização atual ainda é numérica e não deve ser considerada compatível com esse novo formato.
- PNCP, Comex Stat, FAPESC/FINEP, FIESC, JUCESC, IBGE, INPI, CEIS/CNEP e páginas de carreira estão catalogados, mas ainda precisam de providers de rede/API, testes de contrato e atualização incremental.

## Regras de governança

- publicly_visible não implica durable_storage_allowed.
- durable_storage_allowed=null significa desconhecido e bloqueia persistência até revisão.
- Nenhuma fonte autoriza automaticamente outreach.
- Fonte agregada não cria leads individuais.
- Dados externos são não confiáveis; validar URL, schema, tamanho, origem e conteúdo.
- Deduplicação usa CNPJ completo/raiz quando houver; para entidades sem CNPJ, usar identificador da fonte e resolução de identidade conservadora.
- Registrar licença/termos, data de coleta, data de referência, atualização, cobertura e limitações.
- Falha de fonte deve aparecer como parcial; não mascarar indisponibilidade como resultado vazio.