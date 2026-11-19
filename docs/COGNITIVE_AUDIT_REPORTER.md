# Relatório horário de auditoria cognitiva

**Escopo:** documentação técnica do relatório gerado por `scripts/hourly_curiosity_audit.py` e executado por `.github/workflows/hourly_curiosity_audit.yml`.

## Contrato de fontes

- `docs/COGNITIVE_ROADMAP.md` é a fonte dos critérios e da ordem das fases.
- `docs/STATUS.md` fornece o estado por meio do ledger delimitado `JARVIS_COGNITIVE_EVIDENCE`.
- O relatório exibe a primeira fase com critério não verificado. Uma fase sem IDs machine-readable (como C1 no roadmap atual) é reportada como `unknown`, nunca ignorada nem presumida concluída. Registro ausente, duplicado, malformado ou com evidência incompleta também não pode ser tratado como concluído.
- Um estado `verified` precisa conter referência de commit e check de Actions deste repositório. Os caminhos de implementação, consumidor e teste são resolvidos pela política compartilhada `repository_path_policy`, precisam apontar para arquivos existentes e rejeitam symlinks/escapes. A validação semântica de consumidor e runtime continua pertencendo ao selector e à revisão.

## Limites

O relatório é somente leitura. Não altera STATUS, não cria missões, não executa código candidato e não promove critérios. O entrypoint adiciona a raiz do checkout ao caminho de importação para funcionar no comando direto usado pelo workflow horário, mesmo sem `PYTHONPATH`. Uma saída sem critérios pendentes não comprova runtime ou produção; apenas indica que os IDs explícitos do roadmap estão marcados como `verified` no ledger.

## Regressão corrigida — 2026-11-18

O relatório anterior procurava uma seção `## Roadmap` dentro de `docs/STATUS.md`, mas essa seção não existia. A execução horária de 2026-11-18 publicou o texto `Não foi possível localizar a seção 'Roadmap' em docs/STATUS.md.` apesar de a suíte ter passado.

A implementação corrigida lê o roadmap e o ledger separadamente, preserva a ordem C0 antes de C1 e falha de forma conservadora quando a evidência está ausente ou inválida. Os testes de regressão estão em `tests/test_hourly_curiosity_audit_report.py`.
