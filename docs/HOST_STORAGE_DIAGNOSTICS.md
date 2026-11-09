# Inventário limitado de armazenamento do host

O Desktop MCP expõe \`host_storage_diagnostics()\` como consulta somente leitura para investigar volumes com pouco espaço.

## Escopo e limites

- Examina apenas a raiz da unidade de sistema detectada por \`SystemDrive\`; não aceita caminhos arbitrários do chamador.
- Limites padrão: profundidade 5, até 20.000 entradas e 8 segundos.
- Retorna até 30 diretórios, arquivos e extensões com maior tamanho.
- Destaca diretórios cujos nomes indicam temporários, caches ou logs.
- Ignora diretórios protegidos do Windows e não segue symlinks nem junctions/reparse points.
- Registra erros de acesso como entradas ignoradas; uma varredura interrompida por tempo ou quantidade é marcada como truncada.

## Privacidade e segurança

A ferramenta usa somente metadados de filesystem (caminho, tipo, extensão e tamanho). Não abre arquivos, não lê conteúdo, não calcula hashes, não altera atributos e não remove/move nada. O caminho da unidade é derivado do ambiente do processo MCP, não de entrada do usuário.

A varredura é best-effort e limitada: os tamanhos são estimativas dos arquivos alcançados dentro dos limites, não substituem uma análise offline completa do volume. Junctions, diretórios protegidos, arquivos inacessíveis e conteúdo além da profundidade/tempo configurados não entram nos totais.

## Ferramenta Shell

A projeção de \`Get-PSDrive\` retorna \`Provider.Name\` como texto simples em vez de serializar o objeto Provider completo, evitando payloads desnecessariamente grandes.


## Fallback pelo diagnóstico de recursos

Quando o gateway MCP expuser `host_resource_diagnostics` mas não conceder a ferramenta
dedicada `host_storage_diagnostics`, use:

```json
{"process_limit": 20, "include_storage_inventory": true}
```

O parâmetro é opt-in e aditivo: chamadas existentes mantêm o comportamento e o payload
anteriores. O inventário reutiliza os mesmos limites de profundidade, quantidade de
entradas e tempo; continua restrito à unidade de sistema e somente leitura.
