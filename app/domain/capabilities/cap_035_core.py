
def execute(context=None):
    if context is None:
        context = {}
        # Carregar dependências
        from app.domain.capabilities.cap_034_core import CAP034
        cap034 = CAP034()
        user_data = cap034.execute(context)

        # Identificar mudanças nos padrões do usuário
        changes = []
        for key, value in user_data.items():
            if key not in context or context[key] != value:
                changes.append({key: value})

        # Atualizar contexto com as mudanças detectadas
        context.update(user_data)
        return changes
