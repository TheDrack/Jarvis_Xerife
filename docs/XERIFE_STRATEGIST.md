# Xerife Strategist Module

## Visão Geral

O **Xerife Strategist** é um módulo avançado que dá ao Jarvis a capacidade de propor e implementar melhorias de forma autônoma, mas sob um rigoroso filtro de custo-benefício e segurança. Este módulo implementa um sistema de análise ROI (Return on Investment) para decisões técnicas.

## Componentes Principais

### 1. ViabilityMatrix (Matriz de Viabilidade)

A matriz de viabilidade é o coração do sistema de decisão. Ela analisa três dimensões:

#### Custo Estimado (`CostEstimate`)
- **Tokens de API**: Consumo estimado de tokens LLM
- **Custo em USD**: Valor monetário estimado
- **Complexidade de Código**: Simple, Moderate, ou Complex
- **Linhas de Código**: Estimativa de LOC
- **Tempo de Desenvolvimento**: Horas estimadas
- **Tempo de CI/CD**: Minutos de pipeline

#### Impacto Sugerido (`ImpactEstimate`)
- **Ganho de Performance**: Porcentagem de melhoria
- **Redução de Erros**: Porcentagem de bugs evitados
- **Bugs Prevenidos**: Número estimado
- **Utilidade para o Usuário**: Minimal, Low, Medium, High, Critical
- **Redução de Débito Técnico**: Boolean
- **Melhoria de Manutenibilidade**: Boolean

#### Risco Técnico (`RiskEstimate`)
- **Nível de Risco**: Low, Medium, High, Critical
- **Quebra de Sistemas Legados**: Boolean
- **Novas Dependências**: Boolean
- **Preocupações de Segurança**: Boolean
- **Incompatibilidade Retroativa**: Boolean
- **Descrição do Risco**: Texto livre
- **Estratégia de Mitigação**: Texto livre

### 2. StrategistService

Serviço responsável por:
- Gerar matrizes de viabilidade
- Calcular ROI: `(Impact - Risk) / Cost`
- Arquivar propostas (aprovadas/rejeitadas)
- Gerar RFCs (Request for Comments)
- Formatar prompts de decisão
- Verificar orçamento
- Analisar logs de erro

## Fluxo de Proposta de Melhoria (RFC)

### 1. Monólogo Interno (INTERNAL_MONOLOGUE)

Antes de propor qualquer melhoria, o Jarvis realiza um monólogo interno para avaliar viabilidade:

```python
from app.application.services.strategist_service import StrategistService
from app.domain.models.viability import (
    CostEstimate,
    ImpactEstimate,
    ImpactLevel,
    RiskEstimate,
    RiskLevel,
)

# Inicializar serviço
strategist = StrategistService(
    default_budget_cap=10.0,  # $10 por missão
    min_roi_threshold=0.5,    # ROI mínimo de 0.5
)

# Estimar custos
cost = CostEstimate(
    api_tokens=5000,
    api_cost_usd=0.05,
    code_complexity="moderate",
    lines_of_code_estimate=150,
    development_time_hours=2.0,
    ci_cd_time_minutes=10,
)

# Estimar impacto
impact = ImpactEstimate(
    performance_gain_percent=30.0,
    error_reduction_percent=20.0,
    potential_bugs_prevented=3,
    user_utility_level=ImpactLevel.HIGH,
    technical_debt_reduction=True,
)

# Estimar riscos
risk = RiskEstimate(
    risk_level=RiskLevel.MEDIUM,
    introduces_new_dependencies=True,
    risk_description="Pode afetar módulos legados de autenticação",
    mitigation_strategy="Adicionar testes de regressão completos",
)

# Gerar matriz de viabilidade
matrix = strategist.generate_viability_matrix(
    proposal_title="Adicionar cache de sessão Redis",
    proposal_description="Implementar cache distribuído para melhorar performance de autenticação",
    cost=cost,
    impact=impact,
    risk=risk,
)

# Verificar viabilidade
if matrix.is_viable():
    print(f"✅ Proposta aprovada! ROI: {matrix.calculate_roi():.2f}")
else:
    print(f"❌ Proposta rejeitada: {matrix.rejection_reason}")
```

### 2. Arquivamento da Proposta

Se aprovada internamente, a proposta é arquivada:

```python
# Arquivar proposta
filepath = strategist.archive_proposal(matrix)
# Salvo em: docs/proposals/approved/{proposal_id}.json
```

Se rejeitada, vai para o diretório de rejeitadas:

```python
# Proposta rejeitada vai para: docs/proposals/rejected/{proposal_id}.json
```

### 3. Geração de RFC

