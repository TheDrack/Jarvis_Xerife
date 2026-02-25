from app.core.nexuscomponent import NexusComponent
class Cap040Core(NexusComponent):
    def __init__(self, *args, **kwargs):
        pass


    def execute(context=None):
        if context is None:
            context = {}

        # Carregar as estratégias disponíveis
        strategies = context.get('strategies', [])

        # Verificar se há estratégias disponíveis
        if not strategies:
            raise ValueError('Nenhuma estratégia disponível')

        # Inicializar o resultado
        result = {}

        # Avaliar cada estratégia
        for strategy in strategies:
            # Executar a estratégia
            strategy_result = strategy.execute(context)

            # Armazenar o resultado da estratégia
            result[strategy.__name__] = strategy_result

        # Retornar o resultado
        return result

