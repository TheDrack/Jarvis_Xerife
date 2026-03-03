# JARVIS – Status Atual do Projeto

> **Data:** 2026-03-03  
> **Situação geral:** Reorganização estrutural concluída. Núcleo Proativo ativo.

---

## ⚙️ Estado do Projeto

| Componente | Status |
|---|---|
| Nexus (Injeção de Dependência) | ✅ Ativo |
| Nexus Circuit Breaker | ✅ Ativo (timeout 2 s, cooldown 60 s) |
| API REST (FastAPI) | ✅ Ativo |
| Adaptadores de Borda (Voz, Teclado) | ✅ Ativo |
| Adaptadores de Infraestrutura (LLM, DB, GitHub) | ✅ Ativo |
| Domínio (Modelos, Serviços) | ✅ Ativo |
| **Memória Vetorial (FAISS)** | ✅ **Ativo** (biográfica, 30 dias) |
| **Visão Computacional (Gemini 1.5 Flash)** | ✅ **Ativo** (screenshot / webcam) |
| **Overwatch Daemon (Núcleo Proativo)** | ✅ **Ativo** (CPU/RAM, contexto, inatividade) |
| Auto-Evolução | ⏸️ **PAUSADA** (reorganização) |
| Playwright Worker | 🔧 Em revisão |
| Instalador PyInstaller | 🔧 Em revisão |

---

## 🗂️ Estrutura de Pastas

```
app/
├── core/               # Nexus, NexusComponent, Config, Encryption, LLM config
├── domain/             # Lógica de negócio pura (modelos, serviços, AI, gears)
├── application/        # Casos de uso, portas (interfaces) e serviços
│   ├── ports/          # Interfaces que os adaptadores devem implementar
│   └── services/       # Serviços de aplicação (orchestrator, assistant, etc.)
├── adapters/           # Implementações das portas
│   ├── edge/           # Adaptadores de hardware (voz, teclado, automação)
│   └── infrastructure/ # Adaptadores de infraestrutura (LLM, DB, GitHub, API)
├── plugins/            # Sistema de plugins dinâmicos
├── runtime/            # Pipeline runner (orquestração declarativa)
└── utils/              # Utilitários gerais

.frozen/                # Arquivos não instanciados (aguardando uso)
├── caps/               # Capabilities não ativas
├── domain_adapters/    # Adaptadores que estavam no domain (movidos)
├── infrastructure/     # Duplicatas antigas de infrastructure
└── orphan_caps/        # Capabilities órfãs de app/adapters root
```

---

## 🧬 Nexus – Sistema de Injeção de Dependência

O **Nexus** (`app/core/nexus.py`) é o sistema central de instanciação.  
**Todos os componentes ativos devem ser NexusComponent e registrados no Nexus.**

- Componentes não instanciados pelo Nexus → movidos para `.frozen/`
- Registry local: `data/nexus_registry.json`
- Registry remoto: Gist do GitHub (sincronizado automaticamente)
- **Circuit Breaker:** se a instanciação demorar > 2 s, injeta `CloudMock` por 60 s.

---

## 🧠 Memória Vetorial (Ativo desde 2026-03-03)

O JARVIS agora possui **memória biográfica persistente** via `VectorMemoryAdapter`:

- Implementa a porta `MemoryProvider` (`app/application/ports/memory_provider.py`).
- Usa **FAISS** (com fallback puro-Python offline) para busca por similaridade.
- Vetores gerados via bag-of-hashed-words (sem necessidade de modelo externo).
- A cada resposta, o `AssistantService` consulta os **30 dias anteriores** por contexto similar e armazena o comando do usuário e a resposta do JARVIS.
- Registrado no Nexus como `vector_memory_adapter`.

---

## 👁️ Visão Computacional (Ativo desde 2026-03-03)

O `VisionAdapter` (`app/adapters/infrastructure/vision_adapter.py`) permite que o JARVIS "veja":

- Captura silenciosa de screenshot (mss/Pillow) ou frame de webcam (OpenCV).
- Envia a imagem ao **Gemini 1.5 Flash** com o prompt: *"Descreva o contexto atual do usuário em 1 frase"*.
- Todas as dependências são opcionais (fallback `None` se indisponíveis).
- Registrado no Nexus como `vision_adapter`.

---

## 🔭 Overwatch Daemon – Núcleo Proativo (Ativo desde 2026-03-03)

O `OverwatchDaemon` (`scripts/overwatch_daemon.py`) roda em background, independente do loop de comandos:

| Monitoramento | Ação |
|---|---|
| CPU > 85% ou RAM > 85% | Notifica via Telegram/voz |
| Mudança em `data/context.json` | Recarrega contexto |
| Inatividade > 30 min | Usa `VisionAdapter` para verificar presença; se presente, sugere tarefa pendente do calendário |

Todas as ações são logadas com o prefixo `[PROACTIVE_CORE]`.  
Iniciado automaticamente em `main.py` via `bootstrap_background_services()`.
Usa `nexus.resolve()` para acessar `vision_adapter`, `telegram_adapter` e `voice_provider`.

---

## 🧊 Política Frozen

Arquivos em `.frozen/` são código não utilizado atualmente.  
Eles ficam preservados até que sejam necessários.  
Para reativar um arquivo frozen:
1. Mova-o para o local correto em `app/`
2. Registre-o no Nexus via `data/nexus_registry.json`
3. Atualize esta documentação

---

## ⏸️ Auto-Evolução (PAUSADA)

O sistema de auto-evolução está **pausado** enquanto a reorganização estrutural é concluída.

- Workflow: `.github/workflows/auto_evolution_triggerV2.yml`
- Status: `workflow_dispatch` apenas (requer acionamento manual)
- Para reativar: revisar estrutura → estabilizar → remover pausa

---

## 🚧 Pendências

- [ ] Revisar `app/domain/gears/` – muitos `cap_*_core.py` ainda presentes
- [ ] Revisar `app/domain/capabilities/` – necessita limpeza
- [ ] Playwright Worker necessita revisão de integração
- [ ] Testes precisam ser atualizados para nova estrutura
