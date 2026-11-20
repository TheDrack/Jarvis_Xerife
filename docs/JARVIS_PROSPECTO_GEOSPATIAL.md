# Jarvis Prospecto — Camada geoespacial

## Objetivo

Associar endereços de estabelecimentos a coordenadas geográficas com CRS explícito para consultas de proximidade e futura visualização em mapa. A geocodificação é uma observação separada do cadastro empresarial: não altera o dado original da Receita Federal e mantém sua própria precisão, confiança, provedor e data.

## O que está implementado nesta etapa

- ProspectCompany passa a carregar tipo de logradouro, logradouro, número, complemento, bairro, CEP, município, UF e país.
- geocoding_address monta o melhor endereço disponível e retorna None quando não existe dado de localização suficiente.
- Os adaptadores CSV e DuckDB da Receita Federal extraem os componentes de endereço das colunas oficiais do estabelecimento.
- GeoCoordinate valida latitude/longitude e registra o CRS de cada observação (EPSG:4326 por padrão; GeocodeBR retorna SIRGAS 2000 / EPSG:4674).
- AddressGeocoding exige coordenadas e precisão para resultados success/partial, e não permite que failed ou pending afirmem coordenadas. Guarda também o endereço formatado retornado pelo provedor.
- Precisões distinguem rooftop, premise, street, interpolated, postal_code, locality, region e unknown.
- GeoRadiusQuery e distance_km fornecem a base para consultas por raio usando Haversine.
- GeocodingService reutiliza resultados success/partial, aceita force=True para atualização explícita e rejeita resposta de outro endereço; falhas não são cacheadas para não perpetuar indisponibilidade temporária.
- DuckDBGeocodingRepository persiste o cache em arquivo próprio, inicializa o schema uma vez por instância e isola escritas do banco analítico CNPJ.

## Persistência e identidade

A chave do cache é SHA-256 do endereço normalizado por Unicode NFKC, casefold e espaços. Pontuação e componentes não são descartados, para evitar unir endereços distintos por heurística agressiva.

A chave identifica o endereço pesquisado, não a empresa. Estabelecimentos diferentes no mesmo endereço podem compartilhar a mesma geocodificação. A associação com cada prospect deve ser feita pelo endereço/fingerprint, mantendo os registros empresariais independentes. A origem cadastral do endereço continua na ProspectEvidence do prospect; o cache não guarda um CNPJ único como dono da coordenada.

## Precisão e qualidade

- rooftop / premise: localização de edifício/unidade, conforme a evidência fornecida pelo geocodificador.
- street / interpolated: localização aproximada ao longo da via.
- postal_code / locality / region: centroide ou referência de área; não é endereço exato.
- unknown: o provedor não informou precisão suficiente.

Não converter CEP ou município diretamente em coordenada e rotular como endereço exato. Confiança é opcional: se o provedor não oferecer um score calibrado, o campo permanece nulo em vez de inventarmos um valor. A interface futura deverá distinguir visualmente precisão e confiança e permitir filtrar/excluir resultados aproximados.

## Provedor local selecionado: Ipea geocodebr / CNEFE

O adapter `GeocodeBrGeocoder` integra a versão Python opcional do projeto Ipea `geocodebr`, baseada no CNEFE publicado pelo IBGE. O pacote usa DuckDB no processamento, aceita tabelas Polars e retorna `pyarrow.Table`; não faz uma chamada HTTP por endereço. A primeira execução baixa os arquivos de referência necessários para o cache local. Documentação: https://pypi.org/project/geocodebr/.

Instalação opcional em Python 3.10 ou superior:

```bash
python -m pip install -e ".[geocodebr]"
```

O extra não é instalado por padrão. O import do provedor é tardio, portanto o runtime principal não instala o pacote nem baixa a base CNEFE ao iniciar. O adapter recebe registros `ProspectCompany` estruturados, exige município e UF (campos obrigatórios do geocodebr), envia um lote e preserva a associação por identificador de linha. Guarda precisão, desvio estimado, endereço encontrado, origem `geocodebr:cnefe` e CRS `EPSG:4674`. O resultado Python é um `pyarrow.Table`; a integração consome `to_pylist()` e não depende de `pandas`.

Mapeamento de precisão: `numero` → `premise`; `numero_aproximado` → `interpolated`; `logradouro` → `street`; `cep` → `postal_code`; `localidade` → `locality`; `municipio` → `region`. Só `numero` é classificado como sucesso; os demais níveis são parciais. A estimativa `desvio_metros` é mantida como `accuracy_m`, sem ser tratada como score probabilístico.

## Execução integrada à campanha

A campanha CLI agora aceita geocodificação opcional:

```bash
python scripts/prospecto_run.py \
  --campaign config/prospecting/campaigns/jarvis-prospecto-grande-florianopolis.json \
  --store /caminho/cnpj.duckdb \
  --out artifacts/prospecto \
  --geocode
```

- Sem `--geocode`, o comportamento permanece offline e não importa/inicializa o provedor.
- Com `--geocode`, apenas empresas que serão entregues no CSV são enviadas ao serviço; empresas fora do ICP ficam de fora, salvo quando `--include-unqualified` é usado.
- Registros sem endereço, município ou UF não são enviados ao provedor e entram no contador de ignorados.
- O cache DuckDB fica por padrão em `~/.local/share/jarvis/prospecto/geocoding.duckdb`. Use `--geocoding-db` para alterar o caminho.
- A primeira execução pode baixar tabelas CNEFE necessárias para o tipo de endereço consultado. O cache de dados do pacote é separado do cache de resultados do Jarvis.
- O CSV contém latitude, longitude, precisão, desvio estimado, CRS, endereço encontrado, status e provedor. O manifesto registra totais de tentativas, resultados precisos/parciais/falhos e empresas ignoradas.
- Coordenadas de precisão `postal_code`, `locality` ou `region` continuam identificadas como parciais; não devem ser exibidas como pontos exatos de estabelecimento.

A integração cobre o CLI e o arquivo CSV/manifesto. O MCP de busca e a interface de mapa ainda não estão conectados. A geração real de coordenadas depende da instalação do extra e da disponibilidade dos dados CNEFE locais.

O Nominatim público do OpenStreetMap não deve ser usado como serviço de geocodificação em massa do Prospecto: sua política limita a no máximo uma requisição por segundo e restringe tarefas em lote/recorrentes. Consulte a política oficial: https://operations.osmfoundation.org/policies/nominatim/.

## Próximas etapas

1. Selecionar provedor compatível com o volume e o modelo comercial (API contratada ou instância própria).
2. Implementar adapter com timeout, rate limit, retries controlados, normalização e mapeamento explícito de precisão.
3. Criar job de geocodificação em lote, com checkpoints, limites por provedor, idempotência e reprocessamento de falhas.
4. Associar resultados aos prospects e expor filtros espaciais (raio, área, distância a centros logísticos).
5. Criar endpoint de mapa com clusters/camadas e atribuição/licença cartográfica visível.
6. Adicionar mapa de calor e seleção de área após validar volume e performance com dados reais.

## Estado

Esta etapa implementa contratos, cache persistente, integração opcional ao CLI de campanha e exportação das coordenadas no CSV. Ainda não oferece endpoint MCP nem interface de mapa.