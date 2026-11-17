# Security Guardrails — Jarvis Xerife

Este documento define invariantes de segurança para código, agentes, ferramentas e operações. Ele complementa as políticas implementadas; não substitui a verificação dos contratos e testes do subsistema.

## 1. Fronteira de confiança

- Prompts, respostas de LLM, arquivos, logs, conteúdo web e resultados de conectores são dados não confiáveis.
- Instruções de modelo nunca concedem privilégios.
- Identidade e autorização devem ser verificadas fora do modelo, no host/servidor que executa a ação.
- A disponibilidade de uma ferramenta no catálogo não significa que o chamador esteja autorizado.

## 2. Identidade e autorização

- Vincule cada chamada sensível a principal autenticado, sessão, ferramenta, escopo e, quando aplicável, task/attempt.
- Valide permissões no momento da execução, não apenas no momento do cadastro.
- Use allowlists explícitas e princípio do menor privilégio.
- Ausência de principal, grant ou política válida deve falhar fechada.
- Tokens de worker devem ser individuais, opacos, armazenados como hash, expiráveis e revogáveis.
- Não trate JWT de usuário e token de worker como credenciais intercambiáveis.
- O caminho legado direto com Supabase service-role não oferece a mesma identidade individual; não o descreva como equivalente ao caminho autenticado.
- Não armazene credenciais em manifests, exemplos, prompts, logs ou commits.

## 3. Execução de ferramentas

- Validar schema de entrada/saída e versão exata do manifest.
- Verificar autorização antes de resolver/executar o adapter.
- Restringir operações, parâmetros, escopo, timeout, taxa e orçamento conforme a política real.
- Separar leitura, ação limitada e intervenção privilegiada.
- Registrar metadados mínimos de auditoria, sem payloads sensíveis.
- Idempotência em memória do processo não equivale a idempotência distribuída.
- Não executar shell, código arbitrário, upload, alteração de rede ou ação administrativa apenas porque o modelo solicitou.

## 4. Segredos e configuração

- Use o mecanismo de configuração/secret provider do subsistema; evite leitura ad hoc de variáveis de ambiente espalhada pelo domínio.
- Nunca imprimir valores de tokens, senhas, API keys, cookies, runtime keys ou chaves privadas.
- Logs e diagnósticos devem expor presença/estado, nunca valor.
- .env, arquivos de perfil e artefatos com credenciais não devem ser commitados.
- Rotação/revogação deve ser tratada como operação de segurança, com autorização e verificação posterior.

## 5. Dados pessoais e conteúdo sensível

- Colete apenas o necessário para a finalidade autorizada.
- Redija ou minimize PII antes de indexação, persistência ou envio a terceiros, conforme o contrato do subsistema.
- Não persistir payloads brutos de rede no pipeline de metadados passivos.
- Não registrar conteúdo de tela, áudio, tráfego ou documentos sem autorização e finalidade explícitas.
- Defina retenção, exclusão e escopo por usuário/principal para dados duráveis.

## 6. Android, Desktop e Host

- Permissões Android são concedidas pelo usuário e podem ser revogadas; não contorne VPN, Accessibility, consentimento ou restrições do sistema.
- Shell Android é opt-in, pareado e limitado ao perfil de sessão autorizado.
- Inspeção passiva de tráfego não deve contornar TLS, certificate pinning ou confiança de aplicativos.
- Desktop deve usar listener restrito, autenticação/pairing e firewall de escopo mínimo.
- Não exponha portas locais à internet pública. Use transporte privado autenticado e valide Host/Origin.
- Ferramentas visuais devem observar o estado antes de agir e verificar pós-condições.

## 7. Multiagente e execução autônoma

- Cada worker deve ter identidade e grants próprios; não compartilhar token entre slots.
- A fila deve validar lease, tentativa atual e fencing antes de aceitar conclusão.
- Worker com capacidade text_reasoning não deve receber tarefas que exigem browser, shell, GitHub ou ferramentas externas.
- Aprovação humana para ações sensíveis deve ser verificada por componente confiável, não por campo fornecido pelo LLM.
- Evolução de código deve ocorrer em snapshot isolado, com rede e filesystem limitados, testes e revisão antes de publicar.
- Nunca auto-merge em caminhos sensíveis sem os gates e a aprovação exigidos.

## 8. Testes e mudanças

- Alterações em autenticação, autorização, execução, privacidade, rede ou persistência exigem testes de regressão focados.
- Mantenha testes de segurança ativos. Não reduza cobertura nem remova testes para fazer CI passar.
- Revise migrations, RLS e grants no banco de destino; código/migration versionada não prova aplicação em produção.
- Não declare produção segura apenas porque testes locais passaram.

## 9. Resposta a incidentes

1. Interrompa a operação afetada sem apagar evidências.
2. Preserve logs sanitizados, IDs de request/task e timestamps.
3. Revogue credenciais comprometidas por fluxo autorizado.
4. Determine escopo e impacto a partir de evidências.
5. Corrija em branch isolada e adicione regressões.
6. Revalide permissões, dados e serviço após a correção.

## Referências

- [Arquitetura](docs/ARCHITECTURE.md)
- [Identidade de workers](docs/architecture/agent-worker-identity.md)
- [Inventário de capacidades](docs/skills-connectors/CAPABILITY_INVENTORY.md)
- [Protocolo de contexto e memória](docs/skills-connectors/CONTEXT_MEMORY_PROTOCOL.md)
