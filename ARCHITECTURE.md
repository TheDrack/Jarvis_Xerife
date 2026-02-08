# Arquitetura Hexagonal do Jarvis Assistant

## Visão Geral: Orquestrador de Dispositivos Distribuído

**Jarvis não é apenas uma API** - é um **cérebro na nuvem** que coordena "Soldados" (dispositivos locais) através de um sistema inteligente de orquestração baseada em capacidades e consciência espacial.

### O Conceito

Imagine que você está em casa e diz "tire uma selfie" - Jarvis usa a câmera do seu celular.  
Mas se você diz "ligue a TV da sala", ele roteia para o Raspberry Pi conectado ao IR blaster.  
E quando você viaja e pede "toque música", ele entende que deve usar o celular atual, não o PC em casa a 300km de distância.

**Como funciona?**
1. **Cérebro Central (Cloud)**: Jarvis processa intenções e decide ONDE executar cada comando
2. **Soldados (Devices)**: Dispositivos locais registram suas capacidades e aguardam ordens
3. **Roteamento Inteligente**: Sistema hierárquico considera dispositivo, rede e GPS para escolher o executor ideal

Este projeto segue o padrão de **Arquitetura Hexagonal** (também conhecida como Ports and Adapters), criado por Alistair Cockburn, adaptado para suportar orquestração distribuída. A arquitetura separa claramente a lógica de negócio (domínio) das preocupações de infraestrutura e hardware.

## Por Que Arquitetura Hexagonal?

### Motivação

1. **Cloud Readiness**: Permitir que o núcleo da aplicação rode em ambientes headless (sem display, áudio ou entrada de hardware) na nuvem
2. **Orquestração Distribuída**: Coordenar múltiplos dispositivos (mobile, desktop, IoT) através de um cérebro central
3. **Separação de Responsabilidades**: Isolar a lógica de decisão e interpretação de comandos das dependências de hardware
4. **Testabilidade**: Facilitar testes sem necessidade de hardware real (mocks)
5. **Escalabilidade**: Preparar para múltiplos dispositivos clientes (Edge) comunicando com um cérebro central (Cloud)
6. **Roteamento Inteligente**: Escolher o dispositivo ideal baseado em capacidades, localização geográfica e proximidade de rede
7. **Flexibilidade**: Trocar implementações de infraestrutura sem alterar a lógica de negócio

### Conceito: Cloud (Cérebro) vs Edge (Soldados)

```
┌──────────────────────────────────────────────────────────────────┐
│                    CLOUD (Cérebro / Orquestrador)                │
│  - Lógica de decisão e interpretação                             │
│  - Processamento de intenções                                    │
│  - Regras de negócio                                             │
│  - Orquestração de comandos                                      │
│  - ROTEAMENTO INTELIGENTE por capacidades e localização          │
│  - Registro de dispositivos e capabilities                       │
│  - Totalmente independente de hardware                           │
└──────────────────────────────────────────────────────────────────┘
                              ↕
                    DeviceService (Routing)
                              ↕
┌──────────────────────────────────────────────────────────────────┐
│                    EDGE (Soldados / Executores)                  │
│  - Reconhecimento de voz local                                   │
│  - Síntese de fala (TTS)                                         │
│  - Automação de interface (PyAutoGUI)                            │
│  - Controle de teclado/mouse                                     │
│  - Controle de dispositivos IoT (IR, câmera, sensores)           │
│  - Enviam capacidades para o Cloud                               │
│  - Executam comandos recebidos                                   │
│  - Depende de hardware físico                                    │
└──────────────────────────────────────────────────────────────────┘
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

## Fluxo de Execução: Orquestração Distribuída

### Fluxo Completo com Roteamento de Dispositivos

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. User speaks → VoiceAdapter.listen() (local ou via API)          │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Text → CommandInterpreter.interpret() → Intent                  │
│    - CommandInterpreter (rule-based) OU                             │
│    - LLMCommandAdapter (Gemini AI com consciência espacial)        │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 3. Intent → IntentProcessor.validate() + create_command()          │
│    - Valida parâmetros e cria Command                               │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 4. Command → AssistantService._execute_command()                   │
│    ┌─────────────────────────────────────────────────────────────┐ │
│    │ 4a. Determina capability requerida (ex: "camera", "type")  │ │
│    └─────────────────────────────────────────────────────────────┘ │
│                          ↓                                          │
│    ┌─────────────────────────────────────────────────────────────┐ │
│    │ 4b. DeviceService.find_device_by_capability()              │ │
│    │     - Busca dispositivo com a capability                   │ │
│    │     - Aplica HIERARQUIA DE PROXIMIDADE (ver abaixo)        │ │
│    └─────────────────────────────────────────────────────────────┘ │
│                          ↓                                          │
│    ┌─────────────────────────────────────────────────────────────┐ │
│    │ 4c. DeviceService.validate_device_routing()                │ │
│    │     - Verifica conflitos de rede/localização               │ │
│    │     - Pede confirmação se necessário                        │ │
│    └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 5. Execution → Roteia para dispositivo adequado                    │
│    - Se local: ActionProvider / WebProvider (adapters locais)      │
│    - Se remoto: Envia para dispositivo via target_device_id        │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 6. Response → VoiceProvider.speak() → User hears feedback          │
└─────────────────────────────────────────────────────────────────────┘
```

