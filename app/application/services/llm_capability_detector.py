# -*- coding: utf-8 -*-
"""
LLM-based Capability Detector - Uses AI to detect implemented capabilities

This detector replaces keyword-based file scanning with LLM-based code understanding,
providing more accurate capability detection by analyzing code semantics rather than
just looking for keywords.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.adapters.infrastructure.ai_gateway import LLMProvider
from app.core.llm_config import LLMConfig

logger = logging.getLogger(__name__)


class LLMCapabilityDetector:
    """
    Detects implemented capabilities using LLM to analyze code semantics.
    
    This provides more accurate detection than keyword-based scanning because:
    - LLM understands code context and intent
    - Can identify functionality even with different naming conventions
    - Recognizes partial implementations vs complete implementations
    - Can assess code quality and completeness
    """
    
    # Maximum characters to include in LLM prompt to avoid token overflow
    # Approximate: 1 token ≈ 4 characters, so 8000 chars ≈ 2000 tokens
    MAX_CODE_CONTEXT_CHARS = 8000
    
    def __init__(self, ai_gateway=None, repository_root: Optional[Path] = None):
        """
        Initialize the LLM capability detector
        
        Args:
            ai_gateway: AI Gateway instance for LLM integration
            repository_root: Root directory of the repository (defaults to current working directory)
        """
        self.ai_gateway = ai_gateway
        self.repository_root = repository_root or Path.cwd()
        self._forced_provider = self._resolve_provider(LLMConfig.CAPABILITY_LLM_PROVIDER)
        
        if not self.ai_gateway:
            logger.warning("No AI Gateway provided for LLM capability detection")
    
    async def detect_capability_async(
        self, 
        capability_id: int,
        capability_name: str,
        capability_description: str,
        related_files: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Detect if a capability is implemented using LLM analysis
        
        Args:
            capability_id: ID of the capability
            capability_name: Name of the capability
            capability_description: Description of what the capability does
            related_files: Optional list of files to check (if None, scans common locations)
            
        Returns:
            Dictionary with:
            - status: "complete", "partial", or "nonexistent"
            - confidence: 0.0-1.0 confidence score
            - evidence: List of evidence supporting the status
            - files_found: List of files containing related code
            - recommendations: List of recommendations for improvement
        """
        if not self.ai_gateway:
            return self._fallback_detection(capability_name)
        
        try:
            # Gather code context
            code_context = await self._gather_code_context(
                capability_name, 
                capability_description,
                related_files
            )
            
            # Ask LLM to analyze if capability is implemented
            analysis = await self._llm_analyze_capability(
                capability_id,
                capability_name,
                capability_description,
                code_context
            )
            
            return analysis
            
        except Exception as e:
            logger.error(f"LLM capability detection failed: {e}", exc_info=True)
            return self._fallback_detection(capability_name)
    
    async def _gather_code_context(
        self,
        capability_name: str,
        capability_description: str,
        related_files: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Gather relevant code files for LLM analysis
        
        Args:
            capability_name: Name of the capability
            capability_description: Description of the capability
            related_files: Optional list of specific files to check
            
        Returns:
            Dictionary mapping file paths to their content
        """
        code_context = {}
        
        if related_files:
            # Use provided files
            for file_path in related_files:
                full_path = self.repository_root / file_path
                if full_path.exists():
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            code_context[file_path] = f.read()
                    except Exception as e:
                        logger.warning(f"Failed to read {file_path}: {e}")
        else:
            # Search for related files using keywords from capability name
            keywords = self._extract_keywords(capability_name, capability_description)
            code_context = self._search_files_by_keywords(keywords)
        
        return code_context
    
    def _extract_keywords(self, name: str, description: str) -> List[str]:
        """Extract search keywords from capability name and description"""
        # Simple keyword extraction - in production, could use LLM for this too
        keywords = []
        
        # Extract words from name
        name_words = name.lower().replace('-', ' ').replace('_', ' ').split()
        keywords.extend([w for w in name_words if len(w) > 3])
        
        # Extract key terms from description
        if description:
            desc_words = description.lower().split()
            keywords.extend([w for w in desc_words if len(w) > 5][:3])
        
        return list(set(keywords))
    
    def _search_files_by_keywords(self, keywords: List[str], max_files: int = 5) -> Dict[str, str]:
        """
        Search repository for files containing keywords
        
        Args:
            keywords: List of keywords to search for
            max_files: Maximum number of files to return
            
        Returns:
            Dictionary mapping file paths to content
        """
        code_context = {}
        
        # Search in common Python directories
        search_dirs = [
            self.repository_root / "app",
            self.repository_root / "scripts",
        ]
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            
            for py_file in search_dir.rglob("*.py"):
                if len(code_context) >= max_files:
                    break
                
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    # Check if any keyword appears in the file
                    content_lower = content.lower()
                    if any(keyword in content_lower for keyword in keywords):
                        rel_path = str(py_file.relative_to(self.repository_root))
                        code_context[rel_path] = content
                        
                except Exception as e:
                    logger.debug(f"Skipping {py_file}: {e}")
        
        return code_context
    
    async def _llm_analyze_capability(
        self,
        capability_id: int,
        capability_name: str,
        capability_description: str,
        code_context: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Use LLM to analyze if capability is implemented
        
        Args:
            capability_id: Capability ID
            capability_name: Capability name
            capability_description: Capability description
            code_context: Dictionary of file paths to code content
            
        Returns:
            Analysis results
        """
        # Build analysis prompt
        prompt = self._build_analysis_prompt(
            capability_id,
            capability_name,
            capability_description,
            code_context
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are a code analysis expert. Analyze code to determine if a capability is implemented."
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
            force_provider=self._forced_provider,
        )
        
        # Extract and parse response
        response_text = self._extract_response_text(result)
        if not response_text:
            logger.warning("Empty response from LLM")
            return self._fallback_detection(capability_name)
        
        # Parse LLM response
        return self._parse_llm_analysis(response_text, capability_name)
    
    def _build_analysis_prompt(
        self,
        capability_id: int,
        capability_name: str,
        capability_description: str,
        code_context: Dict[str, str]
    ) -> str:
        """Build analysis prompt for LLM"""
        # Limit code context to avoid token overflow
        context_summary = []
        total_chars = 0
        
        for file_path, content in code_context.items():
            if total_chars >= self.MAX_CODE_CONTEXT_CHARS:
                context_summary.append(f"\n... ({len(code_context) - len(context_summary)} more files omitted)")
                break
            
            # Truncate long files
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
    
    def _parse_llm_analysis(self, response_text: str, capability_name: str) -> Dict[str, Any]:
        """Parse LLM analysis response"""
        try:
            # Clean up response to extract JSON
            json_text = response_text.strip()
            if json_text.startswith("```"):
                json_text = json_text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
                json_text = json_text.strip()
            
            analysis = json.loads(json_text)
            
            # Validate required fields
            required = ["status", "confidence"]
            if not all(field in analysis for field in required):
                logger.error(f"Missing required fields in LLM response: {analysis}")
                return self._fallback_detection(capability_name)
            
            # Validate status value
            valid_statuses = ["complete", "partial", "nonexistent"]
            if analysis["status"] not in valid_statuses:
                logger.error(f"Invalid status from LLM: {analysis['status']}")
                return self._fallback_detection(capability_name)
            
            logger.info(
                f"LLM detected capability '{capability_name}' as {analysis['status']} "
                f"with {analysis['confidence']:.2f} confidence"
            )
            
            return analysis
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse LLM analysis: {e}")
            logger.error(f"Response was: {response_text}")
            return self._fallback_detection(capability_name)
    
    def _fallback_detection(self, capability_name: str) -> Dict[str, Any]:
        """Fallback detection when LLM is unavailable"""
        return {
            "status": "nonexistent",
            "confidence": 0.3,
            "evidence": ["LLM analysis not available, using fallback"],
            "files_found": [],
            "recommendations": ["Enable AI Gateway for accurate capability detection"]
        }

    def _resolve_provider(self, provider_setting: str) -> Optional[LLMProvider]:
        """Resolve provider based on configuration"""
        provider_setting = provider_setting.lower()
        if provider_setting == "groq":
            return LLMProvider.GROQ
        if provider_setting == "gemini":
            return LLMProvider.GEMINI
        return None


class EnhancedCapabilityManager:
    """
    Enhanced Capability Manager that uses LLM for capability detection.
    
    This wraps the existing CapabilityManager and adds LLM-based detection
    capabilities while maintaining backward compatibility.
    """
    
    def __init__(self, base_manager, ai_gateway=None):
        """
        Initialize enhanced capability manager
        
        Args:
            base_manager: Existing CapabilityManager instance
            ai_gateway: AI Gateway for LLM integration
        """
        self.base_manager = base_manager
        self.llm_detector = LLMCapabilityDetector(ai_gateway=ai_gateway)
    
    async def enhanced_status_scan(self) -> Dict[str, Any]:
        """
        Enhanced status scan using LLM for capability detection
        
        Returns:
            Dictionary with scan results including LLM insights
        """
        from sqlmodel import Session, select
        from app.domain.models.capability import JarvisCapability
        from app.core.llm_config import LLMConfig
        
        logger.info("Starting enhanced LLM-based capability status scan...")
        
        updated_capabilities = []
        max_scan = LLMConfig.MAX_CAPABILITIES_PER_SCAN
        
        with Session(self.base_manager.engine) as session:
            capabilities = session.exec(select(JarvisCapability)).all()
            
            # Limit to configured maximum to manage costs
            for capability in capabilities[:max_scan]:
                try:
                    # Use LLM to detect capability status
                    analysis = await self.llm_detector.detect_capability_async(
                        capability_id=capability.id,
                        capability_name=capability.capability_name,
                        capability_description=getattr(capability, 'description', '')
                    )
                    
                    new_status = analysis.get("status")
                    confidence = analysis.get("confidence", 0.0)
                    
                    # Only update if LLM is confident
                    if confidence >= LLMConfig.MIN_CAPABILITY_CONFIDENCE and new_status and new_status != capability.status:
                        logger.info(
                            f"Updating capability {capability.id}: "
                            f"{capability.status} -> {new_status} "
                            f"(confidence: {confidence:.2f})"
                        )
                        
                        old_status = capability.status
                        capability.status = new_status
                        
                        updated_capabilities.append({
                            "id": capability.id,
                            "name": capability.capability_name,
                            "old_status": old_status,
                            "new_status": new_status,
                            "confidence": confidence,
                            "evidence": analysis.get("evidence", []),
                            "recommendations": analysis.get("recommendations", [])
                        })
                    
                except Exception as e:
                    logger.error(f"Error analyzing capability {capability.id}: {e}")
            
            # Commit changes
            session.commit()
            
            # Generate summary
            all_capabilities = session.exec(select(JarvisCapability)).all()
            status_counts = {
                "nonexistent": sum(1 for c in all_capabilities if c.status == "nonexistent"),
                "partial": sum(1 for c in all_capabilities if c.status == "partial"),
                "complete": sum(1 for c in all_capabilities if c.status == "complete"),
            }
            
            logger.info(f"Enhanced scan complete. Updated {len(updated_capabilities)} capabilities.")
            logger.info(f"Scanned {min(max_scan, len(capabilities))} of {len(capabilities)} total capabilities")
            
            return {
                "total_capabilities": len(all_capabilities),
                "scanned_capabilities": min(max_scan, len(capabilities)),
                "nonexistent": status_counts["nonexistent"],
                "partial": status_counts["partial"],
                "complete": status_counts["complete"],
                "updated": updated_capabilities,
                "llm_powered": True
            }
