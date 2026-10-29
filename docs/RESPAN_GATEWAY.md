# Respan Gateway no Jarvis

## Papel na arquitetura

O [Respan Gateway](https://github.com/respanai/respan-gateway?utm_source=freebuff&utm_medium=paid&utm_campaign=respan-gateway&bfcid=bfc_1.eyJpZCI6IjU2ZTk1ODc4LTJiMzYtNDFiZS04MjJjLTllZjY0MzAxOTAzZCIsImMiOiIyMDM2ODZkZS1mMzg0LTQ4NTQtYmViNC1hYzBiYWRmNmM1NTUiLCJrIjoiM2IxMGE4YmUtNzgyOS00MmJhLWFmNmEtYmI0YWUxZTRhY2Y4IiwiaWF0IjoxNzkzMjEzODIyfQ.BWXXO44GZf9RgS2sU5VElUarHHC-JtgQY5glkAm7Nbg) é um gateway de LLM open-source que roda **in-process** no processo Python do Jarvis: um único cliente OpenAI-compatible (`gw.openai()`) que decide provider/modelo por rotas, repete a chamada e cai para o próximo candidato quando um provedor falha.

- **`AIGateway`** ganhou o provider `respan` (`LLMProvider.RESPAN`), ao lado de Groq, Gemini e Venice.
- O gateway **não** pede conta, créditos hospedados nem export de tracing do Respan: ele gasta as chaves de provider que o projeto já tem (`GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, ...).
- Quando habilitado, ele é a **camada de roteamento** das conclusões de texto (chat): o modelo pedido é roteado pelo nome (`groq/<modelo>`, `claude-*`, `gemini-*`) e as rotas do `gateway.toml` cuidam de retries/fallback. Se o gateway falhar, o `AIGateway` cai para Groq → Gemini → Venice.
- **Desligado por padrão**: sem `RESPAN_GATEWAY_ENABLED=true`, o comportamento atual (High Gear → Low Gear → Gemini/Venice) continua idêntico.

## Instalação

O pacote está fixado em `requirements.txt`:

```bash
pip install -r requirements.txt   # inclui respan-gateway==0.3.0
# ou, isolado:
pip install --only-binary=:all: respan-gateway==0.3.0
```

Requer **Python 3.10+** e os wheels publicados (Linux x64/arm64 com glibc 2.28+, macOS x64/arm64, Windows x64). O cliente `gw.openai()` usa o pacote `openai`, já declarado no projeto.

## Configuração

Variáveis de ambiente (coloque no `.env`, que é ignorado pelo git; nunca em código ou front-end):

| Variável | Significado |
|---|---|
| `RESPAN_GATEWAY_ENABLED` | `true` liga o provider `respan` no `AIGateway` (padrão: desligado). |
| `RESPAN_MODEL` | Modelo pedido ao gateway. Padrão: `groq/<GROQ_MODEL>` (usa a Marcha Alta configurada). |
| `RESPAN_GATEWAY_CONFIG` | Caminho de um `gateway.toml` existente. Sem ele, o gateway usa `./gateway.toml` se existir, senão descobre os providers pelas chaves do ambiente. |

Um `gateway.toml` mínimo (rotas, providers extras, `client_keys`, MCP) é opcional; segredos dentro dele devem ser referências `env:NAME`:

```toml
[routes.jarvis]                       # clientes pedem "model": "jarvis"
to = ["groq/llama-3.3-70b-versatile", "gemini/gemini-1.5-pro"]
tries = 2
```

## Uso

```bash
# 1. Ver o que a configuração atual serviria (providers + modelos)
python scripts/check_respan_gateway.py

# 2. Enviar uma conclusão real pelo caminho integrado AIGateway -> gateway
python scripts/check_respan_gateway.py --prompt "diga olá"

# 3. Servidor local em loopback, para stacks que não são Python
python scripts/check_respan_gateway.py --serve --port 8099
#    clientes OpenAI-compatíveis usam http://127.0.0.1:8099/v1
#    Ctrl-C encerra; para subir de novo, o mesmo comando.

# 4. Aplicação normal (o gateway abre in-process quando habilitado)
python main.py
```

Equivalente pela CLI do pacote: `python -m respan_gateway` (ou `respan-gateway`) serve o gateway; `respan-gateway check --online` valida a configuração chamando cada provider.

Com `RESPAN_GATEWAY_ENABLED=true`, `GatewayLLMCommandAdapter.generate_conversational_response` e `LLMCommandInterpreter` passam a receber `{"provider": "respan", "model": ...}` de `AIGateway.generate_completion`; os extratores de resposta do projeto já reconhecem esse provider (resposta OpenAI-compatible).

## O que foi verificado

- `tests/adapters/test_ai_gateway_respan.py` (9 testes) cobre: provider desligado por padrão, seleção/forçar `respan`, modelo padrão `groq/<Marcha Alta>`, extração de texto e fallback para Groq em erro de rate limit.
- O teste de fumaça `test_gateway_routes_a_completion_through_the_local_provider` abre o gateway de verdade com um **provider fixture local** (OpenAI-compatible em `127.0.0.1`, porta efêmera), chama `AIGateway.generate_completion` e confirma que o fixture recebeu `POST /v1/chat/completions` e que a resposta voltou com `provider == "respan"`. O mesmo caminho foi exercitado via `scripts/check_respan_gateway.py --prompt`.
- **Nenhuma requisição a provedor real foi executada nesta verificação** (o ambiente não tinha chaves): a conclusão veio do fixture local. Chamada live fica para o ambiente normal do desenvolvedor, com `RESPAN_GATEWAY_ENABLED=true` e as chaves no `.env`.

## Limites

- O provider usa `chat.completions`; multimodal continua indo para Gemini/Venice.
- Gateway sem `client_keys` recusa endereço não-loopback: mantenha o servidor em `127.0.0.1`.
- Falha ao abrir o gateway (pacote ausente, nenhuma chave, config inválida) só desabilita o provider e registra warning; o app segue com os provedores diretos.

## Referências

- Guia oficial (v0.3.0): https://github.com/respanai/respan-gateway?utm_source=freebuff&utm_medium=paid&utm_campaign=respan-gateway&bfcid=bfc_1.eyJpZCI6IjU2ZTk1ODc4LTJiMzYtNDFiZS04MjJjLTllZjY0MzAxOTAzZCIsImMiOiIyMDM2ODZkZS1mMzg0LTQ4NTQtYmViNC1hYzBiYWRmNmM1NTUiLCJrIjoiM2IxMGE4YmUtNzgyOS00MmJhLWFmNmEtYmI0YWUxZTRhY2Y4IiwiaWF0IjoxNzkzMjEzODIyfQ.BWXXO44GZf9RgS2sU5VElUarHHC-JtgQY5glkAm7Nbg
- API Python: https://github.com/respanai/respan-gateway/blob/v0.3.0/python/README.md
- Configuração: https://github.com/respanai/respan-gateway/blob/v0.3.0/docs/configuration.md
