# Runbook — buscar clientes de forma repetível

**Objetivo:** transformar "quem pode comprar" numa execução mensal de um comando, com o mesmo recorte de mercado, comparável entre meses.
**Escala:** a base oficial tem ~70 milhões de estabelecimentos; a forma saudável de consumi-la está em [JARVIS_PROSPECTO_DATA_PIPELINE.md](JARVIS_PROSPECTO_DATA_PIPELINE.md).
**Custo:** R$ 0 em dados (dados abertos da Receita, CC-BY).
**Estado:** descoberta + qualificação + CSV + manifesto testados com fixtures; em 17/11/2026 foi executado um recorte real parcial de 67.252 linhas. Isso não equivale a uma varredura nacional.

## 1. O que é uma campanha

Um arquivo JSON em `config/prospecting/campaigns/` que congela duas coisas:

- **`query`** — o recorte de mercado: UF, municípios, prefixos de CNAE, só empresas ativas, limite.
- **`icp`** — o perfil de comprador: cidades/estados, setores, pesos por critério e o `fit_threshold`.

Campanhas são versionadas no Git: mudar o ICP é um diff revisável, não uma preferência escondida numa sessão de chat.

Campanha inicial da operação própria: `config/prospecting/campaigns/jarvis-prospecto-grande-florianopolis.json`.

## 2. Baixar a base

1. Baixe a competência do mês em [Dados Abertos do CNPJ](https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/cadastros/cnpj) (~7,8 GB compactados, ~37 arquivos).
2. Extraia e renomeie o que a campanha usa para nomes estáveis:

| Arquivo oficial | Nome esperado |
|---|---|
| `K3241.K03200Y*.ESTABELE` | `Estabelecimentos0.csv` |
| `K3241.K03200Y*.EMPRECSV` | `Empresas0.csv` |
| `F.K03200$Z.D*.MUNICCSV` | `Municipios.csv` |
| `F.K03200$Z.D*.CNAECSV` | `Cnaes.csv` |

3. Guarde a competência no nome da pasta (`/dados/receita/2026-11/`). O adaptador valida presença dos arquivos e falha alto se faltar um.

## 3. Rodar

Para uso recorrente, carregue a base uma vez num store colunar (DuckDB) e consulte o store — metodologia, medições e limites em [JARVIS_PROSPECTO_DATA_PIPELINE.md](JARVIS_PROSPECTO_DATA_PIPELINE.md):

```bash
python scripts/prospecto_ingest.py --data-dir /dados/receita/2026-11 --db /dados/receita/prospecto-2026-11.duckdb --uf SC
python scripts/prospecto_run.py \
  --campaign config/prospecting/campaigns/jarvis-prospecto-grande-florianopolis.json \
  --store /dados/receita/prospecto-2026-11.duckdb \
  --out artifacts/prospecto
```

Para escolher o recorte na hora, sem editar JSON, use o catálogo de filtros:

```bash
python scripts/prospecto_run.py --list-presets
python scripts/prospecto_run.py \
  --campaign config/prospecting/campaigns/jarvis-prospecto-grande-florianopolis.json \
  --store /dados/receita/prospecto-2026-11.duckdb \
  --preset metalmecanica-sc \
  --out artifacts/prospecto
```

`limit` é o tamanho da página; a execução percorre todas as páginas até esgotar o filtro. `--max-companies` existe como teto de segurança e, quando corta, o manifesto marca `truncated`.

Para incluir leads que não estão no cadastro (indicação, site, inbound), aponte o CSV:

```bash
python scripts/prospecto_run.py --campaign ... --store ... \
  --external-leads leads/indicacoes.csv \
  --external-source-url https://exemplo.com/indicacoes \
  --out artifacts/prospecto
```

Colunas: `empresa` (obrigatória), `cnpj`, `cidade`, `uf`, `setor`, `site`, `fonte`, `fonte_url`. A entrega traz `cadastro_receita` com `encontrado`, `nao encontrado` ou `nao verificado` — leia essa coluna antes de prometer cobertura.

Sem store, a varredura direta nos CSVs continua válida para uma execução isolada:

```bash
python scripts/prospecto_run.py \
  --campaign config/prospecting/campaigns/jarvis-prospecto-grande-florianopolis.json \
  --data-dir /dados/receita/2026-11 \
  --out artifacts/prospecto
```

Ajustes úteis: `--limit 50` (amostra rápida), `--include-unqualified` (ver também quem ficou fora do ICP), `--now 2026-11-17T00:00:00+00:00` (execução reproduzível), `--establishments`/`--companies`/`--municipalities`/`--cnaes` (caminhos fora do padrão).

## 4. Ler a saída

Dois arquivos, com carimbo de tempo e sem sobrescrever execução anterior:

- `<campanha>-<AAAAmmddTHHMMSSZ>.csv` — o banco entregue ao cliente.
- `<campanha>-<AAAAmmddTHHMMSSZ>.json` — o manifesto da execução.

