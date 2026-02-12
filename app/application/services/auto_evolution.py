# -*- coding: utf-8 -*-
"""Auto Evolution Service - Self-improvement system for JARVIS"""

import logging
import re
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class AutoEvolutionService:
    """
    Service for managing JARVIS auto-evolution based on ROADMAP.md.
    
    This service implements the self-evolution loop:
    1. Parses ROADMAP.md to find next achievable mission
    2. Attempts to implement the mission
    3. Integrates with EvolutionLoopService for rewards/punishments
    
    The service prioritizes missions marked as:
    - 🔄 (in progress) - highest priority
    - 📋 (planned) - secondary priority
    - ✅ (completed) - skipped
    """
    
    def __init__(self, roadmap_path: Optional[str] = None):
        """
        Initialize the auto evolution service.
        
        Args:
            roadmap_path: Path to ROADMAP.md (defaults to docs/ROADMAP.md)
        """
        if roadmap_path:
            self.roadmap_path = Path(roadmap_path)
        else:
            # Default to docs/ROADMAP.md relative to project root
            self.roadmap_path = Path(__file__).parent.parent.parent.parent / "docs" / "ROADMAP.md"
        
        logger.info(f"AutoEvolutionService initialized with roadmap: {self.roadmap_path}")
    
    def parse_roadmap(self) -> Dict[str, Any]:
        """
        Parse the ROADMAP.md file to extract missions and their status.
        
        Returns:
            Dictionary with roadmap structure and missions
        """
        if not self.roadmap_path.exists():
            logger.error(f"Roadmap file not found: {self.roadmap_path}")
            return {
                'error': 'Roadmap file not found',
                'sections': []
            }
        
        try:
            content = self.roadmap_path.read_text(encoding='utf-8')
            sections = self._parse_sections(content)
            
            logger.info(f"Parsed roadmap with {len(sections)} sections")
            return {
                'roadmap_path': str(self.roadmap_path),
                'sections': sections,
                'total_sections': len(sections)
            }
        except Exception as e:
            logger.error(f"Error parsing roadmap: {e}")
            return {
                'error': str(e),
                'sections': []
            }
    
    def _parse_sections(self, content: str) -> List[Dict[str, Any]]:
        """Parse roadmap content into sections with missions."""
        sections = []
        
        # Split by major sections (## headers)
        section_pattern = r'^## (.+)$'
        lines = content.split('\n')
        
        current_section = None
        current_missions = []
        
        for line in lines:
            # Check for section header (## AGORA, ## PRÓXIMO, etc.)
            section_match = re.match(section_pattern, line)
            if section_match:
                # Save previous section if exists
                if current_section:
                    sections.append({
                        'title': current_section,
                        'missions': current_missions
                    })
                
                current_section = section_match.group(1).strip()
                current_missions = []
                continue
            
            # Check for mission items (bullet points with status icons)
            if current_section:
                mission = self._parse_mission_line(line)
                if mission:
                    current_missions.append(mission)
        
        # Add last section
        if current_section:
            sections.append({
                'title': current_section,
                'missions': current_missions
            })
        
        return sections
    
    def _parse_mission_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a single line to extract mission information."""
        # Match patterns like:
        # - ✅ Description
        # - 🔄 Description
        # - 📋 Description
        # - [ ] Checkbox description
        
        # Check for emoji-based missions
        emoji_pattern = r'^\s*[-*]\s*(✅|🔄|📋)\s+(.+)$'
        emoji_match = re.match(emoji_pattern, line)
        if emoji_match:
            status_emoji, description = emoji_match.groups()
            status_map = {
                '✅': 'completed',
                '🔄': 'in_progress',
                '📋': 'planned'
            }
            return {
                'description': description.strip(),
                'status': status_map.get(status_emoji, 'unknown'),
                'original_line': line.strip()
            }
        
        # Check for checkbox-based missions
        checkbox_pattern = r'^\s*[-*]\s*\[([ xX])\]\s+(.+)$'
        checkbox_match = re.match(checkbox_pattern, line)
        if checkbox_match:
            checkbox, description = checkbox_match.groups()
            status = 'completed' if checkbox.lower() == 'x' else 'planned'
            return {
                'description': description.strip(),
                'status': status,
                'original_line': line.strip()
            }
        
        return None
    
    def find_next_mission(self) -> Optional[Dict[str, Any]]:
        """
        Find the next achievable mission from the roadmap.
        
        Priority order:
        1. In-progress missions (🔄) in "AGORA" section
        2. Planned missions (📋) in "AGORA" section
        3. In-progress missions (🔄) in "PRÓXIMO" section
        4. Planned missions (📋) in "PRÓXIMO" section
        
        Returns:
            Dictionary with mission details or None if no mission found
        """
        roadmap_data = self.parse_roadmap()
        
        if 'error' in roadmap_data:
            logger.error(f"Cannot find next mission: {roadmap_data['error']}")
            return None
        
        sections = roadmap_data['sections']
        
        # Priority 1: Find "AGORA" section
        agora_section = None
        proximo_section = None
        
        for section in sections:
            title = section['title'].upper()
            if 'AGORA' in title or 'NOW' in title:
                agora_section = section
            elif 'PRÓXIMO' in title or 'NEXT' in title:
                proximo_section = section
        
        # Look for missions in priority order
        if agora_section:
            # First, in-progress missions
            for mission in agora_section['missions']:
                if mission['status'] == 'in_progress':
                    logger.info(f"Found in-progress mission in AGORA: {mission['description'][:50]}...")
                    return {
                        'mission': mission,
                        'section': 'AGORA',
                        'priority': 'high'
                    }
            
            # Second, planned missions
            for mission in agora_section['missions']:
                if mission['status'] == 'planned':
                    logger.info(f"Found planned mission in AGORA: {mission['description'][:50]}...")
                    return {
                        'mission': mission,
                        'section': 'AGORA',
                        'priority': 'medium'
                    }
        
        # Priority 3: Look in PRÓXIMO section for in-progress
        if proximo_section:
            for mission in proximo_section['missions']:
                if mission['status'] == 'in_progress':
                    logger.info(f"Found in-progress mission in PRÓXIMO: {mission['description'][:50]}...")
                    return {
                        'mission': mission,
                        'section': 'PRÓXIMO',
                        'priority': 'medium'
                    }
            
            # Priority 4: Planned missions in PRÓXIMO (lower priority)
            for mission in proximo_section['missions']:
                if mission['status'] == 'planned':
                    logger.info(f"Found planned mission in PRÓXIMO: {mission['description'][:50]}...")
                    return {
                        'mission': mission,
                        'section': 'PRÓXIMO',
                        'priority': 'low'
                    }
        
        logger.warning("No suitable mission found in roadmap")
        return None
    
    def get_roadmap_context(self, mission: Dict[str, Any]) -> str:
        """
        Generate context for the AI to understand the mission.
        
        Args:
            mission: Mission dictionary from find_next_mission()
            
        Returns:
            Context string for AI processing
        """
        if not mission:
            return "No mission context available"
        
        mission_data = mission['mission']
        section = mission['section']
        priority = mission['priority']
        
        context = f"""
