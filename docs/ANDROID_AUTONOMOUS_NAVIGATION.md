# Navegação autônoma Android (módulo aditivo)

## Escopo

Esta integração acrescenta uma ponte opcional Jarvis → Google ARTEMIS para executar tarefas de interface em Android. Não modifica o adaptador de navegação visual desktop, o contrato `VisualNavigationPort`, o MacroDroid, nem o registro atual de dispositivos.

## Arquitetura

- `app/application/ports/android_navigation.py`: contrato isolado da nova capacidade.
- `app/adapters/edge/artemis_android_navigation_adapter.py`: adaptador opcional para `artemis-client`.
- `tests/adapters/test_artemis_android_navigation_adapter.py`: testes com cliente falso, sem telefone, ADB, rede ou credenciais.
- O despacho atual do líder/registro de dispositivos ainda não é alterado. Esta primeira etapa deixa o adaptador explicitamente invocável, evitando acoplamento ou roteamento automático prematuro.

## Configuração

1. Inicie um servidor ARTEMIS em uma máquina confiável que tenha ADB e o dispositivo Android autorizado conectado.
2. Configure `JARVIS_ARTEMIS_SERVER_URL` no processo que instancia o adaptador.
3. Instale `artemis-client` apenas no ambiente dedicado da integração, conforme as instruções oficiais do [ARTEMIS](https://github.com/google/artemis).
4. Passe o serial Android registrado explicitamente como `device_id`. O adaptador não escolhe um telefone automaticamente.
5. Use o perfil `pro` para tarefas que exigem planejamento/verificação; `flash` é para ações rotineiras e simples. A verificação real do resultado continua obrigatória.

## Exemplo

```python
import os
from app.adapters.edge.artemis_android_navigation_adapter import ArtemisAndroidNavigationAdapter

android_nav = ArtemisAndroidNavigationAdapter(
    server_url=os.environ["JARVIS_ARTEMIS_SERVER_URL"]
)
result = android_nav.run_task(
    instruction="Abra Configurações e confirme que a tela Configurações está visível.",
    device_id="SERIAL_ANDROID_REGISTRADO",
    profile="pro",
)
if not result["success"]:
    raise RuntimeError(f"Navegação Android falhou: {result}")
```

## Segurança e limitações

- Não inclua credenciais em instruções ou logs.
- A URL do servidor deve permanecer em rede privada/autorizada; não exponha o endpoint publicamente sem autenticação e controles de acesso.
- Não execute tarefas destrutivas sem autorização específica.
- A etapa atual não sincroniza automaticamente o cadastro Jarvis com a lista de dispositivos ADB. Essa ligação precisa de uma mudança de integração separada, depois de definir uma fonte de identidade confiável e testar a seleção do dispositivo.
- Os testes unitários usam doubles e não comprovam conectividade real com telefone nem compatibilidade ponta a ponta; isso exige ambiente ARTEMIS/ADB conectado.

## Referências

- [Google ARTEMIS](https://github.com/google/artemis)
- [README e SDK](https://github.com/google/artemis/blob/main/README.md)
- [MCP Server ARTEMIS](https://github.com/google/artemis/tree/main/mcp_server)