Manifesto responde "o que exatamente rodou": `query`, `profile_id`, `source_id`, `generated_at`, `scanned_rows`, `matched_rows`, `discovered_companies`, `delivered_rows`, `excluded_not_fit`, `needs_verification`, `truncated` e as notas da fonte. É a peça que torna a busca auditável e repetível.

Colunas do CSV: `empresa`, `cnpj`, `cidade`, `uf`, `setor`, `segmento`, `site`, `score_fit`, `intencao`, `confianca`, `classificacao`, `verificar`, critérios atendidos/não atendidos/sem dado e `fontes`.

A terceira peça é o histórico: `<out>/history/<campanha>-<stamp>.json`, com as empresas daquela entrega, usado para o diff do mês seguinte.

- `classificacao=outbound` — aderente ao ICP, sem sinal explícito de intenção: lista fria.
- `classificacao=priority` — aderente e com sinal explícito datado.
- `verificar=sim` — algum critério ficou sem dado (por exemplo porte) ou a confiança das evidências está abaixo do mínimo.

## 5. Repetir todo mês

1. Baixe a nova competência.
2. Rode a **mesma** campanha apontando para a nova pasta.
3. Leia o diff que o comando imprime: `entraram`, `sairam`, `mudaram` e `permaneceram`, com nome e CNPJ de cada empresa.
4. Compare também os manifestos: `discovered_companies`, `truncated` e `needs_verification`.

### Como o histórico funciona

Cada execução grava um snapshot das empresas efetivamente entregues em `<out>/history/<campanha>-<stamp>.json` (uma empresa por CNPJ; sem CNPJ, nome normalizado + cidade). No mês seguinte, o comando carrega o snapshot mais recente **pela data de referência gravada no arquivo**, não pela ordem do nome, calcula o diff e só então grava o novo. A mesma data de referência não pode ser gravada duas vezes: o comando falha em vez de sobrescrever histórico.

O diff responde o que os contadores não respondem: uma empresa que saiu do CSV fechou, mudou de atividade ou caiu fora do novo recorte — e é isso que precisa ser olhado antes de repetir a abordagem.

A seção `mudaram` (`~`) cobre quem continua na entrega mas piorou ou melhorou: queda de score por mudança de CNAE, ou passagem de `outbound` para `priority` quando aparece um sinal explícito. A transição vem escrita (`fit 100 -> 60, outbound -> not_fit`), sem exigir que se abra dois arquivos para descobrir o que aconteceu. Empresas que caem de tier e saem da entrega aparecem como `sairam` no modo padrão; para vê-las como `mudaram`, rode com `--include-unqualified`.

Use `--history <dir>` para guardar os snapshots fora da pasta de saída ou `--no-history` para uma execução exploratória.

Se `truncated=true`, o limite da consulta cortou a lista: aumente `limit` ou estreite CNAEs/municípios.

## 5b. Primeira execução real (17/11/2026, competência 2026-11)

Recorte: divisão 1 dos estabelecimentos (67.252 linhas, ~1% da divisão, que é ~10% da base nacional) + `Empresas1`, `Municipios`, `Cnaes` oficiais.

| Medida | Resultado |
|---|---|
| Estabelecimentos lidos | 67.252 |
| Ativos no recorte | 9.882 (14,7%) |
| Nas 4 cidades, qualquer CNAE | 428 |
| Nas 4 cidades com CNAE do recorte | 49 |
| Casados pelo adaptador (ativos) | 12 |
| Empresas úteis | 10 |
| Entregues no CSV | 7 |
| Fora do ICP | 3 (CNAE 461x — representantes comerciais não casam com os alvos de setor) |

Conclusões que mudaram a campanha:

- **Só 14,7% dos registros estão ativos.** `only_active` não é opcional; sem ele a lista seria majoritariamente de empresas baixadas.
- **O volume é estrutural, não pontual.** 12/67.252 = 0,018% da base. Extrapolando 70 milhões de estabelecimentos, o recorte atual tem ordem de **12 mil empresas ativas** — muito acima do limite. Logo o CSV é sempre uma amostra, e a amostra segue a ordem do arquivo (CNPJ base ascendente), não uma prioridade comercial. Por isso o limite da campanha caiu de 300 para 100 nesta rodada, e o manifesto avisa quando truncou.
- **A base oficial tem nomes mascarados.** 52 empresas do split trazem razão social composta só por `*`. O adaptador passou a descartar nome sem nenhuma letra e a contá-lo como linha descartada, em vez de entregar `********` como prospect.
- **O `fit_threshold` de 70 está filtrando corretamente:** empresas de representantes comerciais (461x) ficam em 60 e saem do CSV por padrão.

O próximo ajuste estrutural é particionar o recorte (uma cidade ou um segmento por campanha) ou trocar o corte por amostragem determinística — aumentar `limit` só aumenta o viés.

## 6. Ajustar o ICP

