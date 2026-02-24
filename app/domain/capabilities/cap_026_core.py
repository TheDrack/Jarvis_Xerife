
def execute(context=None):
    if context is None:
        context = {}

    # Avaliar se a mudança beneficia uma tarefa específica ou a arquitetura inteira
    def evaluate_change(change):
        if change['scope'] == 'local':
            return 'A mudança beneficia uma tarefa específica.'
        elif change['scope'] == 'systemic':
            return 'A mudança beneficia a arquitetura inteira.'
        else:
            return 'Não foi possível determinar o escopo da mudança.'

    # Simular uma mudança para teste
    change = {
        'scope': 'systemic',
        'description': 'Mudança no sistema de gerenciamento de banco de dados.'
    }

    result = evaluate_change(change)
    return result
