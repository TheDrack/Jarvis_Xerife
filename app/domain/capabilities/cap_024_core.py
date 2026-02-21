
      def execute(context=None):
         import time
         import logging
         from app.domain.capabilities import metrics

         # Inicializar o logger
         logger = logging.getLogger(__name__)

         # Definir o período de tempo para monitorar a degradação do desempenho
         monitor_period = 60  # 1 minuto

         # Definir o limite de degradação do desempenho (em porcentagem)
         degradation_limit = 10  # 10%

         # Obter as métricas atuais do sistema
         current_metrics = metrics.get_system_metrics()

         # Calcular a degradação do desempenho em relação ao período anterior
         if context and 'previous_metrics' in context:
            previous_metrics = context['previous_metrics']
            degradation = calculate_degradation(current_metrics, previous_metrics)
         else:
            degradation = 0

         # Verificar se a degradação do desempenho ultrapassou o limite
         if degradation > degradation_limit:
            logger.warning(f'Degradation do desempenho detectada: {degradation}%')

         # Armazenar as métricas atuais para o próximo período de monitoramento
         context['previous_metrics'] = current_metrics

         # Aguardar o período de monitoramento
         time.sleep(monitor_period)

         return context

      def calculate_degradation(current_metrics, previous_metrics):
         # Calcular a degradação do desempenho com base nas métricas atuais e anteriores
         # (exemplo: calcular a diferença na taxa de processamento)
         degradation = (current_metrics['processing_rate'] - previous_metrics['processing_rate']) / previous_metrics['processing_rate'] * 100
         return degradation
   