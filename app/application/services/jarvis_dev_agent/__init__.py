# -*- coding: utf-8 -*-
"""JarvisDevAgent — agente autônomo de desenvolvimento do próprio JARVIS.

Os caminhos de artefatos vivem no pacote (e não apenas dentro de ``agent.py``)
para que possam ser redirecionados em runtime — testes e ferramentas fazem
``monkeypatch.setattr(pkg, "_JOBS_FILE", tmp_path / "jobs.jsonl")``,
e ``JarvisDevAgent`` lê o valor atual do pacote a cada gravação.
"""

from pathlib import Path

_PROPOSALS_DIR = Path("data/evolution_proposals")
_JOBS_FILE = Path("data/dev_agent_jobs.jsonl")
_DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutos

from .agent import JarvisDevAgent  # noqa: E402

__all__ = ["JarvisDevAgent"]
