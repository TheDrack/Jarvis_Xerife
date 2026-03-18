# -*- coding: utf-8 -*-
import random
import logging
from typing import List, Dict, Any, Optional
from app.core.nexus import Nexus

logger = logging.getLogger(__name__)

class CuriosityEngine:
    """
    Motor de Curiosidade do JARVIS.
    Responsável por identificar áreas de melhoria e proativamente sugerir evoluções.
    """

    def __init__(self, nexus: Nexus):
        self.nexus = nexus
        self.interest_areas = [
            "code_optimization", 
            "security_patching", 
            "ux_improvement", 
            "self_healing_logic",
            "documentation"
        ]

    async def generate_research_topic(self, project_context: Dict[str, Any]) -> str:
        """
        Gera um tópico de pesquisa ou melhoria baseado no estado atual do projeto.
        """
        # CORREÇÃO: Sintaxe corrigida na linha 50 (atribuição de pesos e escolha)
        weights = [0.3, 0.3, 0.1, 0.2, 0.1]
        chosen_area = random.choices(self.interest_areas, weights=weights, k=1)[0]
        
        try:
            metabolism = self.nexus.resolve("metabolism_core")
            
            prompt = (
                f"Com base no contexto do projeto: {list(project_context.keys())}. "
                f"Sugira uma tarefa de pesquisa focada em: {chosen_area}. "
                f"Seja técnico e objetivo."
            )
            
            # Chama o LLM para transformar a área num tópico concreto
            topic = await metabolism.generate_thought(prompt)
            return topic if topic else f"Exploração proativa em {chosen_area}"
            
        except Exception as e:
            logger.error(f"[Curiosity] Falha ao gerar tópico: {e}")
            return f"Análise de rotina: {chosen_area}"

    def filter_relevant_gaps(self, technical_gaps: List[str]) -> List[str]:
        """
        Filtra uma lista de lacunas técnicas mantendo apenas as que coincidem com os interesses.
        """
        if not technical_gaps:
            return []

        # CORREÇÃO: Lógica de filtragem robusta contra tipos inesperados
        relevant = []
        for gap in technical_gaps:
            if not isinstance(gap, str):
                continue
                
            gap_lower = gap.lower()
            if any(area.replace("_", " ") in gap_lower for area in self.interest_areas):
                relevant.append(gap)
        
        return relevant

    def update_interests(self, new_interests: List[str]):
        """Permite que o sistema mude o foco de curiosidade dinamicamente."""
        self.interest_areas = list(set(self.interest_areas + new_interests))
        logger.info(f"[Curiosity] Novos interesses integrados: {new_interests}")
