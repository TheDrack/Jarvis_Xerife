# DeepSeek V4.1 Flash — referência para o Jarvis Learning Engine

**Status:** referência técnica e plano de integração; não habilita chamadas externas, treinamento ou alteração de pesos.
**Modelo de referência:** `deepseek-ai/DeepSeek-V4.1-Flash-1017`
**Alias atual da API:** `deepseek-flash`
**Licença dos pesos publicados:** MIT (conforme model card do Hugging Face).

## 1. Fontes primárias

- [DeepSeek — V4.1 Flash release](https://www.deepseek.com/en/news/deepseek-v4-1-flash/)
- [DeepSeek API — V4.1 Flash 1017 update](https://api-docs.deepseek.com/news/news261017/)
- [DeepSeek API — quick start / agent integrations](https://api-docs.deepseek.com/quick_start/agent_integrations/)
- [DeepSeek API — Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
- [Hugging Face — V4.1-Flash-1017 model card and technical report](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017)
- [vLLM — deployment recipe](https://github.com/vllm-project/vllm/blob/main/recipes/models/deepseek-ai/DeepSeek-V4.1-Flash.yaml)

O alias `deepseek-flash` é servido atualmente pelo checkpoint 1017. Os nomes legados `deepseek-v4-flash` e `deepseek-v4-flash-vision-exp` são aliases de compatibilidade e não devem ser usados em novas configurações.

## 2. Arquitetura documentada

| Elemento | Especificação publicada |
|---|---|
| Backbone | 552B parâmetros MoE |
| Ativação | 8B na codificação da entrada; 16B na geração |
| Transformer | 40 camadas: 20 encoder causal + 20 decoder |
| Roteamento MoE | 1 especialista compartilhado + 384 roteados; 6 roteados ativos por token |
| Engram | Memória condicional de 196B parâmetros, acessada por lookup de tokens |
| Contexto | Até 1.048.576 tokens |
| Modalidade | Texto e imagem nativos |
| Inferência especulativa | DSpark |
| Atenção | CED com KV global projetado dos estados finais do encoder; atenção esparsa/comprimida |
| Resíduo | Single-Pass mHC |

**Interpretação para o Jarvis:** o valor arquitetural está na assimetria entre leitura e geração, no roteamento esparso e na separação entre recuperação de padrões e computação de raciocínio. Não devemos traduzir isso em “384 agentes” nem supor que seis LLMs separados reproduzam MoE.

Engram não é uma memória episódica equivalente à memória do Jarvis. É um mecanismo paramétrico/condicional dentro do modelo. A memória episódica, semântica e procedural do Jarvis deve continuar fora dos pesos e com proveniência própria.

## 3. Receita de treinamento documentada

O relatório técnico descreve a sequência:

1. **SFT:** ajuste supervisionado.
2. **RL:** pós-treinamento por reinforcement learning.
3. **OPD:** on-policy distillation.

O relatório declara que a receita algorítmica não introduz mudanças fundamentais nesses três algoritmos. As mudanças relevantes concentram-se na geração de dados: síntese automatizada de tarefas agentic e ambientes, escalonamento progressivo da dificuldade/volume e aumento dos rollouts.

O anúncio 1017 também descreve RL com self-feedback para melhorar desenvolvimento de projetos completos. Isso não significa que o modelo possa validar sozinho a correção do próprio trabalho: o Jarvis deve manter verificadores independentes.

### Padrão que devemos adaptar

```text
Tarefa real / falha observada
        ↓
Aluno tenta resolver em ambiente isolado
        ↓
Professor DeepSeek critica e propõe alternativas
        ↓
Testes, execução e evidências independentes avaliam
        ↓
Episódio rotulado por proveniência e qualidade
        ↓
Currículo sintético gera variações difíceis
        ↓
Aluno é treinado em experimento versionado
        ↓
Holdout independente mede generalização e esquecimento
        ↓
Promover ou descartar candidato
```

Rótulos devem permanecer separados: resultado observado, julgamento humano, julgamento do professor e recompensa inferida. Um julgamento do DeepSeek não se transforma automaticamente em ground truth.

## 4. API versus pesos locais

São dois caminhos diferentes:

- **API:** o provedor hospeda o checkpoint; o Jarvis envia solicitações para `https://api.deepseek.com/chat/completions`, usando `model=deepseek-flash`. É a forma adequada para começar com o hardware atualmente não verificado.
- **Pesos abertos:** o checkpoint pode ser baixado sob a licença indicada no model card, mas “8B/16B ativos” não significa que o modelo inteiro caiba em 8–16 GB. Todos os pesos e estruturas necessárias precisam estar disponíveis para o runtime.

O artefato FP8 é reportado em torno de 510 GB. A receita de deployment do vLLM indica uma configuração mínima de aproximadamente 614 GB de VRAM para o checkpoint FP8. Esse número é orientação de deployment do vLLM, não um requisito universal para toda implementação. O modelo completo não é alvo de instalação no PC de trabalho.

A API é um serviço comercial com preços por tokens; disponibilidade de pesos abertos não significa API gratuita.

## 5. Integração no Jarvis existente

### Componentes a reutilizar

- `ModelProfile`, `ModelRegistry` e `ModelRuntimeBindings`: declarar modelo, provider e capacidades sem acoplar o domínio a um SDK.
- `FreeLLMAPIClient` e `FreeLLMAPIModelRuntimeAdapter`: já implementam transporte OpenAI-compatible genérico.
- `FineTuneDatasetCollector`: exportação de exemplos, sujeita aos gates de proveniência/qualidade.
- `RewardSignalProvider`: sinal auxiliar; não é oráculo de correção.
- `EvolutionSandbox` e `EvolutionGatekeeper`: validação isolada e promoção controlada.

### Lacunas para uma integração dedicada

1. O runtime genérico atual recebe configuração global `FREELLMAPI_*`; não devemos repontá-la silenciosamente para DeepSeek, pois isso pode mudar o provider dos mini-agentes existentes.
2. Criar composição isolada `deepseek_teacher` com credencial própria, base URL fixa/validada e perfil separado no ModelRegistry.
3. Expor parâmetros suportados pelo DeepSeek (`thinking` e `reasoning_effort`) através de opções tipadas do runtime, sem permitir campos arbitrários do usuário nem quebrar outros providers.
4. Registrar custo, latência, versão/alias, configuração de raciocínio e identificador do episódio; nunca registrar chaves.
5. Usar DeepSeek apenas como professor/critic no primeiro estágio. Ele não decide autorização, não promove modelos e não aprova seus próprios exemplos.
6. Não alterar o roteamento global até existir avaliação comparativa em tarefas representativas do Jarvis.

### Política inicial de uso

| Trabalho | DeepSeek teacher | Verificador independente |
|---|---:|---|
| Gerar variações de exercícios | Sim | Deduplicação + validação de schema |
| Criticar solução do aluno | Sim | Testes/execução |
| Propor correção de código | Sim | Pytest + sandbox |
| Rotular sucesso de tarefa | Apenas como julgamento de modelo | Resultado real/humano |
| Aprovar promoção de modelo | Não | Evaluation Engine + gates existentes |

## 6. Critérios antes de treinar um aluno

- C0 concluído para os caminhos de dados, memória, privacidade, proveniência e execução usados.
- Dataset com consentimento/base de uso, redaction, escopo, retenção e origem verificáveis.
- Separação temporal e por tarefa entre treino, validação e holdout.
- Baseline congelada e métricas por classe/domínio.
- Testes independentes e adversariais.
- Medição de custo, latência, VRAM/RAM e consumo de armazenamento.
- Artefato versionado, rollback testado e promoção separada da execução de treinamento.

**Decisão:** começar com DeepSeek Flash como professor via API, mantendo um aluno local pequeno e especializado. Não baixar o checkpoint completo, não repontar a frota global e não ativar fine-tuning até os gates de C0 e avaliação serem cumpridos.
