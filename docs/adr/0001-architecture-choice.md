# ADR 0001: Escolhas Arquiteturais - Playwright e Workers Efêmeros

**Status**: Aceito

**Data**: 2026-02-08

**Contexto**: Como arquiteto sênior focado em sistemas distribuídos

**Decisores**: Equipe de Engenharia Jarvis

---

## Contexto e Problema

O projeto Jarvis precisa orquestrar automações web e executar código Python arbitrário em múltiplos dispositivos distribuídos (Workers). Precisamos fazer escolhas técnicas que priorizem:

1. **Escalabilidade**: Suportar múltiplos workers sem overhead excessivo
2. **Isolamento**: Cada execução deve ser isolada e limpa
3. **Persistência de Contexto**: Manter estado de browser entre operações relacionadas
4. **Limpeza de Ambiente**: Evitar poluição de dependências entre execuções

## Opções Consideradas

### Para Automação Web:
- **Opção A**: Selenium WebDriver
- **Opção B**: Playwright
- **Opção C**: Puppeteer (somente Node.js)

### Para Execução de Workers:
- **Opção 1**: Instalação global de dependências
- **Opção 2**: Containers Docker por execução
- **Opção 3**: Venv efêmero com cache compartilhado

---

## Decisão 1: Playwright sobre Selenium

### ✅ Escolha: Playwright

**Justificativa Técnica:**

1. **Contexto Persistente via CDP (Chrome DevTools Protocol)**
   - Playwright oferece controle de contexto de navegação superior
   - Mantém cookies, localStorage, sessionStorage entre execuções
   - Permite criar múltiplos contextos isolados em uma única instância de browser
   - **Crítico para Jarvis**: Permite autenticar uma vez e reutilizar sessão em múltiplas operações

2. **Performance e Recursos**
   - Menor overhead de memória em execuções longas
   - Suporte nativo a headless mode mais eficiente
   - Auto-waiting: espera automaticamente por elementos estarem prontos
   - Network interception e mocking integrados

3. **API Moderna e Pythonica**
   - Async/await nativo
   - Seletores mais robustos (CSS, XPath, text, role-based)
   - Melhor tratamento de erros e timeouts

4. **Multi-browser sem drivers externos**
   - Chromium, Firefox, WebKit inclusos
   - Sem necessidade de gerenciar chromedriver, geckodriver, etc.
   - Instalação simplificada: `playwright install`

**Comparação com Selenium:**

| Aspecto | Playwright | Selenium |
|---------|-----------|----------|
| Contexto Persistente | ✅ Nativo via CDP | ⚠️ Requer workarounds |
| Gerenciamento de Drivers | ✅ Automático | ❌ Manual (chromedriver) |
| Auto-waiting | ✅ Sim | ❌ Não (precisa WebDriverWait) |
| Network Interception | ✅ Nativo | ❌ Limitado |
| Footprint de Memória | ✅ Menor | ⚠️ Maior |
| Maturidade | ⚠️ Mais recente | ✅ Mais antigo |

**Desvantagens Aceitas:**
- Playwright é mais recente (menos histórico de produção)
- Comunidade menor que Selenium
- **Mitigação**: Playwright é mantido pela Microsoft, tem crescimento rápido, e a API moderna compensa

---

## Decisão 2: Workers com Venv Efêmero

### ✅ Escolha: Virtual Environments Efêmeros com Cache Compartilhado

**Justificativa Técnica:**

### Arquitetura da Solução:

```
Worker Request
    ↓
Criar Venv Temporário (/tmp/mission_{id}/)
    ↓
Instalar deps do cache compartilhado (se disponível)
    ↓
Executar código em ambiente isolado
    ↓
Capturar stdout/stderr
    ↓
Destruir Venv (se não keep_alive)
```

**Vantagens:**

1. **Isolamento Total**
   - Cada missão tem seu próprio venv Python
   - Sem conflitos de versões de bibliotecas
   - Falha em uma execução não contamina outras

2. **Escalabilidade**
   - Venvs são leves (~10-50MB vs 500MB+ de container Docker)
   - Criação rápida (1-3s vs 10-30s de container)
   - Permite executar 10-20 missões simultâneas em hardware modesto

