# -*- coding: utf-8 -*-
"""
GitHub Copilot Integration for Repository Context

This module integrates with GitHub Copilot to provide intelligent context
about the repository structure, code patterns, and best practices to GitHub Agents.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class GitHubCopilotContextProvider:
    """
    Provides repository context to GitHub Agents using LLM-based analysis.
    
    This class analyzes the repository structure and generates context that helps
    GitHub Agents (like Jarvis Auto-Fixer) make better decisions when creating
    pull requests or fixing issues.
    """
    
    def __init__(self, ai_gateway=None, repository_root: Optional[Path] = None):
        """
        Initialize GitHub Copilot context provider
        
        Args:
            ai_gateway: AI Gateway instance for LLM integration
            repository_root: Root directory of the repository
        """
        self.ai_gateway = ai_gateway
        self.repository_root = repository_root or Path.cwd()
        
        if not self.ai_gateway:
            logger.warning("No AI Gateway provided for Copilot context generation")
    
    async def generate_repository_context(self) -> Dict[str, Any]:
        """
        Generate comprehensive repository context for GitHub Agents
        
        Returns:
            Dictionary containing:
            - architecture: High-level architecture description
            - key_patterns: Important code patterns and conventions
            - folder_structure: Folder organization and purpose
            - integration_points: Where to integrate new features
            - testing_strategy: How to test changes
            - best_practices: Repository-specific best practices
        """
        if not self.ai_gateway:
            return self._fallback_context()
        
        try:
            # Gather repository information
            repo_info = self._gather_repository_info()
            
            # Use LLM to analyze and generate context
            context = await self._llm_analyze_repository(repo_info)
            
            return context
            
        except Exception as e:
            logger.error(f"Failed to generate repository context: {e}", exc_info=True)
            return self._fallback_context()
    
    def _gather_repository_info(self) -> Dict[str, Any]:
        """Gather information about the repository"""
        info = {
            "name": self.repository_root.name,
            "structure": self._analyze_folder_structure(),
            "readme": self._read_readme(),
            "architecture_docs": self._find_architecture_docs(),
            "key_files": self._identify_key_files(),
        }
        return info
    
    def _analyze_folder_structure(self) -> Dict[str, str]:
        """Analyze folder structure"""
        structure = {}
        
        # Common important directories
        important_dirs = [
            "app", "src", "lib",
            "tests", "test",
            "docs", "documentation",
            "scripts", "tools",
            ".github",
        ]
        
        for dir_name in important_dirs:
            dir_path = self.repository_root / dir_name
            if dir_path.exists() and dir_path.is_dir():
                # Count files and get brief description
                file_count = sum(1 for _ in dir_path.rglob("*.py"))
                structure[dir_name] = f"{file_count} Python files"
        
        return structure
    
    def _read_readme(self) -> Optional[str]:
        """Read README file"""
        for readme_name in ["README.md", "README.rst", "README.txt", "README"]:
            readme_path = self.repository_root / readme_name
            if readme_path.exists():
                try:
                    with open(readme_path, 'r', encoding='utf-8') as f:
                        # Read first 5000 chars to avoid token overflow
                        return f.read(5000)
                except Exception as e:
                    logger.warning(f"Failed to read README: {e}")
        return None
    
    def _find_architecture_docs(self) -> List[str]:
        """Find architecture documentation"""
        arch_docs = []
        
        docs_dir = self.repository_root / "docs"
        if docs_dir.exists():
            for doc_file in docs_dir.rglob("*.md"):
                name_lower = doc_file.name.lower()
                if any(keyword in name_lower for keyword in ["architecture", "design", "structure"]):
                    arch_docs.append(str(doc_file.relative_to(self.repository_root)))
        
        return arch_docs
    
    def _identify_key_files(self) -> List[str]:
        """Identify key configuration and entry point files"""
        key_files = []
        
        # Common key files
        patterns = [
            "setup.py", "pyproject.toml", "requirements.txt",
            "main.py", "app.py", "__init__.py",
            "config.py", "settings.py",
            "Dockerfile", "docker-compose.yml",
            ".github/workflows/*.yml"
        ]
        
        for pattern in patterns:
            if "*" in pattern:
                # Use glob pattern
                for file_path in self.repository_root.glob(pattern):
                    if file_path.is_file():
                        key_files.append(str(file_path.relative_to(self.repository_root)))
            else:
                file_path = self.repository_root / pattern
                if file_path.exists():
                    key_files.append(pattern)
        
        return key_files
    
    async def _llm_analyze_repository(self, repo_info: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to analyze repository and generate context"""
        
        # Build analysis prompt
        prompt = f"""Analyze this repository and provide context for GitHub Agents:

**Repository Name**: {repo_info['name']}

**Folder Structure**:
{json.dumps(repo_info['structure'], indent=2)}

**README Content**:
{repo_info['readme'][:3000] if repo_info['readme'] else 'No README found'}

**Architecture Docs**: {', '.join(repo_info['architecture_docs']) if repo_info['architecture_docs'] else 'None found'}

**Key Files**: {', '.join(repo_info['key_files'][:10])}

Based on this information, provide a comprehensive analysis in JSON format:

{{
  "architecture": "High-level architecture description (Hexagonal, MVC, etc.)",
  "key_patterns": ["pattern 1", "pattern 2"],
  "folder_purposes": {{
    "folder_name": "purpose and what to add here"
  }},
  "integration_points": ["where to add new features"],
  "testing_strategy": "How tests are organized and run",
  "best_practices": ["practice 1", "practice 2"],
  "code_conventions": ["convention 1", "convention 2"]
}}

Be specific and actionable. This will guide automated agents in making changes.
"""
        
        messages = [
            {
                "role": "system",
                "content": "You are a software architecture expert. Analyze repositories and provide actionable guidance."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Get LLM response
        result = await self.ai_gateway.generate_completion(
            messages=messages,
            functions=None,
            multimodal=False,
        )
        
        # Extract and parse response
        response_text = self._extract_response_text(result)
        if not response_text:
            logger.warning("Empty response from LLM for repository analysis")
            return self._fallback_context()
        
        # Parse LLM response
        return self._parse_llm_response(response_text)
    
    def _extract_response_text(self, result: dict) -> Optional[str]:
        """Extract response text from AI Gateway result"""
        provider = result.get("provider")
        response = result.get("response")
        
        if provider == "groq":
            if hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                if hasattr(choice, "message") and hasattr(choice.message, "content"):
                    return choice.message.content
        
        elif provider == "gemini":
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            return part.text.strip()
        
        return None
    
    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """Parse LLM JSON response"""
        try:
            # Clean up response to extract JSON
            json_text = response_text.strip()
            if json_text.startswith("```"):
                json_text = json_text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
                json_text = json_text.strip()
            
            context = json.loads(json_text)
            
            logger.info("Successfully generated repository context using LLM")
            return context
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Response was: {response_text[:500]}")
            return self._fallback_context()
    
    def _fallback_context(self) -> Dict[str, Any]:
        """Fallback context when LLM is unavailable"""
        return {
            "architecture": "Unknown - LLM analysis not available",
            "key_patterns": ["Follow existing code patterns in the repository"],
            "folder_purposes": {
                "app": "Main application code",
                "tests": "Test files",
                "docs": "Documentation",
                "scripts": "Utility scripts"
            },
            "integration_points": ["Check existing code for integration examples"],
            "testing_strategy": "Run pytest for tests",
            "best_practices": ["Maintain code quality", "Add tests for new features"],
            "code_conventions": ["Follow PEP 8 for Python code"]
        }
    
    async def generate_context_for_issue(self, issue_description: str) -> Dict[str, Any]:
        """
        Generate context specific to an issue or feature request
        
        Args:
            issue_description: Description of the issue or feature
            
        Returns:
            Context dictionary with specific guidance for the issue
        """
        if not self.ai_gateway:
            return self._fallback_issue_context(issue_description)
        
        try:
            # Get general repository context first
            repo_context = await self.generate_repository_context()
            
            # Generate issue-specific context
            prompt = f"""Given this repository context:
{json.dumps(repo_context, indent=2)}

And this issue/feature request:
{issue_description}

Provide specific guidance for GitHub Agents to address this issue:

{{
  "affected_areas": ["area 1", "area 2"],
  "files_to_modify": ["file1.py", "file2.py"],
  "files_to_create": ["new_file.py"],
  "testing_approach": "How to test this change",
  "implementation_notes": ["note 1", "note 2"],
  "related_code_patterns": ["pattern to follow"],
  "potential_risks": ["risk 1", "risk 2"]
}}
"""
            
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert at analyzing software issues and providing implementation guidance."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            result = await self.ai_gateway.generate_completion(
                messages=messages,
                functions=None,
                multimodal=False,
            )
            
            response_text = self._extract_response_text(result)
            if response_text:
                return self._parse_llm_response(response_text)
            
            return self._fallback_issue_context(issue_description)
            
        except Exception as e:
            logger.error(f"Failed to generate issue context: {e}", exc_info=True)
            return self._fallback_issue_context(issue_description)
    
    def _fallback_issue_context(self, issue_description: str) -> Dict[str, Any]:
        """Fallback issue context"""
        return {
            "affected_areas": ["Analyze code manually to determine affected areas"],
            "files_to_modify": ["Identify files based on issue description"],
            "files_to_create": [],
            "testing_approach": "Add tests for any new functionality",
            "implementation_notes": ["Follow repository conventions", "Maintain backward compatibility"],
            "related_code_patterns": ["Check similar features in the codebase"],
            "potential_risks": ["Test thoroughly before merging"]
        }
    
    def save_context_for_github_agents(
        self, 
        context: Dict[str, Any], 
        output_file: Optional[Path] = None
    ) -> Path:
        """
        Save context to a JSON file for GitHub Agents to read
        
        Args:
            context: Context dictionary to save
            output_file: Optional output file path (defaults to .github/repository_context.json)
            
        Returns:
            Path to the saved context file
        """
        if output_file is None:
            output_file = self.repository_root / ".github" / "repository_context.json"
        
        # Ensure directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Save context
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(context, f, indent=2)
        
        logger.info(f"Repository context saved to {output_file}")
        return output_file