### Hierarquia de Proximidade para Roteamento

O `DeviceService` usa uma hierarquia inteligente de 3 níveis para escolher o dispositivo ideal:

```
Priority Score (100-10):

┌──────────────────────────────────────────────────────┐
│ 1️⃣ MESMO DISPOSITIVO (Priority 100)                 │
│   - Se source_device_id == target_device_id          │
│   - Exemplo: Celular pede "tire selfie" → próprio   │
│            celular com capability "camera"           │
└──────────────────────────────────────────────────────┘
                    ↓ (se não disponível)
┌──────────────────────────────────────────────────────┐
│ 2️⃣ MESMA REDE/IP (Priority 80)                      │
│   - Compara network_id (SSID ou IP público)         │
│   - Exemplo: Celular em casa pede "ligue TV" →      │
│            Raspberry Pi na mesma WiFi                │
└──────────────────────────────────────────────────────┘
                    ↓ (se não disponível)
┌──────────────────────────────────────────────────────┐
│ 3️⃣ GPS PRÓXIMO (Priority 70 / 40 / 10)              │
│   - Calcula distância usando Haversine formula      │
│   - <1km: Priority 70 (muito próximo)               │
│   - <50km: Priority 40 (mesma cidade)               │
│   - >50km: Priority 10 + pede confirmação           │
│   - Exemplo: Dois celulares a 200m → escolhe o      │
│            mais próximo geograficamente              │
└──────────────────────────────────────────────────────┘
```

**Algoritmo de Distância GPS:**
- Usa fórmula de Haversine para calcular distância entre coordenadas
- Considera raio da Terra (6371 km)
- Implementado em `DeviceService.calculate_distance(lat1, lon1, lat2, lon2)`

### Validação de Conflitos

Antes de executar em dispositivo remoto, o sistema verifica:

```python
validation = DeviceService.validate_device_routing(
    source_device_id=source_device_id,
    target_device_id=target_device_id,
)
```

**Cenários que requerem confirmação:**
1. **Distância >50km**: "O dispositivo está a 120km. Executar remotamente?"
2. **Rede móvel → WiFi doméstico**: "Você está no 4G mas o dispositivo está na rede doméstica. Continuar?"
3. **Redes diferentes**: "Você está em rede diferente. Continuar?"
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

## Guia de Integração de Dispositivos

### Registrando um Novo Dispositivo ("Soldado")

Dispositivos podem se registrar no Jarvis e anunciar suas capacidades para participar da orquestração distribuída.

