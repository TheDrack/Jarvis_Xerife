# Jarvis — áudio móvel, presença e aquecimento do Render

## Objetivo
Usar a interface de voz do site Jarvis já publicada no Render e salva no celular. Não criar uma segunda interface/PWA de áudio. Este documento separa o que já existe do que ainda precisa de integração.

## Aquecimento do serviço hospedado
- O serviço principal configurado em `render.yaml` é `jarvis-api`; a URL de produção referenciada pelo workflow atual é `https://jarvis-api-c47i.onrender.com`.
- A API já possui `GET /health` para health checks e `GET /warmup` para resolver componentes críticos do Nexus e verificar o banco.
- `.github/workflows/keepalive.yml` executa a cada 10 minutos e também aceita execução manual (`workflow_dispatch`). O workflow foi ajustado para chamar `/warmup`, em vez de apenas `/health`, e imprimir a resposta JSON para diagnóstico.
- Esse agendamento é uma estratégia de keep-alive: tende a evitar o repouso por inatividade no plano gratuito, mas consome minutos de GitHub Actions e não garante disponibilidade permanente. Para acordar apenas quando o usuário abrir o site, o frontend existente precisa chamar `/warmup` no início e então consultar `/health` com retentativas limitadas; a origem do frontend não foi identificada neste repositório, portanto essa chamada ainda não foi adicionada à UI.
- A rota `/warmup` é pública hoje. Ela não deve aceitar ações destrutivas nem retornar segredos; a resposta deve conter somente estado operacional.

## Presença local e acesso privado
- `PresenceService` é uma máquina de estados isolada (`READY`, `ACTIVE`, `AWAY`, `SLEEP`) com limites configuráveis. Ela ainda não está conectada ao ciclo de vida da API nem ao cliente móvel.
- A rota MCP local em `127.0.0.1:8765` e a configuração Tailscale existente devem ser preservadas. Não habilitar Tailscale Funnel nem publicar a API local para a internet.
- Acordar o serviço hospedado no Render é diferente de acordar o computador Windows pela rota RDC–Aperture–Tailscale–Jarvis; não misturar os dois mecanismos.

## Estado atual e limites
- A interface de voz móvel já existe no site publicado, conforme confirmado pelo usuário. Não criar uma UI substituta.
- `app/adapters/api/voice_endpoint.py` contém um fluxo conceitual de voz via WebSocket, mas não foi confirmado como parte da API publicada nem como protegido por autenticação. Não expor esse endpoint diretamente sem integrar autenticação, limites de tamanho, timeouts e tratamento de desconexão.
- O adaptador TTS `pyttsx3` depende do áudio do Windows; não resolve sozinho a reprodução no celular.
- A senha administrativa fica fora do escopo deste ajuste e não foi alterada.

## Verificações recomendadas
1. Executar manualmente o workflow `keepalive` no GitHub Actions e confirmar HTTP 200 e JSON com `status: warm`.
2. Confirmar que a URL `https://jarvis-api-c47i.onrender.com/warmup` responde no Render. Um primeiro acesso pode demorar devido ao cold start.
3. Quando a localização do frontend for identificada, ligar a chamada inicial a `/warmup` na interface já existente, com timeout e retentativas limitadas.
4. Testar `PresenceService` e, em etapa separada, integrar presença autenticada ao cliente e ao agendador sem suspender Tailscale ou acesso remoto.

## Próximos passos
1. Identificar o repositório/origem do site de voz já instalado no celular para adicionar o aquecimento no evento de abertura, sem duplicar a interface.
2. Integrar a presença local com autenticação e telemetria mínima, sem registrar tokens ou conteúdo de áudio.
3. Tratar a recuperação da senha administrativa em uma etapa posterior, sem rotação de `SECRET_KEY` nem alterações de banco não verificadas.
