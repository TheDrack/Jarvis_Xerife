# Diagnóstico de recursos do host

O servidor Desktop MCP expõe `host_resource_diagnostics(process_limit=25)` como consulta somente leitura. A ferramenta coleta identidade do host, CPU, RAM, swap/pagefile, volumes montados e inventário limitado de processos.

## Campos

- `resources.memory_total_bytes`, `memory_available_bytes`, `memory_used_bytes` e `memory_percent`: estado da memória física segundo psutil.
- `resources.swap`: total, usado, livre e percentual de swap. No Windows, o psutil apresenta métricas de memória de paginação/pagefile; isso não substitui a leitura da configuração de tamanho máximo do pagefile.
- `resources.disks[]`: capacidade e espaço livre por ponto de montagem.
- `top_cpu_processes[]`: processos ordenados por CPU reportada pelo psutil.
- `top_memory_processes[]`: processos ordenados por RSS (resident set size/working set), independentemente do ranking de CPU.
- `top_processes[]`: alias de compatibilidade para `top_cpu_processes[]`.

O limite de processos é inteiro entre 1 e 50. O adaptador psutil percorre o inventário de processos e mantém somente os N maiores de cada ranking, evitando materializar e ordenar a tabela completa.

## Interpretação

1. RAM alta com swap baixo pode indicar pressão física ainda sem paginação intensa.
2. RAM alta e swap/pagefile usado crescente sugere pressão sustentada e atividade de paginação; compare snapshots em momentos distintos.
3. Use `top_memory_processes` para localizar consumidores de RAM. CPU alta não significa necessariamente consumo alto de memória.
4. Verifique espaço livre por volume antes de qualquer limpeza. Espaço em disco e memória RAM são recursos diferentes; não conclua que um causa o outro sem evidência.
5. RSS/working set inclui páginas residentes atribuídas ao processo e pode incluir memória compartilhada; não é uma medida exata de memória privada exclusiva.

## Privacidade e limites

A coleta não lê linhas de comando, variáveis de ambiente, credenciais, conteúdo de arquivos, histórico de navegação ou payloads de processos. A ferramenta não encerra processos, não altera pagefile, não apaga arquivos e não muda configurações do sistema.

A telemetria é um snapshot. Para encontrar vazamentos ou crescimento contínuo, compare snapshots ao longo do tempo. A coleta remota só estará disponível depois de atualizar e reiniciar o servidor MCP no host e restabelecer o transporte.