3. **Limpeza Automática**
   - Venvs temporários são removidos após execução
   - Sistema sempre limpo, sem acúmulo de "lixo"
   - Opção `keep_alive` para casos que precisam persistência

4. **Cache Inteligente**
   - Bibliotecas comuns (requests, pandas, etc.) ficam em cache
   - Primeira instalação: ~30s, próximas: ~3s
   - Reduz uso de rede e tempo de inicialização

**Comparação com Alternativas:**

| Aspecto | Venv Efêmero | Docker Container | Global Install |
|---------|--------------|------------------|----------------|
| Isolamento | ✅ Excelente | ✅ Perfeito | ❌ Nenhum |
| Tempo de Criação | ✅ 1-3s | ⚠️ 10-30s | ✅ 0s |
| Footprint | ✅ 10-50MB | ⚠️ 500MB+ | ✅ 0MB |
| Limpeza | ✅ Automática | ✅ Automática | ❌ Manual |
| Complexidade | ✅ Baixa | ⚠️ Média-Alta | ✅ Baixíssima |
| Portabilidade | ✅ Linux/Win/Mac | ⚠️ Requer Docker | ✅ Todas |

**Exemplo de Implementação:**

```python
class TaskRunner:
    def execute_mission(self, mission: Mission) -> MissionResult:
        # Criar venv temporário
        venv_path = Path(f"/tmp/mission_{mission.id}/venv")
        self._create_venv(venv_path)
        
        # Instalar deps do cache
        for dep in mission.requirements:
            self._install_with_cache(venv_path, dep)
        
        # Executar com timeout
        result = self._execute_in_venv(venv_path, mission.code)
        
        # Cleanup (se não keep_alive)
        if not mission.keep_alive:
            shutil.rmtree(venv_path)
        
        return result
```

**Desvantagens Aceitas:**
- Não há isolamento de sistema operacional (vs Docker)
- Processos maliciosos podem afetar o host
- **Mitigação**: Jarvis é para automação pessoal confiável, não execução de código arbitrário de terceiros

---

## Consequências

### Positivas:

1. **Manutenibilidade**: Código mais limpo com Playwright, menos workarounds
2. **Escalabilidade**: Venvs efêmeros permitem mais execuções simultâneas
3. **Resiliência**: Falhas isoladas, sem contaminação entre execuções
4. **Velocidade de Iteração**: Desenvolvedores podem testar localmente sem Docker

### Negativas (Mitigadas):

1. **Learning Curve**: Equipe precisa aprender Playwright (vs Selenium familiar)
   - **Mitigação**: API mais simples acelera aprendizado
   
2. **Overhead de Criação de Venv**: 1-3s por execução
   - **Mitigação**: Cache de bibliotecas + opção keep_alive para workflows longos

### Neutras:

1. **Dependência de Python**: Precisa Python 3.8+ no worker
2. **Gestão de Cache**: Precisa política de limpeza periódica do cache

---

## Riscos e Monitoramento

### Riscos Identificados:

1. **Cache Crescendo Indefinidamente**
   - **Monitoramento**: Alert se cache > 5GB
   - **Mitigação**: Cleanup de libs não usadas há 30+ dias

2. **Venvs "Órfãos"** (não removidos por crash)
   - **Monitoramento**: Cronjob para limpar /tmp/mission_* > 1 dia
   - **Mitigação**: Watchdog que limpa venvs antigos

3. **Playwright Browsers Desatualizados**
   - **Monitoramento**: Verificar versão semanal
   - **Mitigação**: CI job que executa `playwright install`

---

## Referências

- [Playwright Documentation](https://playwright.dev/python/)
- [Python venv Official Docs](https://docs.python.org/3/library/venv.html)
- [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/)
- [Hexagonal Architecture Pattern](https://alistair.cockburn.us/hexagonal-architecture/)

---

## Revisões Futuras

Esta ADR deve ser revisada se:
- Selenium adicionar suporte equivalente a CDP
- Precisarmos executar código não-confiável (terceiros)
- Workers precisarem rodar em ambientes muito restritos (<1GB RAM)

**Próxima Revisão Programada**: Q3 2026

---

*Assinado pela equipe de engenharia Jarvis com o princípio de "Automação com Propósito"*
