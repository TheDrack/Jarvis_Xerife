# -*- coding: utf-8 -*-
import json
import sys
import argparse
from pathlib import Path


class CapabilityAnalyzer:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def analyze(self, capability: dict) -> dict:
        """
        Retorna:
        {
          decision: AUTO | REQUIRES_HUMAN,
          reason: str
        }
        """

        title = capability.get("title", "").lower()
        notes = capability.get("notes", "").lower()
        description = capability.get("description", "").lower()

        # 🔒 HARD BLOCKS — nunca auto
        human_keywords = [
            "economic",
            "revenue",
            "payment",
            "self-protection",
            "protect itself",
            "protect the user",
            "human validation",
            "financial",
            "security",
            "credential",
            "token",
            "permission"
        ]

        for kw in human_keywords:
            if kw in title or kw in description or kw in notes:
                return {
                    "decision": "REQUIRES_HUMAN",
                    "reason": f"Keyword '{kw}' requires human validation"
                }

        # 🔬 SAFE AUTO — engenharia pura
        auto_keywords = [
            "maintain",
            "detect",
            "identify",
            "classify",
            "log",
            "monitor",
            "document",
            "map",
            "validate",
            "test",
            "analyze"
        ]

        for kw in auto_keywords:
            if kw in title:
                return {
                    "decision": "AUTO",
                    "reason": f"Engineering task detected via keyword '{kw}'"
                }

        # ⚠️ fallback conservador
        return {
            "decision": "REQUIRES_HUMAN",
            "reason": "Unable to safely classify capability"
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capability", required=True, help="JSON string da capability")
    parser.add_argument("--repo-path", default=".")
    args = parser.parse_args()

    capability = json.loads(args.capability)
    analyzer = CapabilityAnalyzer(Path(args.repo_path))
    result = analyzer.analyze(capability)

    # saída limpa para GitHub Actions
    print(json.dumps(result))