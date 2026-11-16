# Paridade móvel do Jarvis Global

## Arquitetura implementada

- **Global HUD:** `app/static/jarvis-desktop.html`, servido por `GET /` no runtime local `app/adapters/edge/jarvis_desktop_local.py`.
- **Universal Intelligence:** `app/static/intelligence.html`, servido por `GET /intelligence`.
- **PWA:** manifesto raiz em `/manifest.webmanifest`; Service Worker em `/service-worker.js`, com escopo `/`.
- **Android nativo:** `mobile/android` mantém login móvel, armazenamento de tokens no Android Keystore, presença, notificações, chat, voz, TTS e compartilhamento de localização opt-in. A aba HUD pode carregar o mesmo Global HUD responsivo.
- **Fonte de verdade:** os clientes reutilizam o runtime e os contratos existentes. Esta implementação não cria uma segunda API de negócio nem duplica os módulos do HUD.

## Matriz de capacidades do Global HUD

| Módulo | Desktop | Navegador/PWA móvel | Android WebView |
|---|---|---|---|
| Core e briefing | Sim | Sim, layout responsivo | Sim, ao abrir o HUD |
| Eventos | Sim | Sim | Sim, ao abrir o HUD |
| Fontes | Sim | Sim | Sim, ao abrir o HUD |
| Orbital / God's Eye | Sim | Sim | Sim, ao abrir o HUD |
| Telemetria do host | Sim | Sim, somente leitura | Sim, ao abrir o HUD |
| Rede / topologia | Sim | Sim, inventário passivo/read-only | Sim, ao abrir o HUD |
| Dispositivos | Sim | Sim, inventário read-only | Sim, ao abrir o HUD |
| Câmeras | Sim | Sim, modal e controles com alvos de toque móveis | Sim, ao abrir o HUD |
| Universal Intelligence | Sim | Sim, página responsiva e navegável | Sim, ao abrir o HUD |

A navegação móvel do Global usa uma barra persistente horizontal, rolagem independente dos painéis, alvos de toque de pelo menos 44 px e respeito às áreas seguras do Android. Os módulos são os já existentes no HUD; a presença na matriz não significa que o backend ganhou novas capacidades.

## PWA e armazenamento

- O manifesto inicia em `/`, usa escopo raiz e modo `standalone`.
- O Service Worker encaminha requisições GET diretamente à rede.
- **Não há cache offline:** tokens, páginas autenticadas e respostas da API não são persistidos em Cache Storage.
- A instalação PWA no Chrome requer contexto seguro: HTTPS ou localhost. HTTP em IP de LAN não satisfaz esse requisito.
- A PWA não substitui o aplicativo Android nativo. O app continua responsável por recursos do sistema operacional móvel, como presença, notificações, microfone, TTS e localização opt-in.

## Limites de segurança e integração

- As rotas existentes do HUD continuam exigindo o token local de pareamento quando acessam dados e ações autenticadas. O manifesto e o Service Worker são recursos estáticos.
- A coleta de rede é passiva/read-only; não são introduzidos probes ativos.
- Telemetria e inventário de dispositivos são somente leitura.
- Esta entrega não introduz shell remoto, elevação de privilégio, escrita arbitrária no host, encerramento de processos ou alteração de serviços Ubuntu.
- O código do Global HUD pode ser servido em Linux/Ubuntu pelo runtime local, mas a integração completa com `HostPort`, supervisão do sistema, comandos equivalentes de terminal e recuperação do Ubuntu ainda requer incrementos próprios com autorização e auditoria.

## Graphify Memory / aprovações

A interface móvel ainda não aprova candidatos Graphify. No estado verificado desta implementação:
- O repositório Jarvis não contém endpoint de leitura ou aprovação da fila Graphify.
- O conector Graphify disponível fornece consulta/revisão de estado e gravação de notas, mas não expõe uma operação de aprovação/publicação que o runtime Jarvis possa chamar.
- Não é seguro simular uma aprovação no frontend ou aceitar um booleano fornecido pelo cliente.

A integração exige uma API oficial autorizada, identidade do revisor, escopo de permissão, auditoria e testes de estado/transição. Até isso existir, a aprovação continua no fluxo oficial do Graphify.

## Verificação e critérios de aceitação

- Testes de contrato cobrem entrega do manifesto e Service Worker, ausência de cache, navegação dos módulos existentes e contratos de layout responsivo.
- GitHub Actions deve executar o pytest completo antes do merge.
- Ainda é necessária validação visual em Android físico e navegador desktop; testes de contrato não substituem teste de interação real.
- A instalação PWA remota depende de HTTPS configurado no ambiente de publicação.