#### Endpoint: `POST /v1/devices/register`

**Autenticação:** Requer token Bearer JWT (use `/token` para obter)

**Request Body:**
```json
{
  "name": "Celular-Samsung-Galaxy",
  "type": "mobile",
  "capabilities": [
    {
      "name": "camera",
      "description": "Câmera frontal e traseira 12MP",
      "metadata": {
        "front_camera": true,
        "back_camera": true,
        "resolution": "12MP"
      }
    },
    {
      "name": "type_text",
      "description": "Digitação via teclado virtual",
      "metadata": {
        "keyboard_type": "virtual"
      }
    },
    {
      "name": "gps",
      "description": "GPS de alta precisão",
      "metadata": {
        "accuracy": "high"
      }
    }
  ],
  "network_id": "WiFi-Casa-5G",
  "network_type": "wifi",
  "lat": -23.5505,
  "lon": -46.6333,
  "last_ip": "192.168.1.100"
}
```

**Response:**
```json
{
  "success": true,
  "device_id": 42,
  "message": "Device 'Celular-Samsung-Galaxy' registered successfully with ID 42"
}
```

#### Tipos de Dispositivos

- `mobile`: Smartphones e tablets
- `desktop`: PCs e laptops
- `iot`: Raspberry Pi, Arduino, ESP32, etc.
- `cloud`: Instâncias cloud ou servidores

#### Capabilities Comuns

| Capability | Descrição | Uso Típico |
|------------|-----------|------------|
| `camera` | Acesso à câmera | Selfies, fotos, reconhecimento visual |
| `type_text` | Digitação de texto | Automação de formulários |
| `press_key` | Pressionar teclas | Atalhos de teclado |
| `open_browser` | Abrir navegador | Navegação web |
| `ir_control` | Controle infravermelho | TVs, ar-condicionado, dispositivos IR |
| `audio_playback` | Reprodução de áudio | Música, podcasts, notificações |
| `home_automation` | Controle de casa inteligente | Luzes, fechaduras, termostatos |

#### Mantendo Dispositivo Ativo (Heartbeat)

Para indicar que o dispositivo está online, envie heartbeats periódicos:

**Endpoint:** `PUT /v1/devices/{device_id}/heartbeat`

```json
{
  "status": "online",
  "lat": -23.5505,
  "lon": -46.6333,
  "last_ip": "192.168.1.100"
}
```

**Recomendação:** Envie heartbeat a cada 30-60 segundos.

### Exemplos de Payloads com target_device_id

Quando Jarvis roteia um comando para um dispositivo específico, a resposta inclui o `target_device_id`:

#### Exemplo 1: Comando Local (Mesmo Dispositivo)
```json
// Request
POST /v1/execute
{
  "command": "tire uma selfie",
  "metadata": {
    "source_device_id": 42,
    "network_id": "WiFi-Casa-5G"
  }
}

// Response (dispositivo tem capability "camera")
{
  "success": true,
  "message": "Command routed to device: Celular-Samsung-Galaxy",
  "data": {
    "target_device_id": 42,
    "target_device_name": "Celular-Samsung-Galaxy",
    "target_device_network": "WiFi-Casa-5G",
    "required_capability": "camera",
    "requires_device_execution": true
  }
}
```

#### Exemplo 2: Comando Remoto (Mesma Rede)
```json
// Request (do celular, pedindo ação no PC)
POST /v1/execute
{
  "command": "abra o navegador",
  "metadata": {
    "source_device_id": 42,
    "network_id": "WiFi-Casa-5G"
  }
}

// Response (PC na mesma rede tem capability "open_browser")
{
  "success": true,
  "message": "Command routed to device: PC-Escritorio",
  "data": {
    "target_device_id": 15,
    "target_device_name": "PC-Escritorio",
    "target_device_network": "WiFi-Casa-5G",
    "required_capability": "open_browser",
    "requires_device_execution": true
  }
}
```