Para propostas aprovadas, um RFC é gerado automaticamente:

```python
if matrix.approved:
    rfc_path = strategist.generate_rfc(matrix)
    # Salvo em: docs/proposals/RFC-XXXX.md
    print(f"RFC gerado: {rfc_path}")
```

O RFC contém:
- Resumo da proposta
- Análise detalhada de custos, impacto e riscos
- ROI score
- Espaço para implementação técnica
- Seção de decisão (aguardando aprovação)

### 4. Interface de Decisão com o Comandante

Antes de implementar, o Jarvis apresenta a proposta ao usuário:

```python
# Formatar prompt de decisão
prompt = strategist.format_decision_prompt(matrix)
print(prompt)
```

Exemplo de output:

```
🎯 **Comandante, identifiquei uma oportunidade de melhoria com ROI positivo.**

**Proposta:** Adicionar cache de sessão Redis
Implementar cache distribuído para melhorar performance de autenticação

**Análise de Viabilidade:**
• ROI Score: 2.15 (Impact-Risk/Cost = (6.5-3.0)/1.6)
• Custo Estimado: $0.05 USD, 2.0h dev, complexidade moderate
• Benefício Esperado: high utilidade, 30% perf, 20% menos erros
• Risco Técnico: medium
  - Pode afetar módulos legados de autenticação
  - Mitigação: Adicionar testes de regressão completos

**Recomendação:** ✅ APROVAR

**Posso prosseguir com a criação da branch e implementação?** (sim/não)
```

## Travas de Segurança e Orçamento

### 1. Budget Cap (Teto de Gastos)

O TaskRunner agora suporta controle de orçamento:

```python
from app.application.services.task_runner import TaskRunner

# Inicializar com budget cap
runner = TaskRunner(
    sandbox_mode=True,
    budget_cap_usd=50.0,  # Máximo $50 por instância
)

# Rastrear custos
runner.track_mission_cost("mission_001", 2.50)
runner.track_mission_cost("mission_002", 3.75)

# Verificar status
status = runner.get_budget_status()
print(f"Gasto: ${status['total_cost_usd']:.2f}")
print(f"Restante: ${status['remaining_usd']:.2f}")
print(f"Dentro do orçamento: {status['within_budget']}")

# Se exceder o orçamento
if not runner.is_within_budget():
    print("⚠️ ALERTA: Orçamento excedido! Abortando missão.")
    # Lógica de abort
```

### 2. Sandbox Mode (Modo Seguro)

Para execução segura de código gerado:

```python
runner = TaskRunner(
    sandbox_mode=True,  # Ativa modo sandbox
    use_venv=True,      # Sempre usar venv em sandbox
)

# Scripts são executados em ambiente isolado
# Localização: {cache_dir}/sandbox/
```

### 3. Verificação de Budget por Tokens

```python
from app.application.services.strategist_service import BudgetExceededException

try:
    cost, within = strategist.check_budget(
        used_tokens=10000,
        token_cost_per_1k=0.002,  # $0.002 por 1K tokens
        budget_cap=5.0,            # $5 cap
    )
    print(f"Custo atual: ${cost:.4f}")
except BudgetExceededException as e:
    print(f"Orçamento excedido: ${e.used:.2f} > ${e.limit:.2f}")
    # Abortar missão
```

## Autotimização e Análise de Erros

### Análise Periódica de Logs

O Strategist pode analisar logs de erro e sugerir refatorações preventivas:

```python
# Logs de erro do sistema
error_logs = [
    {
        "error_message": "NoneType object has no attribute 'user_id'",
        "error_type": "AttributeError",
        "count": 15,
    },
    {
        "error_message": "Connection timeout to Redis",
        "error_type": "TimeoutError",
        "count": 8,
    },
]

# Analisar e gerar sugestões
suggestions = strategist.analyze_error_logs(error_logs)

for suggestion in suggestions:
    print(f"💡 {suggestion}")
```

Output:
```
💡 Refactoring oportunidade: 'AttributeError:NoneType object has no attribute 'user_id'' 
   ocorreu 15 vezes. Considere adicionar validação ou tratamento específico.
💡 Refactoring oportunidade: 'TimeoutError:Connection timeout to Redis' 
   ocorreu 8 vezes. Considere adicionar validação ou tratamento específico.
```

## Princípio da Frugalidade

O Xerife Strategist prioriza soluções **"Suficientemente Boas"** (Good Enough) em vez de arquiteturas super-complexas:

### Critérios de Aprovação Automática

Uma proposta é **automaticamente rejeitada** se:

