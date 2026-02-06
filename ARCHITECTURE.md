# Arquitetura Hexagonal do Jarvis Assistant

## Visão Geral

Este projeto foi refatorado para seguir o padrão de **Arquitetura Hexagonal** (também conhecida como Ports and Adapters), criado por Alistair Cockburn. Esta arquitetura separa claramente a lógica de negócio (domínio) das preocupações de infraestrutura e hardware.

## Por Que Arquitetura Hexagonal?

### Motivação

1. **Cloud Readiness**: Permitir que o núcleo da aplicação rode em ambientes headless (sem display, áudio ou entrada de hardware) na nuvem
2. **Separação de Responsabilidades**: Isolar a lógica de decisão e interpretação de comandos das dependências de hardware
3. **Testabilidade**: Facilitar testes sem necessidade de hardware real (mocks)
4. **Escalabilidade**: Preparar para múltiplos dispositivos clientes (Edge) comunicando com um cérebro central (Cloud)
5. **Flexibilidade**: Trocar implementações de infraestrutura sem alterar a lógica de negócio

### Conceito: Cloud (Cérebro) vs Edge (Corpo)

```
┌─────────────────────────────────────────────────────────────┐
│                         CLOUD (Cérebro)                      │
│  - Lógica de decisão e interpretação                        │
│  - Processamento de intenções                                │
│  - Regras de negócio                                         │
│  - Orquestração de comandos                                  │
│  - Totalmente independente de hardware                       │
└─────────────────────────────────────────────────────────────┘
                              ↕
                       Ports (Interfaces)
                              ↕
┌─────────────────────────────────────────────────────────────┐
│                         EDGE (Corpo)                         │
│  - Reconhecimento de voz local                               │
│  - Síntese de fala (TTS)                                     │
│  - Automação de interface (PyAutoGUI)                        │
│  - Controle de teclado/mouse                                 │
│  - Depende de hardware físico                                │
└─────────────────────────────────────────────────────────────┘
```

## Estrutura da Arquitetura

### 1. Domain (Núcleo)

**Localização**: `app/domain/`

**Características**:
- Python puro, sem dependências externas
- Lógica de negócio e regras de decisão
- Modelos de dados (Command, Intent, Response)
- Serviços de domínio (CommandInterpreter, IntentProcessor)
- **100% cloud-ready** - pode rodar em qualquer ambiente

**Componentes**:
```
app/domain/
├── models/
│   └── command.py          # Entidades: Command, Intent, Response, CommandType
└── services/
    ├── command_interpreter.py  # Interpreta texto em Intent
    └── intent_processor.py     # Processa Intent em Command
```

### 2. Application (Casos de Uso)

**Localização**: `app/application/`

**Características**:
- Define contratos (Ports) usando `abc.ABC`
- Orquestra o fluxo da aplicação
- Independente de implementações específicas
- Usa injeção de dependência

**Componentes**:
```
app/application/
├── ports/                  # Interfaces (Contratos)
│   ├── voice_provider.py   # Interface para voz (listen, speak)
│   ├── action_provider.py  # Interface para automação (type, click, press)
│   ├── web_provider.py     # Interface para navegação web
│   └── system_controller.py # Interface para controle de sistema
└── services/
    └── assistant_service.py # Orquestrador principal dos casos de uso
```

### 3. Adapters (Implementações)

**Localização**: `app/adapters/`

**Características**:
- Implementações concretas dos Ports
- Separados em Edge e Infrastructure
- Podem ser trocados sem afetar o domínio

#### Edge Adapters (Hardware Local)

**Localização**: `app/adapters/edge/`

**Dependências**: PyAutoGUI, SpeechRecognition, pyttsx3, pynput

```
app/adapters/edge/
├── voice_adapter.py        # SpeechRecognition (Google Speech API)
├── tts_adapter.py          # pyttsx3 (Text-to-Speech)
├── automation_adapter.py   # PyAutoGUI (screen automation)
├── keyboard_adapter.py     # pynput (keyboard control)
├── web_adapter.py          # webbrowser + automation
└── combined_voice_provider.py # Combina TTS + Voice
```

#### Infrastructure Adapters (Cloud/Serviços)

**Localização**: `app/adapters/infrastructure/`

**Uso Futuro**: Logging, APIs, Databases, Message Queues

### 4. Dependency Injection Container

**Localização**: `app/container.py`

**Função**: 
- Cria e gerencia todas as dependências
- Injeta adapters nos serviços de aplicação
- Factory functions para diferentes ambientes

**Exemplo**:
```python
container = create_edge_container(wake_word="xerife", language="pt-BR")
assistant = container.assistant_service
assistant.start()
```

### 5. Bootstrap (Pontos de Entrada)

**Localização**: `app/bootstrap_edge.py`, `main.py`

**Função**:
- Inicializa a aplicação com adaptadores específicos
- Configura logging
- Gerencia lifecycle da aplicação

## Fluxo de Dados

```
1. User speaks → VoiceAdapter.listen()
                    ↓
2. Text → CommandInterpreter.interpret() → Intent
                    ↓
3. Intent → IntentProcessor.validate() + create_command() → Command
                    ↓
4. Command → AssistantService._execute_command()
                    ↓
5. Execution → ActionProvider / WebProvider (adapters)
                    ↓
6. Response → VoiceProvider.speak() → User hears feedback
```

