"""Build a concise, evidence-aware briefing for a returning user."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent, nexus


class ReconnectionBriefing(NexusComponent):
    """Summarize persisted discoveries and caller-supplied, freshly verified updates.

    The component does not query GitHub implicitly and never upgrades stale or
    missing information into a claim. The caller must supply current PR/workflow
    states obtained from an authorized live source.
    """

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = context or {}
        limit = max(1, min(int(ctx.get("limit", 5)), 10))
        include_curiosity = ctx.get("include_curiosity", True) is not False
        updates = self._items(ctx.get("verified_updates"), limit=limit)
        pull_requests = self._items(ctx.get("pull_requests"), limit=limit)
        curiosity: List[Dict[str, Any]] = []

        if include_curiosity:
            try:
                intake = nexus.resolve("curiosity_intake")
                if intake and hasattr(intake, "execute"):
                    result = intake.execute({"action": "list_recent", "limit": limit})
                    if result.get("success"):
                        curiosity = [
                            item for item in result.get("records", [])
                            if isinstance(item, dict)
                        ]
            except Exception:
                # A missing local inbox must not prevent the assistant from greeting.
                curiosity = []

        sections: List[str] = ["Olá, estou de volta. Aqui está o resumo desde nossa última interação."]
        if updates:
            sections.append("Novidades verificadas:\n" + "\n".join(
                f"- {item['title']}: {item['status']}" for item in updates
            ))
        if pull_requests:
            sections.append("Pull requests:\n" + "\n".join(
                f"- {item['title']}: {item['status']}" +
                (f" — {item['url']}" if item.get("url") else "")
                for item in pull_requests
            ))
        if curiosity:
            sections.append("Ideias e descobertas em investigação:\n" + "\n".join(
                f"- {self._title(item)} (evidência: {item.get('evidence_level', 'unverified')}; "
                f"estado: {item.get('status', 'captured')})"
                for item in curiosity
            ))
        if not updates and not pull_requests and not curiosity:
            sections.append(
                "Não encontrei novidades verificadas para relatar. Posso pesquisar o estado atual "
                "antes de afirmar que houve progresso."
            )

        return {
            "success": True,
            "message": "\n\n".join(sections),
            "verified_updates": updates,
            "pull_requests": pull_requests,
            "curiosity": curiosity,
            "claims_policy": "PR/workflow states are only reported from caller-supplied live evidence; curiosity cards are not proof of implementation.",
        }

    @classmethod
    def _items(cls, value: Any, *, limit: int) -> List[Dict[str, str]]:
        if not isinstance(value, list):
            return []
        result: List[Dict[str, str]] = []
        for raw in value:
            if not isinstance(raw, dict):
                continue
            title = cls._clean(raw.get("title") or raw.get("name"), 240)
            status = cls._clean(raw.get("status") or raw.get("conclusion") or "unverified", 80)
            url = cls._clean(raw.get("url") or raw.get("html_url"), 1000)
            if title:
                result.append({"title": title, "status": status, **({"url": url} if url else {})})
                if len(result) >= limit:
                    break
        return result

    @staticmethod
    def _title(item: Dict[str, Any]) -> str:
        return str(item.get("source_title") or item.get("observation") or "Descoberta sem título")[:240]

    @staticmethod
    def _clean(value: Any, limit: int) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.split())[:limit]
