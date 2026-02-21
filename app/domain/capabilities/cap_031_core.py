
def execute(context=None):
    if context is None:
        context = {}
    user_actions = context.get('user_actions', [])
    goals = []
    for action in user_actions:
        # Infer intention from behavior
        intention = infer_intention(action)
        if intention:
            goals.append(intention)
    return goals

def infer_intention(action):
    # Implementar lógica para inferir intenção
    # Exemplo: se o usuário pede para ligar a luz, a intenção pode ser 'iluminar o ambiente'
    intentions = {
        'ligar_luz': 'iluminar o ambiente',
        'desligar_luz': 'economizar energia'
    }
    return intentions.get(action, None)
