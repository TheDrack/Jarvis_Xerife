# JARVIS – Arquitetura

> Arquitetura Hexagonal (Ports & Adapters) com Nexus como container de DI.

---

## Visão Geral

```
┌─────────────────────────────────────────────────────┐
│                    INTERFACE / CI-CD                 │
│        (GitHub Actions, API REST, Terminal)          │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│               ADAPTADORES (app/adapters/)            │
│  ┌─────────────────┐   ┌────────────────────────┐   │
│  │   edge/         │   │   infrastructure/      │   │
│  │  voz, teclado   │   │  LLM, DB, GitHub, API  │   │
│  └────────┬────────┘   └──────────┬─────────────┘   │
└───────────┼──────────────────────┼─────────────────┘
            │                      │
┌───────────▼──────────────────────▼─────────────────┐
│            APLICAÇÃO (app/application/)              │
│  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │     ports/       │  │       services/           │ │
│  │  (interfaces)    │  │   (casos de uso)          │ │
│  └──────────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────┐
│               DOMÍNIO (app/domain/)                  │
│  models/ │ services/ │ gears/ │ context/ │ missions/ │
└─────────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────┐
│               NÚCLEO (app/core/)                     │
│          Nexus │ Config │ Encryption │ LLM Config    │
└─────────────────────────────────────────────────────┘
```

---

## Camadas

### Core (`app/core/`)
Núcleo do sistema. Sem dependências externas.
- **Nexus**: Container de DI com discovery automático e sincronização via Gist
- **NexusComponent**: Interface base para todos os componentes
- **Config/Encryption**: Configuração segura do sistema

### Domain (`app/domain/`)
Lógica de negócio pura. Sem dependências de infraestrutura.
- **models/**: Entidades do domínio (Pydantic/dataclasses)
- **services/**: Serviços de domínio (interpretação de comandos, estado)
- **gears/**: Sistema de engrenagens LLM (multi-tier)

### Application (`app/application/`)
Casos de uso. Depende apenas do domínio via portas.
- **ports/**: Interfaces (ABCs) que os adaptadores implementam
- **services/**: Orchestration, assistente, evolução, etc.

### Adapters (`app/adapters/`)
Implementações concretas das portas.
- **edge/**: Hardware (voz, teclado, câmera, automação desktop)
- **infrastructure/**: Cloud (LLM, GitHub, banco de dados, API REST)

---

## Nexus – Fluxo de Resolução

```
nexus.resolve("component_id")
    │
    ├── 1. Cache local (já instanciado antes?) → retorna instância
    ├── 2. Remoto (Gist) → busca module_path no mapa remoto
    └── 3. Discovery local → percorre app/ procurando {component_id}.py
```

---

## Pipeline Runner – Fluxo

```
GitHub Actions
    └── pipeline: build_installer
        └── python app/runtime/pipeline_runner.py
            └── lê config/pipelines/build_installer.yml
                └── nexus.resolve("pyinstaller_builder")
                    └── executa PyinstallerBuilder.execute(context)
```

---

## Princípios

1. **Nexus instancia tudo** – nenhum `import` direto de adaptadores no domínio
2. **Portas definem contratos** – domínio depende de interfaces, não implementações
3. **Pipelines são declarativos** – lógica de build/deploy fica nos componentes, não no CI
4. **Frozen para código inativo** – nada morto no código ativo
