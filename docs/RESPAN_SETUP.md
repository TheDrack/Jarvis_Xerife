# Respan: observabilidade e gateway

O Jarvis possui dois caminhos separados; habilitar um não habilita automaticamente o outro.

## 1. Tracing dos SDKs Python

O pacote `respan-ai==4.2.4` é inicializado no início de `main.py`, antes da construção dos clientes LLM. Com `RESPAN_API_KEY` ausente, o tracing fica desativado e o Jarvis continua a iniciar. Com a chave presente, o SDK detecta e instrumenta SDKs LLM compatíveis usados diretamente pela aplicação.

Configure `RESPAN_API_KEY` somente no `.env` local (já ignorado pelo Git) ou no gestor de segredos do ambiente. Nunca comite a chave. Requer Python 3.11–3.13, conforme a documentação oficial.

## 2. Roteamento pelo Respan Gateway open-source

O provider opcional existente no `AIGateway` usa `respan-gateway==0.3.0`, controlado por `RESPAN_GATEWAY_ENABLED`. O gateway pode usar chaves de providers já configuradas, sem exigir uma chave Respan para inferência.

Para exportar traces das requisições que passam pelo gateway, configure um `gateway.toml` existente com:

```toml
[plugins.respan]
key = "env:RESPAN_API_KEY"
content = false
```

`content = false` envia metadados sem mensagens/respostas. O arquivo de configuração deve continuar local e não conter credenciais literais. Defina `RESPAN_GATEWAY_CONFIG` para o caminho do arquivo, e `RESPAN_GATEWAY_ENABLED=true` para habilitar o gateway apenas quando as chaves dos providers necessárias estiverem configuradas. Não exponha o gateway em interfaces públicas sem autenticação.

## Verificação

- `python -m pytest tests/adapters/test_respan_tracing.py -q` verifica o comportamento de inicialização, ausência de chave e encerramento sem chamar serviços externos.
- `python scripts/check_respan_gateway.py` verifica a configuração local do gateway; `--prompt` faz uma chamada real e pode consumir créditos do provider.
- Para confirmar telemetria real, execute uma chamada autorizada com as chaves locais e confira Observability/Logs no Respan. Testes locais com mocks não provam que os traces chegaram ao serviço.

## Documentação oficial

- [Agent setup](https://respan.ai/docs/agent-setup.md)
- [Tracing quickstart](https://www.respan.ai/docs/documentation/features/tracing/quickstart)
- [Open-source gateway](https://www.respan.ai/docs/oss-gateway/introduction)
- [Gateway tracing plugin](https://www.respan.ai/docs/oss-gateway/plugins#respan-tracing)
