# Jarvis Desktop

Aplicativo Windows nativo baseado em WebView2, exibindo o mesmo HUD remoto do Jarvis.
Não duplica o dashboard nem cria outro fluxo de autenticação: usa a mesma origem HTTPS,
o login existente e a rota /intelligence.

## Requisitos

- Windows 10/11
- Python 3.10+
- Microsoft Edge WebView2 Runtime
- Rede disponível para acessar a API Jarvis

## Instalação

Na raiz do repositório, execute:

    python -m pip install -r requirements/desktop.txt
    python -m app.adapters.edge.jarvis_desktop_shell

A primeira abertura carrega o HUD principal para autenticação. Depois do login,
abra INTELLIGENCE pelo HUD. O perfil WebView fica em
%LOCALAPPDATA%\Jarvis\Desktop\WebView2 e mantém a sessão entre reinicializações.

Se a sessão já existir, abra diretamente o painel:

    python -m app.adapters.edge.jarvis_desktop_shell --page intelligence

Painel de dispositivos:

    python -m app.adapters.edge.jarvis_desktop_shell --page network

Servidor local de desenvolvimento (HTTP permitido apenas em loopback):

    $env:JARVIS_CLOUD_BASE_URL = "http://127.0.0.1:10000"
    python -m app.adapters.edge.jarvis_desktop_shell

Outro deployment HTTPS:

    $env:JARVIS_CLOUD_BASE_URL = "https://your-jarvis-host.example"
    python -m app.adapters.edge.jarvis_desktop_shell

## Segurança e arquitetura

- Nenhuma chave de API, credencial de provedor, segredo Render ou bearer token
  é embutido no código ou passado por argumentos.
- O fluxo de login existente continua sendo a autoridade de autenticação.
- O WebView usa perfil persistente por usuário Windows; as ACLs do perfil protegem
  os dados locais da sessão.
- HTTP é recusado para hosts não-loopback.
- A dependência desktop fica isolada em requirements/desktop.txt e não entra
  no ambiente de produção do Render.
- O shell desktop é apresentação. Hardware local, câmeras, MCP e controle de
  rede permanecem no Edge/Local Bridge.
- Modo offline ainda não é implementado: este primeiro incremento exige acesso
  ao HUD remoto. A ponte local e fallback offline são etapas separadas.
