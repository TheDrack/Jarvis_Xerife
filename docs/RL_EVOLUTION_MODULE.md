# Módulo de Reinforcement Learning (RL-Evolution) 🤖

## Visão Geral

O módulo RL-Evolution implementa um sistema de Aprendizado por Reforço para o JARVIS, permitindo que o assistente aprenda com suas ações passadas e melhore continuamente sua eficiência.

## Funcionalidades

### 1. Sistema de Recompensas (Reward System)

- **Tabela de Banco de Dados**: `evolution_rewards` no Supabase/PostgreSQL
- **Tipos de Ações Rastreadas**:
  - ✅ `pytest_pass`: Testes passaram (+10 pontos base)
  - ❌ `pytest_fail`: Testes falharam (-5 pontos base)
  - ✅ `deploy_success`: Deploy bem-sucedido (+50 pontos)
  - ❌ `deploy_fail`: Deploy falhou (-25 pontos)
  - 🔄 `rollback`: Rollback necessário (-30 pontos)
  - 📈 `roadmap_progress`: Progresso no roadmap (+20 pontos por %)
  - 🎯 `capability_complete`: Capacidade completa (+15 pontos)
  - ⚡ `capability_partial`: Capacidade parcial (+5 pontos)

### 2. Lógica de Rotina (Routine Logic)

O serviço `EvolutionLoopService` pode ser executado:

- Após cada execução de testes (pytest)
- Após cada deployment (sucesso ou falha)
- Quando o progresso do roadmap aumenta
- Em intervalos de tempo definidos
- No login do HUD

### 3. Feedback Loop

O sistema cria um ciclo de feedback:

1. **Ação**: Pytest, deploy, ou atualização de capacidade
2. **Recompensa**: Pontos positivos ou negativos são atribuídos
3. **Análise**: Métricas de eficiência são calculadas
4. **Melhoria**: Recomendações são geradas para futuras ações

### 4. Policy Engine (Motor de Políticas)

Usa o **Llama 3.3-70b (High Gear)** para analisar o histórico de recompensas e:

- Identificar padrões de erro
- Recomendar o caminho mais seguro para a próxima meta
- Sugerir melhorias para aumentar a eficiência
- Aprender com erros passados

### 5. Status de Eficiência

Exibe no login do HUD:

```
📈 Comandante, meu nível de eficiência aumentou 72.5 pontos baseado nas últimas evoluções (Taxa de sucesso: 57.1%)
```

## Arquitetura

O módulo segue a **Arquitetura Hexagonal** (Clean Architecture):

```
Domain Layer (app/domain/models/)
├── evolution_reward.py         # Modelo de dados SQLModel

Application Layer
├── ports/
│   └── reward_provider.py      # Interface (porta)
└── services/
    └── evolution_loop.py       # Lógica de negócio

Infrastructure Layer (app/adapters/)
└── infrastructure/
    └── reward_adapter.py       # Implementação do banco de dados
```

## Instalação

### 1. Migração do Banco de Dados

Execute a migração SQL no Supabase:

```sql
-- Arquivo: migrations/002_create_evolution_rewards.sql
-- Cria a tabela evolution_rewards
```

Para aplicar manualmente:

```bash
psql -h db.saibtpdehhprttqlgqdt.supabase.co -U postgres -d postgres -f migrations/002_create_evolution_rewards.sql
```

### 2. Dependências

Todas as dependências já estão incluídas em `requirements.txt`:

- SQLModel (ORM)
- SQLAlchemy
- Groq (para Llama 3.3-70b)

## Uso

### 1. Exemplo Básico - Logging de Pytest

```python
from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter
from app.adapters.infrastructure.reward_adapter import RewardAdapter
from app.application.services.evolution_loop import EvolutionLoopService
from app.core.config import settings

# Inicializar serviços
db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)
reward_adapter = RewardAdapter(engine=db_adapter.engine)
evolution_service = EvolutionLoopService(reward_provider=reward_adapter)

# Logar resultado de teste
evolution_service.log_pytest_result(
    passed=True,
    test_count=25,
    metadata={'ci_run_id': 'abc123', 'branch': 'main'}
)
```

### 2. Exemplo - Logging de Deploy

```python
# Deploy bem-sucedido
evolution_service.log_deploy_result(
    success=True,
    deployment_id='deploy-123',
    metadata={'environment': 'production'}
)

# Deploy com falha
evolution_service.log_deploy_result(
    success=False,
    error_message='Build failed',
    metadata={'environment': 'staging'}
)

# Rollback
evolution_service.log_deploy_result(
    success=False,
    rollback=True,
    error_message='Critical bug detected'
)
```

### 3. Exemplo - Status de Eficiência

```python
# Obter status para exibir no HUD
status = evolution_service.get_evolution_status(days=7)

print(status['commander_message'])
# 📈 Comandante, meu nível de eficiência aumentou 72.5 pontos...

print(f"Efficiency Score: {status['efficiency_score']}")
print(f"Success Rate: {status['success_rate']}%")
```

