
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error

class MonitorPerformanceDegradation:
    def __init__(self, data):
        self.data = data

    def load_data(self):
        return pd.read_csv(self.data)

    def split_data(self):
        data = self.load_data()
        X = data.drop('target', axis=1)
        y = data['target']
        return train_test_split(X, y, test_size=0.2, random_state=42)

    def train_model(self, X_train, y_train):
        model = RandomForestRegressor()
        model.fit(X_train, y_train)
        return model

    def evaluate_model(self, model, X_test, y_test):
        y_pred = model.predict(X_test)
        return mean_squared_error(y_test, y_pred)

    def monitor_performance(self):
        X_train, X_test, y_train, y_test = self.split_data()
        model = self.train_model(X_train, y_train)
        mse = self.evaluate_model(model, X_test, y_test)
        return mse

# Usage
data = 'path_to_your_data.csv'
monitor = MonitorPerformanceDegradation(data)
mse = monitor.monitor_performance()
print(f'Mean Squared Error: {mse}}