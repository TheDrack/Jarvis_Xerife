import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from app.core.interfaces import NexusComponent

class PerformanceAnalyzer(NexusComponent):
    """
    Setor: Domain/Analysis
    Responsabilidade Única: Lógica matemática de análise de degradação.
    Note: Não carrega arquivos, recebe DataFrames.
    """
    def __init__(self):
        self.model = RandomForestRegressor()

    def execute(self, data: pd.DataFrame, target_column: str = 'target'):
        X = data.drop(target_column, axis=1)
        y = data[target_column]
        self.model.fit(X, y)
        return self.model.feature_importances_
