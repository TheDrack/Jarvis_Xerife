# -*- coding: utf-8 -*-
import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any
from enum import Enum

# Adiciona o diretório raiz ao path para importar o core
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.application.services.metabolism_core import MetabolismCore

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("MecanicoRevisionador")

class EscalationReason(Enum):
    BUSINESS_DECISION = "Decisão de negócio necessária"
    ARCHITECTURAL_JUDGMENT = "Requer julgamento arquitetural humano"
    INSUFFICIENT_INFORMATION = "Informação insuficiente para análise segura"
    CRITICAL_RISK = "Risco crítico detectado no DNA"

class MetabolismAnalyzer:
    def __init__(self, repo_path: str = None):
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.core = MetabolismCore()
        # Calibração JARVIS: Reduzido de 100 para 10 para evitar falsos positivos de 'falta de contexto'
        self.min_context_length = 10

    def analyze_event(self, intent: str, instruction: str, context: str) -> Dict[str, Any]:
        logger.info("🔬 Iniciando vistoria técnica do Mecânico Revisionador...")

        full_context = f"Instrução: {instruction}\nContexto: {context}"

        # 1. Verificação de Contexto Mínimo
        if len(full_context) < self.min_context_length:
            return self._escalate(EscalationReason.INSUFFICIENT_INFORMATION)

        # 2. Filtros de Segurança (Hardcoded para performance)
        if any(kw in full_context.lower() for kw in ['database', 'schema', 'security', 'auth', 'delete']):
            return self._escalate(EscalationReason.ARCHITECTURAL_JUDGMENT)

        # 3. Consulta ao Cérebro (IA) para Análise de Risco
        system_p = (
            "Você é o Mecânico Revisionador do JARVIS. Analise a proposta de mudança e determine se "
            "ela é segura para aplicação automática ou se exige intervenção humana (Comandante). "
            "Responda APENAS JSON com: 'requires_human' (boolean), 'reason' (string) e 'risk_level' (0-10)."
        )
        user_p = f"INTENÇÃO: {intent}\n\nPROPOSTA:\n{full_context}"

        try:
            analysis = self.core.ask_jarvis(system_p, user_p)
            self._export_to_gh(analysis)

            return {
                "requires_human": analysis.get("requires_human", True),
                "reason": analysis.get("reason", "Análise inconclusiva"),
                "risk_level": analysis.get("risk_level", 10)
            }
        except Exception as e:
            logger.error(f"Erro na análise de IA: {e}")
            return self._escalate(EscalationReason.CRITICAL_RISK)

    def _escalate(self, reason: EscalationReason) -> Dict[str, Any]:
        res = {"requires_human": True, "reason": reason.value, "risk_level": 10}
        self._export_to_gh(res)
        return res

    def _export_to_gh(self, result: Dict[str, Any]):
        gh_output = os.getenv('GITHUB_OUTPUT')
        if gh_output:
            with open(gh_output, 'a') as f:
                f.write(f"requires_human={str(result['requires_human']).lower()}\n")
                f.write(f"escalation_reason={result.get('reason', '')}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--intent', required=True)
    parser.add_argument('--instruction', required=True)
    parser.add_argument('--context', default='')
    parser.add_argument('--repo-path', default=None)

    args = parser.parse_args()
    analyzer = MetabolismAnalyzer(repo_path=args.repo_path)
    result = analyzer.analyze_event(args.intent, args.instruction, args.context)
    print(json.dumps(result, indent=2))
    sys.exit(0)