### 4. Exemplo - Policy Engine (Análise com IA)

```python
# Requer AIGateway configurado
from app.adapters.infrastructure.ai_gateway import AIGateway

ai_gateway = AIGateway(groq_api_key="...", groq_model="llama-3.3-70b-versatile")
evolution_service = EvolutionLoopService(
    reward_provider=reward_adapter,
    ai_gateway=ai_gateway
)

# Análise assíncrona
analysis = await evolution_service.analyze_with_policy_engine(days=30)
print(analysis['analysis'])
# IA retorna recomendações baseadas em erros passados
```

## Scripts CLI

### 1. Visualizar Status de RL

```bash
python scripts/show_rl_status.py --days 7
```

Exibe:
- Mensagem do comandante
- Métricas de eficiência
- Breakdown por tipo de ação
- Últimos 10 eventos

### 2. Exemplo de Integração

```bash
python scripts/example_evolution_integration.py
```

Demonstra todos os cenários de uso:
- Integração com pytest
- Integração com deploys
- Progresso de roadmap
- Status no HUD
- Policy Engine

## Integração com CI/CD

### GitHub Actions

```yaml
# .github/workflows/test.yml
- name: Run Tests
  id: test
  run: pytest
  continue-on-error: true

- name: Log Test Results to RL
  run: |
    python -c "
    from app.application.services.evolution_loop import EvolutionLoopService
    from app.adapters.infrastructure.reward_adapter import RewardAdapter
    from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter
    from app.core.config import settings
    
    db = SQLiteHistoryAdapter(database_url=settings.database_url)
    reward = RewardAdapter(engine=db.engine)
    evolution = EvolutionLoopService(reward_provider=reward)
    
    passed = '${{ steps.test.outcome }}' == 'success'
    evolution.log_pytest_result(passed=passed, metadata={'workflow': 'CI'})
    "
```

### Deploy com Render

```yaml
# render.yaml
services:
  - type: web
    name: jarvis
    env: python
    buildCommand: |
      pip install -r requirements.txt
      python -c "
      from app.application.services.evolution_loop import EvolutionLoopService
      # Log deploy success
      "
```

## Integração com Container DI

O módulo está integrado ao container de injeção de dependências:

```python
from app.container import Container

container = Container()

# Acessar serviço de evolução
evolution_service = container.evolution_loop_service

# Logar ações
evolution_service.log_pytest_result(passed=True, test_count=10)
```

## Métricas e Estatísticas

### Efficiency Score

Soma total de todos os pontos de recompensa:

- Positivo: Sistema está melhorando
- Negativo: Sistema precisa de ajustes
- Zero: Sistema estável

### Success Rate

Percentual de ações bem-sucedidas vs total:

- ≥ 70%: 🟢 Excelente
- 50-70%: 🟡 Bom
- < 50%: 🔴 Necessita melhoria

### Improvement

Comparação entre período atual e anterior:

- Positivo: Eficiência aumentou
- Negativo: Eficiência diminuiu
- Zero: Manteve-se estável

## Estrutura do Banco de Dados

```sql
CREATE TABLE evolution_rewards (
    id SERIAL PRIMARY KEY,
    action_type VARCHAR(100) NOT NULL,      -- Tipo de ação
    reward_value FLOAT NOT NULL,            -- Pontos (+/-)
    context_data JSONB DEFAULT '{}',        -- Contexto da ação
    meta_data JSONB DEFAULT '{}',           -- Metadados adicionais
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Exemplo de registro**:

```json
{
  "id": 1,
  "action_type": "pytest_pass",
  "reward_value": 25.0,
  "context_data": {
    "passed": true,
    "test_count": 10,
    "failed_tests": []
  },
  "meta_data": {
    "ci_run_id": "abc123",
    "branch": "main"
  },
  "created_at": "2026-02-11T01:12:04Z"
}
```

## Testes

Execute os testes do módulo:

```bash
pytest tests/test_evolution_loop.py -v
```

**Cobertura**: 82% do evolution_loop.py (24 testes passando)

## Roadmap Futuro

- [ ] Dashboard web interativo para visualização
- [ ] Alertas automáticos quando eficiência cai
- [ ] Integração com Slack/Discord para notificações
- [ ] Análise preditiva de falhas
- [ ] Recomendações automáticas de PRs
- [ ] A/B testing de diferentes estratégias

## Contribuindo

1. Novos tipos de ação devem ser adicionados em `EvolutionLoopService.REWARDS`
2. Testes devem ser criados em `tests/test_evolution_loop.py`
3. Documentação deve ser atualizada neste README

## Suporte

Para dúvidas ou problemas:

1. Verifique os logs: `evolution_service` usa logging Python
2. Execute `show_rl_status.py` para verificar o estado
3. Consulte os exemplos em `scripts/example_evolution_integration.py`

## Licença

Mesma licença do projeto principal JARVIS.