## Separação de Dependências

### Core Dependencies (`requirements/core.txt`)
- Pydantic para configuração
- FastAPI e Uvicorn para API server
- SQLModel e psycopg2 para persistência
- **Cloud-ready**: Roda em qualquer ambiente Linux headless
- Sem dependências de hardware

### Edge Dependencies (`requirements/edge.txt`)
- Inclui core.txt
- Adiciona PyAutoGUI, SpeechRecognition, pyttsx3, pynput
- Adiciona google-generativeai para integração LLM
- **Requer**: Display server, audio drivers, input devices

### Dev Dependencies (`requirements/dev.txt`)
- Inclui core.txt
- Ferramentas de teste: pytest, pytest-cov, pytest-mock
- Type checking: mypy
- Code quality: black, flake8, isort
- Development tools: ipython, ipdb

### Produção
- `requirements/prod-edge.txt`: Edge completo + opcionais para monitoramento
- `requirements/prod-cloud.txt`: Só core + API server para deployment headless

## Testabilidade

### Testes de Domínio
- Não precisam de mocks de hardware
- Testam lógica pura de interpretação e processamento
- Rápidos e confiáveis

### Testes de Aplicação
- Usam mocks dos Ports (interfaces)
- Testam orquestração sem hardware real
- Podem rodar em CI/CD sem display/audio

### Testes de Adapters
- Testam implementações específicas
- Podem requerer hardware em alguns casos
- Podem ser isolados se necessário

**Exemplo de teste com mock**:
```python
def test_process_command():
    # Mock dos ports
    mock_voice = Mock(spec=VoiceProvider)
    mock_action = Mock(spec=ActionProvider)
    
    # Serviços reais de domínio (sem hardware)
    interpreter = CommandInterpreter(wake_word="test")
    processor = IntentProcessor()
    
    # Service com dependências injetadas
    service = AssistantService(
        voice_provider=mock_voice,
        action_provider=mock_action,
        # ...
    )
    
    # Teste sem hardware real
    response = service.process_command("escreva hello")
    assert response.success
    mock_action.type_text.assert_called_with("hello")
```

## Cenários de Deployment

### 1. Edge Local (Desenvolvimento)
```bash
# Opção A: Instala todas as dependências via requirements.txt principal
pip install -r requirements.txt

# Opção B: Usa requirements modulares
pip install -r requirements/edge.txt

# Executa com hardware local
python main.py
```

### 2. Cloud Headless (API Server)
```bash
# Instala apenas core (sem dependências de hardware)
pip install -r requirements/core.txt

# Executa servidor API sem hardware
python serve.py

# Acesse em http://localhost:8000/docs
```

### 3. Híbrido (Múltiplos Edges + Cloud Central)
```
Cloud: Processa intenções, toma decisões
  ↓ ↑ (WebSocket/gRPC)
Edge 1, 2, 3...: Executam comandos localmente
```

## Extensibilidade

### Adicionar Novo Comando
1. Adicionar novo `CommandType` em `domain/models/command.py`
2. Atualizar `CommandInterpreter` para reconhecer o padrão
3. Implementar execução em `AssistantService`
4. **Não precisa mexer em adapters** se usar Ports existentes

### Adicionar Novo Adapter
1. Criar novo adapter em `app/adapters/edge/` ou `infrastructure/`
2. Implementar interface do Port correspondente
3. Registrar no Container
4. **Não precisa mexer no domínio ou aplicação**

### Adicionar Nova Interface (Port)
1. Criar nova interface em `app/application/ports/`
2. Implementar adapter concreto
3. Injetar no serviço de aplicação necessário

## Docker e Cloud

### Dockerfile Multi-Stage
- Stage 1: Build dependencies
- Stage 2: Core (cloud-ready)
- Stage 3: Edge (com hardware)

### Docker Compose
- Variáveis de ambiente para configuração
- Volumes para dados persistentes
- Rede para comunicação entre serviços

## Integração com Airflow

Os DAGs do Airflow podem:
- Usar apenas o domínio e aplicação (core)
- Não dependem de hardware
- Podem rodar em workers distribuídos

## Recursos Implementados

✅ **Concluído:**
1. **FastAPI Integration**: API REST funcional com autenticação (ver [API_README.md](API_README.md))
2. **LLM Integration**: Integração com Gemini AI para interpretação de comandos (ver [LLM_INTEGRATION.md](LLM_INTEGRATION.md))
3. **Database Integration**: SQLModel com suporte a PostgreSQL e SQLite
4. **Distributed Mode**: Sistema com worker local e API na cloud (ver [DISTRIBUTED_MODE.md](DISTRIBUTED_MODE.md))
5. **Modular Requirements**: Arquivos separados para diferentes cenários de deployment

## Próximos Passos

1. **WebSocket Support**: Comunicação real-time para múltiplos edges
2. **Cloud Adapters**: Implementar adapters para serviços cloud (AWS Polly, Google Cloud TTS)
3. **Multi-device Orchestration**: Protocolo avançado de comunicação Edge ↔ Cloud
4. **Event Sourcing**: Sistema completo de histórico e replay de eventos
5. **Monitoring & Metrics**: Integração com Prometheus/Grafana

## Referências

- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- [Ports and Adapters Pattern](https://herbertograca.com/2017/09/14/ports-adapters-architecture/)
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
