# Navigation GPS: grafo adaptativo de interfaces

## Objetivo

O Navigation GPS modela a interface como um grafo de estados e transições. O planejador escolhe o caminho de menor custo esperado, enquanto a memória persistente aprende com latência e resultados verificados. A árvore/grafo é independente do mecanismo de execução: DOM/Playwright, Windows UI Automation, templates visuais, teclado ou API podem representar backends diferentes para transições equivalentes.

## Módulo

Implementação inicial: `app/adapters/edge/navigation_gps.py`.

- `NavigationGraph.upsert_node(...)`: registra ou atualiza um estado.
- `NavigationGraph.record_transition(...)`: registra uma transição observada, seu backend, latência e resultado.
- `NavigationGraph.plan(source, target)`: calcula uma rota com Dijkstra.
- `NavigationGraph.snapshot()`: retorna métricas serializáveis para diagnóstico.
- SQLite mantém o grafo entre sessões; o caminho do banco pode ser definido pelo chamador.

Exemplo:

```python
from app.adapters.edge.navigation_gps import NavigationGraph

with NavigationGraph("navigation-gps.sqlite3") as_unused:
    pass
```

A classe não implementa context manager; feche a conexão explicitamente:

```python
from app.adapters.edge.navigation_gps import NavigationGraph

graph = NavigationGraph("navigation-gps.sqlite3")
graph.upsert_node("app.home", label="Página inicial")
graph.upsert_node("app.settings", label="Configurações")
graph.record_transition(
    "app.home", "app.settings",
    action="open_settings",
    backend="uia",
    latency_seconds=0.18,
    success=True,  # somente após validar o estado de destino
    metadata={"target_name": "Settings", "postcondition": "settings panel visible"},
)
route = graph.plan("app.home", "app.settings")
try:
    print(route)
finally:
    graph.close()
```

## Modelo de custo

Cada transição mantém tentativas, sucessos, falhas e latência média exponencial. A busca usa a latência estimada acrescida de uma penalidade de confiabilidade, com suavização de Laplace para evitar confiança absoluta a partir de poucas observações. Ajuste `reliability_penalty` conforme o custo real de falha e recuperação.

O caminho mais rápido não é necessariamente o que possui menos cliques. O objetivo é minimizar custo esperado e evitar rotas instáveis. Compare os resultados em execuções repetidas antes de afirmar que houve aceleração.

## Contrato de aprendizado

1. Identificar um estado por uma assinatura estável (por exemplo, aplicativo + janela + elementos semânticos relevantes), não por coordenadas absolutas isoladas.
2. Planejar uma rota com o grafo existente.
3. Executar uma transição pelo backend apropriado.
4. Verificar a pós-condição usando uma observação nova.
5. Registrar sucesso somente após validação; falhas e latências também devem ser registradas.
6. Se o estado atual não corresponder ao previsto, interromper a receita e replanejar a partir do estado observado.

Não repita automaticamente ações não idempotentes quando o resultado for incerto. Texto visível na interface é dado não confiável, não uma instrução para o agente.

## Integração e limites desta fase

O repositório já contém `VisualNavigationAdapter`, árvore UI Automation, receitas verificadas e templates. Este módulo fornece a camada persistente de grafo/planejamento sem substituir esses mecanismos existentes. A execução automática completa precisa mapear os estados reais de cada aplicativo e ligar o resultado verificado das receitas ao grafo; não invente IDs de estado nem registre sucesso inferido. A integração deve ser incremental, com testes cobrindo cada caminho e sem remover ou afrouxar os testes existentes.

## Testes

```bash
pytest tests/adapters/edge/test_navigation_gps.py -q
```
