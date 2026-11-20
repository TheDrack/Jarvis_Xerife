# Jarvis Prospecto — Camada geoespacial

## Objetivo

Associar endereços de estabelecimentos a coordenadas WGS84 para consultas de proximidade e futura visualização em mapa. A geocodificação é uma observação separada do cadastro empresarial: não altera o dado original da Receita Federal e mantém sua própria precisão, confiança, provedor e data.

## O que está implementado nesta etapa

- ProspectCompany passa a carregar tipo de logradouro, logradouro, número, complemento, bairro, CEP, município, UF e país.
- geocoding_address monta o melhor endereço disponível e retorna None quando não existe dado de localização suficiente.
- Os adaptadores CSV e DuckDB da Receita Federal extraem os componentes de endereço das colunas oficiais do estabelecimento.
- GeoCoordinate valida latitude/longitude WGS84.
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

## Provedor externo

Nenhum provedor externo está selecionado ou conectado nesta PR. A porta Geocoder permite integrar provedores comerciais ou instâncias próprias sem acoplar o domínio.

O Nominatim público do OpenStreetMap não deve ser usado como serviço de geocodificação em massa do Prospecto: sua política limita a no máximo uma requisição por segundo, restringe tarefas em lote/recorrentes e orienta serviços comerciais cuja função principal é geocodificação a operar sua própria instância. Consulte a política oficial: https://operations.osmfoundation.org/policies/nominatim/. A escolha do provedor precisa considerar volume, licença, cache, SLA, custo e possibilidade de troca.

## Próximas etapas

1. Selecionar provedor compatível com o volume e o modelo comercial (API contratada ou instância própria).
2. Implementar adapter com timeout, rate limit, retries controlados, normalização e mapeamento explícito de precisão.
3. Criar job de geocodificação em lote, com checkpoints, limites por provedor, idempotência e reprocessamento de falhas.
4. Associar resultados aos prospects e expor filtros espaciais (raio, área, distância a centros logísticos).
5. Criar endpoint de mapa com clusters/camadas e atribuição/licença cartográfica visível.
6. Adicionar mapa de calor e seleção de área após validar volume e performance com dados reais.

## Estado

Esta etapa implementa contratos, cache persistente, distância geográfica e extração de endereço. Ela ainda não produz coordenadas reais sem um Geocoder conectado, nem oferece endpoint ou interface de mapa.