1. **ROI < threshold** (padrão: 0.5)
2. **Risco CRITICAL** (sempre rejeita)
3. **Risco HIGH** + Utilidade não é HIGH/CRITICAL
4. **Security concerns** sem estratégia de mitigação
5. **Custo > 10x benefício**

### Preferência por Simplicidade

O sistema de scoring favorece:
- Código simples vs complexo
- Menos dependências
- Menor tempo de desenvolvimento
- Menor custo de API

## Estrutura de Diretórios

```
docs/proposals/
├── approved/              # Propostas aprovadas (JSON)
│   └── {proposal_id}.json
├── rejected/              # Propostas rejeitadas (JSON)
│   └── {proposal_id}.json
└── RFC-XXXX.md           # RFCs gerados
```

## Integração com ThoughtLog

O Xerife Strategist pode ser integrado com o sistema de ThoughtLog para rastrear o processo de decisão:

```python
from app.domain.models.thought_log import ThoughtLog, InteractionStatus

# Registrar monólogo interno
thought = ThoughtLog(
    mission_id="strategist_analysis_001",
    session_id="session_123",
    status=InteractionStatus.INTERNAL_MONOLOGUE,
    thought_process=f"Analisando proposta: ROI={matrix.calculate_roi():.2f}",
    problem_description="Identificada oportunidade de cache Redis",
    solution_attempt="Proposta de implementação com matriz de viabilidade",
    success=matrix.is_viable(),
)
```

## Exemplo Completo de Fluxo

```python
# 1. Monólogo Interno
strategist = StrategistService(default_budget_cap=10.0)

# 2. Definir proposta
matrix = strategist.generate_viability_matrix(
    proposal_title="API Rate Limiting",
    proposal_description="Adicionar rate limiting para prevenir abuse",
    cost=CostEstimate(api_cost_usd=0.5, code_complexity="simple", development_time_hours=1.5),
    impact=ImpactEstimate(
        error_reduction_percent=40.0,
        user_utility_level=ImpactLevel.HIGH,
        technical_debt_reduction=False,
    ),
    risk=RiskEstimate(
        risk_level=RiskLevel.LOW,
        mitigation_strategy="Adicionar testes de carga",
    ),
)

# 3. Verificar viabilidade
if matrix.is_viable():
    # 4. Arquivar
    strategist.archive_proposal(matrix)
    
    # 5. Gerar RFC
    rfc_path = strategist.generate_rfc(matrix)
    
    # 6. Pedir aprovação ao comandante
    prompt = strategist.format_decision_prompt(matrix)
    print(prompt)
    
    # 7. Se aprovado, criar branch e implementar
    # (Jarvis NÃO pode fazer merge na main sem aprovação humana)
    
else:
    # Arquivar como rejeitada
    strategist.archive_proposal(matrix)
    print(f"Proposta rejeitada: {matrix.rejection_reason}")
```

## Limitações e Regras

### ❌ Jarvis NÃO PODE:
- Fazer merge na branch `main` sem aprovação humana
- Exceder o budget cap configurado
- Implementar propostas com risco CRITICAL
- Implementar propostas com security concerns sem mitigação

### ✅ Jarvis PODE:
- Criar branches para implementação
- Gerar Pull Requests
- Executar testes em sandbox
- Propor melhorias com base em análise de logs
- Arquivar propostas rejeitadas para aprendizado

## Métricas e Monitoramento

### Tracking de ROI

```python
# Obter todas as propostas aprovadas
approved_dir = strategist.approved_dir
proposals = list(approved_dir.glob("*.json"))

total_roi = 0
for proposal_file in proposals:
    with open(proposal_file) as f:
        data = json.load(f)
        total_roi += data['roi']

avg_roi = total_roi / len(proposals) if proposals else 0
print(f"ROI médio das propostas aprovadas: {avg_roi:.2f}")
```

### Tracking de Budget

```python
budget_status = runner.get_budget_status()
print(f"""
📊 Status do Orçamento:
- Total gasto: ${budget_status['total_cost_usd']:.2f}
- Limite: ${budget_status['budget_cap_usd']:.2f}
- Restante: ${budget_status['remaining_usd']:.2f}
- Missões rastreadas: {budget_status['missions_tracked']}
- Status: {'✅ OK' if budget_status['within_budget'] else '❌ EXCEDIDO'}
""")
```

## Próximos Passos

1. **Integração com Git**: Automação de criação de branches e PRs
2. **Machine Learning**: Melhorar estimativas de custo/impacto com dados históricos
3. **Dashboard**: Interface visual para visualizar propostas e ROI
4. **Alertas**: Notificações quando orçamento está próximo do limite
5. **A/B Testing**: Comparar ROI estimado vs real pós-implementação
