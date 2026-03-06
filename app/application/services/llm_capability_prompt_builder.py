from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Prompt building utilities for LLM capability detection."""

import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

MAX_CODE_CONTEXT_CHARS = 8000


def extract_keywords(name: str, description: str) -> List[str]:
    """Extract search keywords from capability name and description."""
    keywords = []
    name_words = name.lower().replace('-', ' ').replace('_', ' ').split()
    keywords.extend([w for w in name_words if len(w) > 3])
    if description:
        desc_words = description.lower().split()
        keywords.extend([w for w in desc_words if len(w) > 5][:3])
    return list(set(keywords))


def search_files_by_keywords(
    repository_root: Path,
    keywords: List[str],
    max_files: int = 5,
) -> Dict[str, str]:
    """Search repository for files containing keywords.

    Args:
        repository_root: Root directory of the repository.
        keywords: Keywords to search for.
        max_files: Maximum number of files to return.

    Returns:
        Dictionary mapping file paths to content.
    """
    code_context: Dict[str, str] = {}
    search_dirs = [repository_root / "app", repository_root / "scripts"]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for py_file in search_dir.rglob("*.py"):
            if len(code_context) >= max_files:
                break
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                content_lower = content.lower()
                if any(keyword in content_lower for keyword in keywords):
                    rel_path = str(py_file.relative_to(repository_root))
                    code_context[rel_path] = content
            except Exception as e:
                logger.debug(f"Skipping {py_file}: {e}")
    return code_context


def build_analysis_prompt(
    capability_id: int,
    capability_name: str,
    capability_description: str,
    code_context: Dict[str, str],
    max_chars: int = MAX_CODE_CONTEXT_CHARS,
) -> str:
    """Build analysis prompt for LLM capability detection."""
    context_summary = []
    total_chars = 0

    for file_path, content in code_context.items():
        if total_chars >= max_chars:
            context_summary.append(
                f"\n... ({len(code_context) - len(context_summary)} more files omitted)"
            )
            break
        if len(content) > 2000:
            content = content[:2000] + "\n... (truncated)"
        context_summary.append(f"\n### File: {file_path}\n```python\n{content}\n```")
        total_chars += len(content)

    context_str = "".join(context_summary) if context_summary else "No related code files found"

    return f"""Analyze if the following capability is implemented in the codebase:

**Capability ID**: {capability_id}
**Capability Name**: {capability_name}
**Description**: {capability_description}

**Code Context**:
{context_str}

**Analysis Task**:
Determine if this capability is:
- **complete**: Fully implemented, tested, and production-ready
- **partial**: Partially implemented or has significant limitations
- **nonexistent**: Not implemented at all

Respond ONLY in JSON format:
{{
  "status": "complete|partial|nonexistent",
  "confidence": 0.0-1.0,
  "evidence": ["evidence point 1", "evidence point 2"],
  "files_found": ["file1.py", "file2.py"],
  "recommendations": ["recommendation 1", "recommendation 2"]
}}

Be conservative - only mark as "complete" if you see clear, working implementation.
"""


class LLMCapabilityPromptBuilder(NexusComponent):
    """NexusComponent wrapper for LLM capability prompt building utilities."""

    def execute(self, context: dict) -> dict:
        capability_id = context.get("capability_id", 0)
        capability_name = context.get("capability_name", "")
        capability_description = context.get("capability_description", "")
        code_context = context.get("code_context", {})
        prompt = build_analysis_prompt(
            capability_id, capability_name, capability_description, code_context
        )
        return {"success": True, "prompt": prompt}