#### Exemplo 3: Confirmação Necessária (Dispositivo Distante)
```json
// Request (de São Paulo, tentando controlar dispositivo em Brasília)
POST /v1/execute
{
  "command": "ligue a TV",
  "metadata": {
    "source_device_id": 42,
    "network_id": "4G-TIM"
  }
}

// Response (requer confirmação - distância >50km)
{
  "success": false,
  "message": "O dispositivo está a 1015.3km de distância. Deseja executar a ação remotamente?",
  "data": {
    "requires_confirmation": true,
    "target_device_id": 8,
    "target_device_name": "RaspberryPi-Sala",
    "source_device_id": 42,
    "validation": {
      "requires_confirmation": true,
      "reason": "O dispositivo de destino (RaspberryPi-Sala) está a 1015.3km de distância. Deseja executar a ação remotamente?",
      "distance": 1015.3
    }
  },
  "error": "CONFIRMATION_REQUIRED"
}
```

## Personalidade do Xerife: Diretrizes de Consciência Espacial

O "Xerife" é a personalidade padrão do Jarvis, implementada no `GeminiAdapter` através do `AgentService.get_system_instruction()`. Esta personalidade foi projetada especificamente para orquestração distribuída com **consciência espacial**.

### Conceito: Orquestrador vs Assistente Tradicional

Enquanto assistentes tradicionais executam comandos localmente, o **Xerife** age como um **coordenador de ambiente** que:
- Gerencia múltiplos dispositivos distribuídos geograficamente
- Toma decisões conscientes sobre ONDE executar cada comando
- Entende o contexto físico e de rede do usuário
- Prioriza dispositivos baseado em proximidade geográfica e de rede

### Regras de Consciência Espacial

Estas diretrizes estão codificadas no sistema de prompts do Gemini AI:

#### 1. **Inteligência de Localização (Regra de Ouro)**

```
- Você TEM ACESSO à localização GPS (latitude/longitude) de todos os dispositivos
- SEMPRE considera TANTO a rede quanto a distância geográfica ao escolher dispositivos
- Para ações PESSOAIS (selfie, tocar música): use dispositivo de origem
- Para ações de AMBIENTE (ligar luz, TV): use dispositivo na mesma localização física
- Se dispositivo alvo estiver a >50km: SEMPRE peça confirmação
```

**Exemplos Práticos:**
- ✅ Usuário em São Paulo pede "tire selfie" → Usa câmera do celular atual (não PC em outro estado)
- ✅ Usuário em casa pede "ligue TV" → Usa dispositivo IoT da sala (mesma rede WiFi)
- ✅ Usuário viajando pede "toque música" → Toca no celular atual, NÃO no PC de casa

#### 2. **Hierarquia de Priorização**

```
Priority Score (100-10):
1️⃣ Dispositivo de origem (se tiver a capability)
2️⃣ Dispositivos na mesma rede (mesmo SSID ou IP público)
3️⃣ Dispositivos muito próximos (<1km de distância)
4️⃣ Dispositivos na mesma cidade (<50km)
5️⃣ Outros dispositivos online (SEMPRE pedir confirmação)
```

#### 3. **Detecção de Conflitos**

O Xerife identifica automaticamente situações ambíguas:

```
- Usuário em 4G/5G mas dispositivo alvo em WiFi doméstico → Perguntar
- Dispositivo alvo em cidade diferente (>50km) → Perguntar: "Dispositivo a Xkm. Executar remotamente?"
- Redes diferentes mas localização desconhecida → Perguntar: "Dispositivos em redes diferentes. Continuar?"
```

#### 4. **Características de Personalidade**

```
- CONCISO e EFICIENTE (sem explicações longas)
- DIRETO ao ponto
- Foca em AÇÕES, não em teoria
- Profissional mas amigável
- Sempre considera contexto físico do usuário
```

### Implementação Técnica

