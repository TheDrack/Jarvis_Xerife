# Harness Jarvis no Freebuff Desktop

Runbook para registrar o harness Jarvis (skills portáteis + servidor MCP) no Freebuff Desktop
neste checkout. Vale para o clone atual; cada checkout/máquina roda o próprio instalador.

## 1. Onde o Freebuff procura (base de descoberta)

Verificado em 2026-10-27 por inspeção do bundle instalado (`app.asar` do Freebuff Desktop), não por
documentação pública. Revalide após uma atualização do app.

| Recurso | Caminhos lidos | Regra |
|---|---|---|
| Skills | `{projeto}/.claude/skills/`, `{projeto}/.agents/skills/` | `.agents` tem prioridade; o diretório do usuário (`~/.claude/skills`, `~/.agents/skills`) só é lido se o host habilitar |
| Servidores MCP | `{projeto}/.agents/mcp.json`, `{projeto}/../.agents/mcp.json`, `~/.agents/mcp.json` | O último diretório tem precedência, então o projeto sobrepõe o global |
| Instruções | `AGENTS.md` do projeto | Já existe na raiz do repositório |

Detalhes do formato:

- Skill = `SKILL.md` com frontmatter `name` e `description`. **Sem frontmatter a skill é ignorada
  silenciosamente** — por isso o instalador valida antes de copiar.
- `mcp.json` aceita stdio (`command`, `args`, `env`) ou HTTP (`type: "http"`, `url`, `headers`).
  Referências `$VAR` são resolvidas do ambiente do processo.
- Uma conexão/skill recém-configurada não aparece retroativamente: é preciso abrir uma conversa nova
  (ou recarregar o cliente).

Skills de conta (por exemplo `jarvis-core`, `jarvis-vision`, `jarvis-desktop`, `jarvis-browser`,
`jarvis-pixels`, `agent-browser`, `playwright-cli`), sincronizadas com a Cloud, continuam valendo;
as quatro skills deste repositório são o complemento no nível do projeto.

## 2. Instalação

Na raiz do repositório, com o Python do `.venv` (dependências de `requirements/edge.txt`):

```powershell
.\.venv\Scripts\python.exe scripts\install_freebuff_harness.py            # plano (dry-run)
.\.venv\Scripts\python.exe scripts\install_freebuff_harness.py --apply --verify
```

O instalador:

1. copia as skills portáteis de `skills/` para `.agents/skills/` (somente as com frontmatter válido);
2. grava `.agents/mcp.json` registrando o servidor `jarvis_desktop` (stdio, interpretador do `.venv`)
   — usa `--force` se o arquivo existir com conteúdo diferente (uma cópia vira `mcp.json.bak`);
3. com `--verify`, faz handshake MCP real (`initialize`, `tools/list` e uma chamada de leitura
   `list_visual_templates`) e reporta tudo em JSON.

O servidor MCP deriva a raiz do repositório do próprio `__file__`, então o registro funciona mesmo que
o host o inicie de outro diretório de trabalho — verificado com `cwd` fora do repositório.

`.agents/` é um ponto de instalação local com caminho absoluto da máquina: está no `.gitignore` e não
deve ser commitado. Atualizou `skills/` no repositório? Rode o instalador de novo.

## 3. Estado verificado nesta máquina (2026-10-27)

| Item | Estado |
|---|---|
| 4 skills instaladas (`jarvis-android-navigation`, `jarvis-context-memory`, `jarvis-multi-agent-coordination`, `jarvis-visual-navigation`) | instalado, frontmatter validado |
| Handshake MCP `initialize` | ok — `Jarvis Desktop`, protocolo `2025-11-25` |
| `tools/list` | 26 ferramentas (desktop, Android, rede, curiosidade, briefings) |
| Chamada de leitura `list_visual_templates` | ok |
| Carregamento pela UI do Freebuff em conversa nova | **não verificado** — exige reiniciar/abrir nova conversa |

O `jarvis-multi-agent-coordination/SKILL.md` estava sem frontmatter (a skill seria ignorada);
o frontmatter foi adicionado neste repositório em 2026-10-27.

## 4. Rotas alternativas para MCP

`JARVIS_DESKTOP_TRANSPORT=streamable-http` já roda nesta máquina em `127.0.0.1:8765/mcp`, supervisionado e
publicado de forma privada por Tailscale Serve/Aperture. Para um cliente local prefira stdio (o padrão acima);
para outro dispositivo autorizado, use a rota remota:

```json
{
  "mcpServers": {
    "jarvis_desktop_remote": {
      "type": "http",
      "url": "https://aperture.tail350144.ts.net/v1/mcp"
    }
  }
}
```

Não registre dois servidores com o mesmo catálogo na mesma sessão: as ferramentas aparecem duplicadas.
Rotas, grants e critérios de aceite: [ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md](../ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md),
[NAVEGACAO_VISUAL.md](../NAVEGACAO_VISUAL.md) e [SECURE_MCP_TUNNEL.md](../SECURE_MCP_TUNNEL.md).

## 5. Segurança

- `.agents/mcp.json` não contém segredos; nada de tokens, chaves ou senhas em `.agents/`.
- O servidor controla a sessão Windows interativa: observe antes de agir, uma ação por vez, confirme o
  resultado, e mantenha as confirmações exigidas (`click_at`, captura de template).
- O contrato de bootstrap continua sendo o do repositório: [AGENTS.md](../../AGENTS.md),
  [CATALOG.md](CATALOG.md) e [CONTEXT_MEMORY_PROTOCOL.md](CONTEXT_MEMORY_PROTOCOL.md).
