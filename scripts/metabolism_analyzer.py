# -*- coding: utf-8 -*-
import argparse, json, logging, os, sys
from pathlib import Path
from typing import Dict, Any
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.application.services.metabolism_core import MetabolismCore

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("MecanicoRevisionador")

class EscalationReason(Enum):
    INSUFFICIENT_INFORMATION = "Informação insuficiente para análise segura"
    ARCHITECTURAL_JUDGMENT = "Requer julgamento arquitetural humano"
    CRITICAL_RISK = "Risco crítico detectado no DNA"

class MetabolismAnalyzer:
    def __init__(self):
        self.core = MetabolismCore()
        self.min_context_length = 5

    def analyze_event(self, intent: str, instruction: str, context: str) -> Dict[str, Any]:
        full_context = f"Instrução: {instruction}\nContexto: {context}"
        if len(full_context) < self.min_context_length:
            return self._escalate(EscalationReason.INSUFFICIENT_INFORMATION)

        if any(kw in full_context.lower() for kw in ['database', 'schema', 'auth', 'delete']):
            return self._escalate(EscalationReason.ARCHITECTURAL_JUDGMENT)

        system_p = "Você é o Mecânico do JARVIS. Responda APENAS JSON: {'requires_human': bool, 'reason': str, 'risk_level': int}"
        user_p = f"INTENÇÃO: {intent}\nPROPOSTA: {full_context}"

        try:
            analysis = self.core.ask_jarvis(system_p, user_p)
            self._export_to_gh(analysis)
            return analysis
        except Exception:
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
    p = argparse.ArgumentParser()
    p.add_argument('--intent', required=True)
    p.add_argument('--instruction', required=True)
    p.add_argument('--context', default='')
    args = p.parse_args()
    print(json.dumps(MetabolismAnalyzer().analyze_event(args.intent, args.instruction, args.context)))