A personalidade está implementada em:

**Arquivo:** `app/domain/services/agent_service.py`  
**Método:** `AgentService.get_system_instruction()`

```python
@staticmethod
def get_system_instruction() -> str:
    return """Você é o Xerife, um Orquestrador de Ambiente...
    
    INTELIGÊNCIA DE LOCALIZAÇÃO (REGRA DE OURO):
    - Você TEM ACESSO à localização GPS de todos os dispositivos
    - SEMPRE considera TANTO a rede quanto a distância geográfica
    ...
    
    Priorização de Dispositivos:
    1. Dispositivo de origem (se tiver a capacidade)
    2. Dispositivos na mesma rede
    3. Dispositivos muito próximos (<1km)
    ...
    """
```

### Customizando a Personalidade

Para criar variações da personalidade (ex: "Ultron agressivo", "Friday educada"):

1. **Modifique** `get_system_instruction()` em `agent_service.py`
2. **Mantenha** as regras de consciência espacial (críticas para orquestração)
3. **Ajuste** tom, formalidade e estilo de resposta
4. **Teste** com comandos que envolvem múltiplos dispositivos

**Exemplo - Personalidade Mais Casual:**
```python
return """Você é o Xerife, tipo um DJ de dispositivos! 🎧
Seu trampo é coordenar a galera (celulares, PCs, IoT)...

CONSCIÊNCIA ESPACIAL (não pula essa parte!):
- Você saca onde cada dispositivo tá (GPS e rede)
- Sempre manda o comando pro dispositivo mais perto
[... resto das regras de localização ...]
```

### Testando Consciência Espacial

Para validar o comportamento da personalidade:

```python
# Cenário 1: Comando pessoal (deve usar dispositivo de origem)
response = assistant_service.process_command(
    "tire uma selfie",
    request_metadata={
        "source_device_id": 42,
        "network_id": "WiFi-Casa"
    }
)
assert response.data["target_device_id"] == 42  # Mesmo dispositivo

# Cenário 2: Comando de ambiente (deve usar dispositivo na mesma rede)
response = assistant_service.process_command(
    "ligue a TV",
    request_metadata={
        "source_device_id": 42,  # Celular
        "network_id": "WiFi-Casa"
    }
)
assert response.data["target_device_network"] == "WiFi-Casa"  # Mesma rede

# Cenário 3: Dispositivo distante (deve pedir confirmação)
response = assistant_service.process_command(
    "abra o navegador",
    request_metadata={
        "source_device_id": 42,  # Em São Paulo
        "network_id": "4G-TIM"
    }
)
# Se alvo está a >50km:
assert response.error == "CONFIRMATION_REQUIRED"
assert "km" in response.message
```

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
1. **Orquestração Distribuída**: Sistema completo de roteamento de dispositivos com consciência espacial
2. **Device Registry**: Registro e gerenciamento de dispositivos com capabilities via API REST
3. **Intelligent Routing**: Hierarquia de proximidade (Mesmo Dispositivo → Mesma Rede → GPS Próximo)
4. **Spatial Awareness**: Personalidade "Xerife" com regras de consciência geográfica integradas ao Gemini AI
5. **Conflict Detection**: Validação automática de rotas com confirmação para dispositivos distantes (>50km)
6. **FastAPI Integration**: API REST funcional com autenticação e endpoints de device management (ver [API_README.md](API_README.md))
7. **LLM Integration**: Integração com Gemini AI para interpretação de comandos com consciência espacial (ver [LLM_INTEGRATION.md](LLM_INTEGRATION.md))
8. **Database Integration**: SQLModel com suporte a PostgreSQL e SQLite para device registry e history
9. **Distributed Mode**: Sistema com worker local e API na cloud (ver [DISTRIBUTED_MODE.md](DISTRIBUTED_MODE.md))
10. **Modular Requirements**: Arquivos separados para diferentes cenários de deployment

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
