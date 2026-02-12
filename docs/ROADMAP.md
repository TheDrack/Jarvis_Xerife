# Roadmap do Projeto Jarvis

## Visão de Longo Prazo

Jarvis é uma plataforma de orquestração de automação pessoal distribuída que prioriza execução efêmera, agnóstica a dispositivo, e baseada em capacidades. Este roadmap reflete nossa jornada de um assistente de voz para um ecossistema completo de dispositivos inteligentes.

---

## 🚀 **AGORA**: Estabilização do Worker Playwright e Execução Efêmera

**Status**: Em Andamento (Q1 2026)

### Objetivos Principais:
1. **Estabilizar TaskRunner com Venvs Efêmeros**
   - ✅ Criação e destruição automática de ambientes virtuais
   - ✅ Cache inteligente de dependências
   - 🔄 Graceful failure em instalações de pip
   - 🔄 Logs estruturados com mission_id, device_id, session_id

2. **Fortalecer Playwright Integration**
   - ✅ Contexto persistente via CDP
   - ✅ Browser manager com headless mode
   - 🔄 Extension manager para automações complexas
   - ✅ Testes de integração com Playwright

3. **Garantir Resiliência**
   - 🔄 Timeout handling robusto
   - 🔄 Error recovery automático
   - 🔄 Logs estruturados para debugging
   - 📋 Monitoramento de recursos (CPU, memória, disk)

4. **Documentação e Arquitetura**
   - ✅ Hexagonal Architecture bem documentada
   - ✅ ADRs (Architecture Decision Records)
   - 🔄 Testes de contrato para geofencing
   - 📋 Guias de contribuição atualizados

### Métricas de Sucesso:
- [ ] 100% das missões com logs estruturados
- [ ] 0 processos pendurados em timeout
- [ ] Cache de deps reduz tempo de instalação em >80%
- [ ] 95%+ de cobertura de testes no TaskRunner

---

## 📅 **PRÓXIMO**: Interface de Comando de Voz e Dashboard de Monitoramento

**Previsão**: Q2-Q3 2026

### 1. Interface de Comando de Voz Aprimorada

**Por quê?** Atualmente, Jarvis depende de reconhecimento de voz básico. Queremos levar isso ao próximo nível com:

- **Wake Word Detection Local**
  - Usar Porcupine ou similar para detecção offline de "Jarvis", "Friday", etc.
  - Reduzir latência: apenas enviar áudio após wake word

- **Streaming Voice Recognition**
  - Suporte a streaming de áudio em tempo real
  - Feedback visual enquanto transcreve
  - Correção de comandos antes de executar

- **Voice Feedback Melhorado**
  - TTS com vozes naturais (Google Cloud TTS ou Elevenlabs)
  - Respostas contextuais baseadas em histórico
  - Suporte a múltiplos idiomas (pt-BR, en-US, es-ES)

- **Conversação Contextual**
  - Manter contexto de conversas anteriores
  - Perguntas de follow-up ("e agora?", "faz de novo")
  - Confirmações naturais para ações destrutivas

**Entregáveis**:
- [ ] Wake word detection com <100ms latência
- [ ] Streaming STT com Google Speech API
- [ ] TTS com vozes naturais
- [ ] Context-aware conversation manager

### 2. Dashboard de Monitoramento de Dispositivos

**Por quê?** Com múltiplos workers distribuídos, precisamos visibilidade:

- **Visão Geral do Sistema**
  - Mapa de todos os dispositivos conectados
  - Status em tempo real (online, busy, offline)
  - Últimas execuções e saúde de cada worker

- **Métricas e Observabilidade**
  - Tempo médio de execução por tipo de missão
  - Taxa de sucesso/falha por dispositivo
  - Uso de recursos (CPU, RAM, storage)
  - Alertas quando dispositivos ficam offline

- **Histórico e Auditoria**
  - Linha do tempo de todas as execuções
  - Logs centralizados e pesquisáveis
  - Reprodução de execuções anteriores
  - Exportação de dados para análise

