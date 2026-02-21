
def execute(context=None):
    if context is None:
        context = {}
    user_actions = context.get('user_actions', [])
    goals = []
    for action in user_actions:
        intent = analyze_action(action)
        if intent:
            goals.append(intent)
    return goals

def analyze_action(action):
    # Lógica para analisar a ação e identificar a intenção
    # Exemplo: se a ação for 'ligar a luz', a intenção pode ser 'iluminar o ambiente'
    intentions = {
        'ligar a luz': 'iluminar o ambiente',
        'desligar a luz': 'economizar energia',
        # Adicionar mais ações e intenções aqui
    }
    return intentions.get(action, None)
