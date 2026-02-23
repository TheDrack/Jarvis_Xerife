
import sys

import json

from typing import List, Dict



class MissionSelector:

    def __init__(self, objectives: List[Dict]):

        self.objectives = objectives

        self.sorted_objectives = self.sort_by_systemic_impact()

        self.sorted_objectives_by_name = self.sort_by_name()

        self.sorted_objectives_by_systemic_impact_and_name = self.sort_by_systemic_impact_and_name()

    

    def sort_by_systemic_impact(self) -> List[Dict]:

        # Implementação da lógica de ordenação por impacto sistêmico

        return sorted(self.objectives, key=lambda x: x['systemic_impact'], reverse=True)

    

    def sort_by_name(self) -> List[Dict]:

        # Implementação da lógica de ordenação por nome

        return sorted(self.objectives, key=lambda x: x['name'])

    

    def sort_by_systemic_impact_and_name(self) -> List[Dict]:

        # Implementação da lógica de ordenação por impacto sistêmico e nome

        return sorted(self.objectives, key=lambda x: (x['systemic_impact'], x['name']), reverse=True)

    

    def get_sorted_objectives(self, sort_type: str) -> List[Dict]:

        if sort_type == 'systemic_impact':

            return self.sorted_objectives

        elif sort_type == 'name':

            return self.sorted_objectives_by_name

        elif sort_type == 'systemic_impact_and_name':

            return self.sorted_objectives_by_systemic_impact_and_name

        else:

            return []



# Exemplo de uso:

objectives = [

    {'name': 'Objetivo 1', 'systemic_impact': 5},

    {'name': 'Objetivo 2', 'systemic_impact': 3},

    {'name': 'Objetivo 3', 'systemic_impact': 8}

]



mission_selector = MissionSelector(objectives)

sorted_objectives = mission_selector.get_sorted_objectives('systemic_impact_and_name')



for objective in sorted_objectives:

    print(objective['name'], objective['systemic_impact'])