- **Controle Remoto**
  - Pausar/retomar execução de workers
  - Force-kill de processos pendurados
  - Deploy de código para workers específicos

**Stack Tecnológico Proposta**:
- Frontend: React + Tailwind CSS
- Backend: FastAPI (já existente) + WebSockets
- Visualização: Chart.js ou Recharts
- Real-time: Server-Sent Events ou WebSockets

**Entregáveis**:
- [ ] Dashboard web acessível em /dashboard
- [ ] WebSocket para updates em tempo real
- [ ] Visualização de mapa de dispositivos
- [ ] Logs centralizados e pesquisáveis

---

## 🤔 **TALVEZ**: Suporte a Execução de Modelos de IA Locais (TinyLLM)

**Previsão**: Q4 2026 ou posterior

### Visão

Permitir que workers executem modelos de linguagem pequenos localmente para:
1. Interpretação de comandos offline (sem internet)
2. Processamento de dados sensíveis sem sair do dispositivo
3. Reduzir custos de API de LLMs

### Desafios Identificados

1. **Recursos Limitados em Edge Devices**
   - Raspberry Pi 4 tem apenas 4-8GB RAM
   - Modelos LLM pequenos (TinyLLaMA, Phi-2) precisam 2-4GB
   - Solução: Quantização INT4/INT8 para reduzir uso de memória

2. **Latência de Inferência**
   - CPUs lentas em edge devices (~10-30s por resposta)
   - Solução: Cache de respostas comuns, fallback para cloud

3. **Gerenciamento de Modelos**
   - Download e atualização de modelos (1-5GB)
   - Solução: Download incremental, versionamento

### Candidatos a Modelos

- **TinyLLaMA** (1.1B parâmetros, ~2GB): Boa performance geral
- **Phi-2** (2.7B parâmetros, ~5GB): Microsoft, foco em reasoning
- **Gemma-2B** (Google): Otimizado para tarefas específicas
- **ONNX Runtime**: Para inferência otimizada em CPU

### Critérios de Decisão

Implementaremos TinyLLM se:
- [ ] 30%+ dos usuários têm dispositivos edge com >4GB RAM
- [ ] Casos de uso sem internet são comuns
- [ ] Custos de API de LLM excedem $50/mês por usuário
- [ ] Comunidade pede explicitamente

**Não implementaremos se**:
- Complexidade supera benefícios
- Modelos cloud continuam baratos e rápidos
- Edge devices não têm recursos suficientes

---

## 🗺️ Visão de Futuro (2027+)

### Possibilidades em Exploração:

1. **Automação Preditiva**
   - Aprender rotinas e sugerir automações
   - "Às 7h você sempre abre emails, quer que eu faça isso automaticamente?"

2. **Integração com Home Assistant**
   - Jarvis como orquestrador de smart home
   - Controlar luzes, termostato, câmeras

3. **Mobile App Nativo**
   - App iOS/Android para controle fácil
   - Notificações push de execuções
   - Controle por voz no celular

4. **Marketplace de Extensões**
   - Comunidade pode criar e compartilhar automações
   - "Instalar extensão de integração com Spotify"

5. **Multi-tenant Cloud**
   - Oferecer Jarvis como SaaS
   - Usuários sem conhecimento técnico podem usar

---

## Princípios que Guiam o Roadmap

1. **Automação com Propósito**: Cada feature deve resolver um problema real
2. **Execução Efêmera Primeiro**: Priorizar soluções stateless e limpas
3. **Privacidade por Design**: Dados sensíveis nunca saem do controle do usuário
4. **Simplicidade sobre Features**: Melhor fazer poucas coisas excepcionalmente bem

---

## Como Contribuir

Quer influenciar o roadmap? 
1. Abra uma issue descrevendo seu caso de uso
2. Vote em features existentes com 👍
3. Contribua com PRs para itens marcados como "good first issue"

---

**Última Atualização**: 2026-02-08  
**Mantido por**: Equipe Jarvis  
**Feedback**: Abra uma issue ou discussion no GitHub