### Mission from ROADMAP ({section} section - Priority: {priority})

**Description:** {mission_data['description']}

**Current Status:** {mission_data['status']}

**Instructions:**
1. Analyze the mission description carefully
2. Implement the smallest possible changes to address this mission
3. Follow existing code patterns and architecture
4. Run tests after implementation
5. If tests pass, mark this as a success for the Reinforcement Learning system
6. If tests fail, this counts as a punishment for the RL system

**Remember:** This is part of JARVIS's auto-evolution loop. Small, incremental changes are preferred over large refactors.
"""
        
        return context.strip()
    
    def is_auto_evolution_pr(self, pr_title: str, pr_body: Optional[str] = None) -> bool:
        """
        Check if a PR is from the auto-evolution system.
        
        Args:
            pr_title: PR title
            pr_body: Optional PR body/description
            
        Returns:
            True if PR is from auto-evolution, False otherwise
        """
        # Keywords that indicate auto-evolution PRs
        auto_evolution_keywords = [
            'auto-evolution',
            'auto evolution',
            'jarvis evolution',
            'self-evolution',
            'roadmap mission',
            '[auto-evolution]',
            '[jarvis-evolution]'
        ]
        
        # Check title (case-insensitive)
        title_lower = pr_title.lower()
        for keyword in auto_evolution_keywords:
            if keyword in title_lower:
                logger.info(f"PR detected as auto-evolution (keyword in title: {keyword})")
                return True
        
        # Check body if provided
        if pr_body:
            body_lower = pr_body.lower()
            for keyword in auto_evolution_keywords:
                if keyword in body_lower:
                    logger.info(f"PR detected as auto-evolution (keyword in body: {keyword})")
                    return True
        
        logger.debug(f"PR not detected as auto-evolution: {pr_title}")
        return False
    
    def get_success_metrics(self) -> Dict[str, Any]:
        """
        Calculate success metrics for the auto-evolution system.
        
        Returns:
            Dictionary with completion percentages and statistics
        """
        roadmap_data = self.parse_roadmap()
        
        if 'error' in roadmap_data:
            return {
                'error': roadmap_data['error']
            }
        
        total_missions = 0
        completed_missions = 0
        in_progress_missions = 0
        planned_missions = 0
        
        for section in roadmap_data['sections']:
            for mission in section['missions']:
                total_missions += 1
                if mission['status'] == 'completed':
                    completed_missions += 1
                elif mission['status'] == 'in_progress':
                    in_progress_missions += 1
                elif mission['status'] == 'planned':
                    planned_missions += 1
        
        completion_percentage = (
            (completed_missions / total_missions * 100) 
            if total_missions > 0 
            else 0.0
        )
        
        return {
            'total_missions': total_missions,
            'completed': completed_missions,
            'in_progress': in_progress_missions,
            'planned': planned_missions,
            'completion_percentage': round(completion_percentage, 2),
            'roadmap_path': str(self.roadmap_path)
        }
