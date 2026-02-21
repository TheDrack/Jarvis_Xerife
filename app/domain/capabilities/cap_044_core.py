
def execute(context=None):
    if context is None:
        context = {}
    
    # Obter a estratégia a ser avaliada
    strategy = context.get('strategy')
    
    if strategy is None:
        raise ValueError('Estratégia não fornecida')
    
    # Inicializar os custos computacionais
    cpu_cost = 0
    memory_cost = 0
    token_cost = 0
    
    # Avaliar o custo computacional da estratégia
    for operation in strategy.get('operations', []):
        cpu_cost += operation.get('cpu_cost', 0)
        memory_cost += operation.get('memory_cost', 0)
        token_cost += operation.get('token_cost', 0)
    
    # Retornar os custos computacionais estimados
    return {
        'cpu_cost': cpu_cost,
        'memory_cost': memory_cost,
        'token_cost': token_cost
    }
   