- `weights`: distribua o que realmente distingue o comprador. Critério configurado sem peso é rejeitado na carga.
- `fit_threshold`: com `industry=0.4` e `territory=0.6`, o limite 70 exige que o setor também case; 60 aceitaria quem está só na região.
- `minimum_confidence`: abaixo disso o prospect sai com `verificar=sim`.
- A base oficial não publica número de funcionários: `employee_count` fica ausente e o critério de porte fica `unknown` — não preencha por estimativa.

## 7. Hipóteses da campanha inicial (nosso ICP)

O arquivo marca explicitamente que o recorte é hipótese: atacado, construção/obras, metalmecânica, máquinas e manutenção na Grande Florianópolis. Nada disso foi validado por resultado comercial.

Critério de invalidação sugerido: se depois de 20 abordagens humanas menos de ~10% responderem, o problema pode ser o recorte (CNAE) ou a oferta — rever a campanha antes de aumentar volume.

## 8. Limites e proibições

- Varredura em Python puro sobre dezenas de milhões de linhas: serve para carga mensal, não para consulta interativa. Para consulta repetida, materialize os CSVs em DuckDB/PostgreSQL.
- O adaptador **não lê telefone nem e-mail**. A entrega é a lista de empresas com CNPJ e fonte oficial; contato exige decisão de finalidade, retenção e opt-out.
- Google Places não pode ser usado como base (os termos proíbem armazenar nome/endereço); ver [JARVIS_PROSPECTO_SOURCES.md](JARVIS_PROSPECTO_SOURCES.md).
- O `tenant_id` da campanha é rótulo local de operador. Uma API futura deve resolver o tenant por membership autenticada, nunca por este arquivo.
- Nada é enviado automaticamente: `DO_NOT_CONTACT` é terminal e o envio continua humano.


## 9. Uso interno pelo Jarvis

O mesmo store DuckDB usado pelo CLI pode ser lido pelo Android MCP e pela janela Prospecto do HUD Global Desktop. O adaptador não cria nem baixa a base automaticamente: ele abre o arquivo configurado em modo de leitura.

Configure `JARVIS_PROSPECTO_STORE_PATH` no processo Android MCP ou no servidor local do HUD Desktop. Se não for definido, o adaptador procura `data/prospecting/cnpj.duckdb` na raiz do repositório.

Exemplos de configuração (substitua o caminho pelo local real do arquivo):

**Windows PowerShell**
```powershell
$env:JARVIS_PROSPECTO_STORE_PATH = "D:\JarvisData\prospecting\cnpj.duckdb"
```

**Termux**
```bash
export JARVIS_PROSPECTO_STORE_PATH="$HOME/.local/share/jarvis/prospecting/cnpj.duckdb"
```

A janela **Prospecto** no HUD Global chama o endpoint local autenticado `/api/prospecting/search`; a pesquisa não é executada no navegador nem abre uma conexão DuckDB no frontend. O endpoint usa o mesmo adaptador Nexus. A rota de lookup `/api/prospecting/lookup` também é local e autenticada.

As ferramentas MCP disponíveis são registradas somente no Android MCP e passam pelo Tool Dispatcher. Para autorizá-las, crie/pareie uma sessão com o perfil `termux_jarvis`. Sessões existentes não recebem novas capabilities automaticamente; se a sessão atual foi criada antes desta alteração, será necessário revogá-la e parear novamente com esse perfil. Não revogue uma sessão ativa sem confirmar que não há outra operação dependente dela.

Exemplo para criar o novo perfil, depois de revogar a sessão anterior pelo fluxo normal:

```bash
PYTHONPATH="$PWD" python -m app.adapters.infrastructure.session_authorization create --profile termux_jarvis
```

As ferramentas MCP disponíveis são:

- `prospecting.companies.search`: recebe `uf`, `cnae_prefixes`, opcionalmente `municipalities`, `only_active`, `include_secondary_cnae`, `limit` (1–100) e `after_cnpj_basico`.
- `prospecting.companies.lookup`: consulta um CNPJ completo de 14 dígitos e identifica um estabelecimento exato.

Exemplo de pesquisa:

```json
{
  "uf": "SC",
  "municipalities": ["São José", "Florianópolis"],
  "cnae_prefixes": ["4120", "2511"],
  "only_active": true,
  "include_secondary_cnae": true,
  "limit": 50
}
```

A busca por segmento retorna um resultado por raiz CNPJ (8 dígitos), com um CNPJ completo representativo. Para investigar uma filial específica, use a consulta exata por CNPJ. Quando `truncated=true`, continue com o valor de `next_cursor` em `after_cnpj_basico`.

O arquivo DuckDB é local ao host: configurar o caminho no Android não disponibiliza automaticamente o arquivo do Desktop, e vice-versa. O Android MCP aplica o perfil de sessão e o Tool Dispatcher; o HUD Desktop aplica o token local e o guardião de rede privada. A distribuição/host definitivo da base precisa ser escolhido separadamente. O banco está coberto pelo `.gitignore`; não o envie ao Git.

Essas ferramentas apenas pesquisam dados públicos e devolvem proveniência. Não coletam telefone/e-mail e não enviam mensagens ou contatos.
