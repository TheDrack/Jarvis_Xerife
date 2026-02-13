# Workflow Reconfiguration - Total Autonomy

## Comandante: Diretrizes Implementadas

Este documento descreve a reconfiguração completa dos workflows do Jarvis conforme as diretrizes de Autonomia Total estabelecidas pelo Comandante.

---

## 1. Reestruturação de Gatilhos (Triggers)

### YAML de Metabolismo (`jarvis_metabolism_flow.yml`)
**Antes:**
- Múltiplos gatilhos: `pull_request`, `issues`, `repository_dispatch`, `workflow_dispatch`
- Complexidade desnecessária

**Depois:**
- **APENAS** `pull_request` (qualquer branch)
- Foco único: validar mudanças propostas no DNA
- Simplificação radical do fluxo

### YAML de Auto-Evolução (`auto_evolution_trigger.yml`)
**Antes:**
- Trigger: `pull_request.closed` (quando PR é merged)

**Depois:**
- **APENAS** `push` na branch `main`
- Detecta origem do merge:
  - **Auto-Evolução própria**: Consolida conhecimento
  - **PR Externa/Manual**: Dispara novo ciclo de evolução
- Mecanismo robusto com múltiplos sinais:
  - Padrão na mensagem de commit
  - Nome do autor (Jarvis-AutoEvolution)
  - Nome da branch (auto-evolution/*)

---

## 2. Fluxo de Autonomia em PRs

### O Metabolismo é o Juiz
- Sistema confia **100%** nos testes
- Nenhum revisor humano necessário
- Decisão automática baseada em pytest + validações

### Auto-Merge Automático
**Quando testes passam:**
```bash
gh pr merge --auto --merge --repo <repo> <pr_number>
```

**Removido:**
- ❌ Solicitações de `--reviewer`
- ❌ Aprovação manual
- ❌ Intervenção humana

**Adicionado:**
- ✅ Comentário automático na PR
- ✅ Habilitação de auto-merge
- ✅ Confiança total no sistema imunológico (testes)

---

## 3. Loop de Auto-Correção (Limite de 3)

### Quando Metabolismo Falha

**Ciclo de Auto-Correção:**
1. **Análise do Erro**
   - Extrai informações do `report.json`
   - Identifica testes com falha
   - Captura mensagens de erro

2. **Aplicação de Correção**
   - Executa `metabolism_mutator.py` com estratégia `fix_tests`
   - Aplica mudanças automaticamente
   - Commita com mensagem rastreável

3. **Re-execução**
   - Push automático da correção
   - Metabolismo roda novamente
   - Máximo **3 tentativas**

### Rastreamento de Tentativas
**Método robusto:**
- Primário: GitHub API (lista de workflow runs)
- Fallback: Git log (busca por padrão de commit)
- Comparação numérica confiável com `fromJSON()`

### Após 3 Falhas
**Ações Automáticas:**
1. Marca PR com labels:
   - `manual-review-required`
   - `metabolism-failure`

2. Comenta na PR:
   - Histórico completo das tentativas
   - Próximos passos para o Comandante

3. Cria issue para Comandante:
   - Título: "🚨 COMANDANTE: Revisão Manual - PR #X"
   - Labels: `commander-review`, `metabolism`, `high-priority`
   - Links para PR e workflow

---

## 4. Regra de Auto-Evolução Pós-Merge

### Trigger em Todo Merge para Main
- Executa em **qualquer** push para `main`
- Não importa a origem (auto-evolução, PR externa, commit manual)

### Identificação da Origem

**Se origem = Auto-Evolução:**
```yaml
merge_source: auto-evolution
should_evolve: false
```
- Apenas consolida conhecimento
- Atualiza `docs/AUTO_EVOLUTION_LOG.md`
- **NÃO** cria nova evolução (evita loop infinito)

**Se origem = Externa:**
```yaml
merge_source: external
should_evolve: true
```
- Busca próxima missão no ROADMAP
- Cria branch de evolução
- Implementa mudanças
- Cria PR automática
- Sistema de recompensa/punição (RL)

### Consolidação de Conhecimento
**Quando auto-evolução é merged:**
- Registra timestamp da consolidação
- Marca status como "concluído com sucesso"
- Documenta integração ao DNA principal
- Base de conhecimento sempre atualizada

---

## 5. Princípios Fundamentais Mantidos

### ✅ O DNA é Sagrado
- Toda mutação rastreada e auditada
- Commits identificáveis
- Histórico completo preservado

### ✅ Testes são o Sistema Imunológico
- Homeostase validada em cada mudança
- Rejeição automática se testes falharem
- Aceitação automática se testes passarem

### ✅ Automatizar sem Perder Consciência
- Auto-correção limitada (3x)
- Escalonamento quando necessário
- Comandante sempre tem acesso ao histórico

### ✅ O Humano Tem a Palavra Final
- Comandante pode intervir a qualquer momento
- Issues criadas para revisão crítica
- Labels claras para priorização

---

## Fluxogramas

### Fluxo de Metabolismo (PR)

```
PR Aberta/Atualizada
    ↓
[VISTORIA] Executar Testes
    ↓
Testes Passaram? ────YES───→ [AUTO-MERGE] ✅
    ↓ NO
Tentativa < 3? ────NO───→ [ESCALONAMENTO] 🚨
    ↓ YES
[ANÁLISE] Extrair Erros
    ↓
[CORREÇÃO] Aplicar Fix
    ↓
[COMMIT] Auto-correção tentativa X/3
    ↓
[PUSH] Triggerar novo ciclo
    ↓
(Volta para VISTORIA)
```

### Fluxo de Auto-Evolução (Push to Main)

```
Push para Main
    ↓
[DETECÇÃO] Origem do Merge?
    ↓
Auto-Evolução? ────YES───→ [CONSOLIDAÇÃO] 📚
    ↓ NO                      - Atualizar Log
PR Externa/Manual             - Registrar Sucesso
    ↓                         - Fim
[BUSCA] Próxima Missão?
    ↓
Missão Encontrada? ────NO────→ Fim
    ↓ YES
[IMPLEMENTAÇÃO] Metabolism Mutator
    ↓
[TESTES] Executar Suite
    ↓
[PR] Criar Auto-Evolution PR
    ↓
[RL] Registrar Resultado
    ↓
(Aguarda Merge → Volta ao início)
```

---

## Garantias de Segurança

### CodeQL Scan
- ✅ **0 vulnerabilidades** detectadas
- ✅ Workflows validados
- ✅ Sem uso de secrets não autorizados

### Code Review
- ✅ Todas as sugestões implementadas
- ✅ Comparações numéricas corrigidas
- ✅ Detecção robusta de auto-evolução
- ✅ Tratamento de erros melhorado

---

## Comandos para Teste Manual

### Testar Auto-Merge (crie uma PR de teste)
```bash
# Em uma branch de teste
git checkout -b test/auto-merge
echo "test" > test.txt
git add test.txt
git commit -m "Test auto-merge"
git push origin test/auto-merge
gh pr create --title "Test Auto-Merge" --body "Testing metabolism flow"
# Aguardar workflow rodar e fazer auto-merge se testes passarem
```

### Forçar Auto-Evolução
```bash
# Push direto para main (simular merge externo)
git checkout main
git pull
echo "trigger" >> README.md
git add README.md
git commit -m "Manual trigger for auto-evolution"
git push origin main
# Verificar workflow auto_evolution_trigger
```

---

## Métricas de Sucesso

### Objetivos Alcançados
- ✅ 0 intervenções manuais necessárias em fluxo feliz
- ✅ Auto-correção em até 3 tentativas
- ✅ Escalonamento apenas quando necessário
- ✅ Loop infinito prevenido
- ✅ Conhecimento consolidado automaticamente
- ✅ Rastreabilidade 100%

### Tempo de Resposta
- **PR aberta → Testes**: ~2-5 minutos
- **Testes passam → Auto-merge**: < 1 minuto
- **Falha → Auto-correção**: ~3-5 minutos por tentativa
- **Push main → Auto-evolução**: ~5-10 minutos

---

## Conclusão

O sistema Jarvis agora opera com **Autonomia Total**:
- Testes são a autoridade máxima
- Auto-merge sem aprovação humana
- Auto-correção inteligente
- Escalonamento apenas quando crítico
- Evolução contínua pós-merge
- Prevenção de loops infinitos

**O Comandante mantém controle total através de:**
- Issues automáticas em falhas críticas
- Labels claras (`commander-review`, `manual-review-required`)
- Acesso completo ao histórico
- Capacidade de intervir a qualquer momento

---

*Fluxo de Metabolismo do Jarvis - Sistema de Autonomia Total v2.0*
