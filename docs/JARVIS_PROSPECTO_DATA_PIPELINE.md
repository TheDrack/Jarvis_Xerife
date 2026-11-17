# Jarvis Prospecto — como consumir a base inteira sem sofrer

**Pergunta:** como varrer ~30 GB de CSV por mês (~70 milhões de estabelecimentos) de forma saudável, filtrando e organizando os dados?
**Resposta implementada:** carregar uma vez por competência, por arquivo e por escopo de UF, num store colunar (DuckDB) — e consultar o store, nunca o CSV bruto.

## 1. Diagnóstico antes de escolher ferramenta

| Fato medido | Número |
|---|---|
| Competência 2026-11 completa | 37 arquivos, ~7,8 GB compactados |
| Estabelecimentos | ~70 milhões de linhas, ~30 GB de CSV descompactado |
| Divisão 0 isolada | 2,28 GB compactados (bem maior que as outras) |
| Linhas por segundo em Python puro (varredura simples) | ~65 mil/s neste ambiente |
| Banda do sandbox até a Receita | ~240 KB/s |
| Servidor da Receita | **sem `Accept-Ranges`** — retomada com `curl -C -` corrompe o arquivo |

Conclusões práticas: baixar e varrer tudo a cada campanha é inviável; retomada de download não funciona; é preciso materializar uma vez e consultar muitas.

## 2. Metodologia

1. **Filtrar durante a leitura, não depois.** O recorte é por UF (`--uf SC`) e a carga só grava o que está no escopo. Prospecção de quatro municípios não precisa de base nacional.
2. **Processar por blocos no nível do arquivo.** Cada CSV da Receita é uma unidade de trabalho: ao terminar, entra em `ingest_log`; reiniciar a carga pula o que já foi carregado. Dentro do arquivo, quem faz o bloco é o motor (vetorizado, com `memory_limit` e derramamento em disco), não um laço Python.
3. **Memória limitada e explícita.** `SET memory_limit='2GB'`, `threads=4`, `preserve_insertion_order=false`. Sem isso, um join grande vira swap do sistema.
4. **Materializar em colunar.** DuckDB grava um único arquivo, sem servidor, e responde filtro+join em milissegundos sobre milhões de linhas. Parquet é a alternativa para arquivo morto: ~5× menor que CSV e leitura bem mais rápida em consultas repetidas.
5. **Organizar com as tabelas de domínio.** `municipalities` e `cnaes` entram no store para traduzir códigos; sem elas o dado é ilegível (município é código, não nome).
6. **Uma competência por arquivo de store.** `prospecto-2026-11.duckdb`, `prospecto-2026-12.duckdb`. O diff mensal compara snapshots de campanha, não pedaços do store.

### Por que DuckDB e não SQLite ou Postgres

- **SQLite** é OLTP, orientado a linha: bom para ponto-a-ponto, caro para inserir e varrer milhões de linhas. Em benchmark público de 1 milhão de linhas, inserção linha a linha custou ~4,4 s e a agregação ~0,63 s, contra milissegundos do DuckDB em memória — diferença de duas ordens de grandeza para o nosso padrão de acesso.
- **Postgres** resolve, mas exige servidor, backup, tuning e conexão; para um job mensal de um operador, é infraestrutura sem retorno.
- **DuckDB** roda no processo, lê CSV direto (sem etapa de importação obrigatória), usa leitura colunar com poda por zona e derrama em disco sob limite de memória — exatamente o perfil de "varrer muito, usar poucas colunas".

Fonte de referência: documentação de performance do DuckDB e comparações públicas CSV×Parquet (leitura completa de 15,95 GB de CSV em ~11,8 s; Parquet ~5× menor).

## 3. Implementação

`app/adapters/infrastructure/prospecting/cnpj_store.py`:

- `CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)` — carrega estabelecimentos do escopo, resolve empresas por semi-join (`cnpj_basico IN (SELECT ... FROM establishments)`) em vez de carregar 70 milhões de empresas, e recarrega `municipalities`/`cnaes`.
- `CnpjStoreProvider(database)` — implementa o mesmo contrato `DiscoveryProvider` do adaptador CSV: mesma query, mesmo resultado, mesmas notas de fonte. Teste de paridade garante que os dois caminhos entregam os mesmos CNPJs.
- **CNAE principal e secundário.** `include_secondary_cnae` (ligado por padrão) casa também a lista de atividades secundárias do estabelecimento, porque empresa do segmento frequentemente se registra em atividade vizinha. Sem isso o filtro esconde prospect real.
- **Varredura completa por páginas.** `DiscoveryResult.next_cursor` devolve a próxima raiz de CNPJ; `run_campaign` percorre as páginas até esgotar o filtro. `limit` virou tamanho de página; `max_companies` é o teto opcional, e quando ele corta, o manifesto marca `truncated`.
- **Catálogo de filtros.** `config/prospecting/filters.json` guarda recortes nomeados (construção, atacado, metalmecânica, serviços para obras, todos os setores) que o operador escolhe na hora com `--preset`, sem editar JSON.
- Nome mascarado (`********`) e CNPJ inválido continuam sendo descartados, iguais ao caminho CSV.
- Layout tolerante: o arquivo atual tem **30 colunas** (o layout documentado lista 29). O leitor de CSV usa só até a coluna de município, então a coluna extra não desloca nada; o store nomeia as colunas próprias dinamicamente.

CLIs:

```bash
# uma vez por mês, por estado que você prospecta
python scripts/prospecto_ingest.py \
  --data-dir /dados/receita/2026-11 \
  --db /dados/receita/prospecto-2026-11.duckdb \
  --uf SC

# toda campanha, agora em segundos
python scripts/prospecto_run.py \
  --campaign config/prospecting/campaigns/jarvis-prospecto-grande-florianopolis.json \
  --store /dados/receita/prospecto-2026-11.duckdb \
  --out artifacts/prospecto
```

## 4. Medições neste ambiente (dados reais da competência 2026-11)

| Cenário | Linhas lidas | Tempo de carga | Store | Tempo da campanha | Entregues |
|---|---|---|---|---|---|
| Recorte de 67.252 linhas + `Empresas1` real (4,49 M linhas) | 67.252 | 3 s | 1,8 MB | 0 s | 7 |
| Recorte de 263.961 linhas + `Empresas1` | 263.961 | 3 s | 2,8 MB | 0 s | 21 |
| Mesmo recorte de 67.252, caminho CSV puro | 67.252 | — | — | 4 s | 7 (idênticos) |

A carga de 264 mil linhas ficou em ~88 mil linhas/s, incluindo a leitura do arquivo de empresas.

**Extrapolação (não medição):** a 88 mil linhas/s, 70 milhões de estabelecimentos levam da ordem de **13 minutos** num único processo, com 4 threads e 2 GB de limite. Para SC (~4,7% da base), o store fica na ordem de 3,3 milhões de linhas — algumas centenas de MB. A carga real de uma competência completa ainda **não foi executada aqui**: o download parou em 102 de 326 MB de uma divisão, por banda e ausência de retomada.

## 5. Cobertura: quem pode ser cliente e não está na base

A Receita é registro de pessoa jurídica, não de comprador. Lacunas reais, em ordem de impacto:

1. **Sem CNPJ (informal)** — autônomo, equipe de obra não formalizada, profissional liberal pessoa física. Invisível por definição; exige outro canal.
2. **CNPJ baixado ou inapto** — na medição do recorte, só ~14,7% das linhas estavam ativas. Quem encerrou o CNPJ e segue operando fica fora de `only_active`.
3. **Sede em outra cidade/estado** — filtramos município do estabelecimento e UF; quem atende a região sem estar sediado nela não aparece.
4. **CNAE divergente** — mitigado pelo casamento de CNAE secundário, mas quem está registrado em atividade fora do conjunto de prefixos continua invisível.
5. **Registro recente ou dado incompleto** — competência mensal; razão social mascarada (`***`), fantasia vazia, sem decisor e sem intenção de compra.

Consequência de desenho: a base é a fonte **primária**, não a única. Cada empresa carrega a evidência da fonte que a produziu, e "não está no cadastro" é um estado explícito que pede busca web, indicação ou inbound — nunca silêncio.

### Como o segundo canal entra na operação

`ExternalLeadsAdapter` lê um CSV local (`empresa;cnpj;cidade;uf;setor;site;fonte;fonte_url`, só `empresa` obrigatório) com os leads que a Receita não tem. `CompositeDiscoveryProvider` entrega primeiro o resultado do cadastro, pagina o cadastro até esgotar e só então anexa os leads externos, deduplicando por CNPJ ou nome.

Cada lead externo com CNPJ é conferido no store (`lookup_company`) **fora do filtro da campanha**: existir no cadastro e caber no filtro são coisas diferentes. O resultado vai para a coluna `cadastro_receita` da entrega:

| Valor | Significado |
|---|---|
| `encontrado` | empresa no extrato da Receita (fonte primária) |
| `nao encontrado` | lead externo com CNPJ que o extrato não contém |
| `nao verificado` | lead sem CNPJ, ou conferência indisponível |


Exemplo:

```bash
python scripts/prospecto_run.py --campaign ... --store ... \
  --external-leads leads/indicacoes.csv \
  --external-source-url https://exemplo.com/indicacoes \
  --out artifacts/prospecto
```

Os leads externos **não** são filtrados por CNAE (o arquivo não tem código de atividade) — o adapter registra isso nas notas do manifesto, e o operador responde pelo critério de setor desses registros.

## 6. Operação mensal recomendada

1. Baixar a competência (sem retomada; se cair, baixar de novo e validar com `unzip -t`).
2. `prospecto_ingest.py` para o store da competência. Se interromper, rodar de novo: arquivos já carregados são ignorados.
3. `prospecto_run.py --store ...` para cada campanha; comparar o CSV e o manifesto com o mês anterior.
4. Opcional: exportar a tabela de estabelecimentos em Parquet (`COPY ... TO 'x.parquet' (FORMAT PARQUET)`) para arquivo histórico compacto.

## 7. Limites conhecidos

- `duckdb` passa a ser dependência do projeto (adicionada em `requirements.txt`).
- As medições da seção 4 foram feitas **antes** da paginação completa e do CNAE secundário: os tempos seguem válidos, a contagem de empresas entregues tende a crescer e deve ser remedida na próxima execução real.
- O store é escopado por UF: consultar outro estado exige nova carga daquele estado.
- A carga nacional completa não foi medida; os tempos acima são medições parciais + extrapolação declarada.
- O store não guarda contato (telefone/e-mail das colunas 22–28 são ignorados), mantendo a decisão de privacidade do domínio.
- Não há ingestão incremental por delta entre competências: cada mês é um store novo, comparado via snapshot de campanha.
