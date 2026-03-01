# JARVIS – Status Atual do Projeto

> **Data:** 2026-03-01  
> **Situação geral:** Reorganização estrutural em andamento

---

## ⚙️ Estado do Projeto

| Componente | Status |
|---|---|
| Nexus (Injeção de Dependência) | ✅ Ativo |
| API REST (FastAPI) | ✅ Ativo |
| Adaptadores de Borda (Voz, Teclado) | ✅ Ativo |
| Adaptadores de Infraestrutura (LLM, DB, GitHub) | ✅ Ativo |
| Domínio (Modelos, Serviços) | ✅ Ativo |
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
