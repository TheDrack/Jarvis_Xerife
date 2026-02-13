# -*- coding: utf-8 -*-
"""
Marvel Evolution Service - Jarvis Marvel Skills Learning System

This service extends AutoEvolutionService to specifically handle the Marvel-level
skills from MARVEL_ROADMAP.md (CHAPTER 9 capabilities).

The Marvel Evolution System:
1. Reads MARVEL_ROADMAP.md to find incomplete Marvel skills
2. For each skill, identifies required scripts and implementations
3. Validates through "Metabolismo" (stress tests with pytest)
4. Marks skills as "Aprendida" (Learned) only after tests pass
5. Reports progress in Portuguese: "Comandante, mais uma habilidade..."
"""

import logging
import re
from typing import Dict, Any, Optional, List
from pathlib import Path

from app.application.services.auto_evolution import AutoEvolutionService

logger = logging.getLogger(__name__)


class MarvelEvolutionService(AutoEvolutionService):
    """
    Service for managing Jarvis Marvel-level skills evolution.
    
    This extends AutoEvolutionService with Marvel-specific functionality:
    - Parses MARVEL_ROADMAP.md instead of ROADMAP.md
    - Identifies Marvel skills (IDs 94-102 from capabilities.json)
    - Generates Portuguese progress reports
    - Integrates with Metabolismo (test validation)
    """
    
    # Marvel skill capability IDs from data/capabilities.json
    MARVEL_CAPABILITY_IDS = list(range(94, 103))  # IDs 94-102
    
    # Marvel skill names (Portuguese)
    MARVEL_SKILLS = {
        94: "Interface Holográfica - Antecipar Necessidades do Usuário",
        95: "Diagnóstico de Armadura - Propor Soluções Proativamente",
        96: "Controle de Periféricos - Ação Proativa e Segura",
        97: "Sistemas Integrados - Coordenar Físico e Digital",
        98: "Copiloto Cognitivo - Operar como Assistente Mental",
        99: "Alinhamento Contínuo - Manter Sintonia com Usuário",
        100: "Evolução Preservando Identidade - Evoluir sem Perder Essência",
        101: "Sustentabilidade Econômica - Autossuficiência Financeira",
        102: "Infraestrutura Cognitiva Pessoal - Fundação do Pensamento",
    }
    
    def __init__(self, marvel_roadmap_path: Optional[str] = None):
        """
        Initialize the Marvel Evolution Service.
        
        Args:
            marvel_roadmap_path: Path to MARVEL_ROADMAP.md (defaults to docs/MARVEL_ROADMAP.md)
        """
        # Initialize parent with Marvel roadmap path
        if marvel_roadmap_path:
            super().__init__(roadmap_path=marvel_roadmap_path)
        else:
            # Default to docs/MARVEL_ROADMAP.md
            marvel_path = Path(__file__).parent.parent.parent.parent / "docs" / "MARVEL_ROADMAP.md"
            super().__init__(roadmap_path=str(marvel_path))
        
        logger.info(f"MarvelEvolutionService initialized with roadmap: {self.roadmap_path}")
    
    def find_next_marvel_skill(self) -> Optional[Dict[str, Any]]:
        """
        Find the next Marvel skill that needs to be learned.
        
        This looks specifically for skills marked with [ ] (not learned) in the
        "As 9 Habilidades do Jarvis Marvel" section.
        
        Returns:
            Dictionary with skill details or None if no skill found
        """
        if not self.roadmap_path.exists():
            logger.error(f"Marvel roadmap not found: {self.roadmap_path}")
            return None
        
        try:
            content = self.roadmap_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            # Find skills in "As 9 Habilidades do Jarvis Marvel" section
            in_skills_section = False
            current_skill = None
            skill_number = 0
            
            for i, line in enumerate(lines):
                # Check if we're in the skills section
                if '## 🎯 As 9 Habilidades do Jarvis Marvel' in line:
                    in_skills_section = True
                    continue
                
                # Check if we've left the skills section
                if in_skills_section and line.startswith('## ') and 'Habilidades' not in line:
                    break
                
                # Look for skill headers (### 1. Interface Holográfica...)
                skill_header_match = re.match(r'^### (\d+)\.\s+(.+)$', line)
                if skill_header_match and in_skills_section:
                    skill_number = int(skill_header_match.group(1))
                    skill_name = skill_header_match.group(2).strip()
                    current_skill = {
                        'number': skill_number,
                        'name': skill_name,
                        'capability_id': None,
                        'status': None,
                        'line_number': i,
                    }
                    continue
                
                # Look for capability ID
                if current_skill and '**ID da Capacidade**:' in line:
                    id_match = re.search(r'(\d+)', line)
                    if id_match:
                        current_skill['capability_id'] = int(id_match.group(1))
                
                # Look for status line with checkbox
                if current_skill and '**Status**:' in line:
                    if '[ ]' in line:
                        current_skill['status'] = 'not_learned'
                        # Found first not-learned skill
                        logger.info(f"Found next Marvel skill to learn: {current_skill['name']}")
                        return self._build_marvel_skill_context(current_skill, lines, i)
                    elif '[x]' in line or '[X]' in line:
                        current_skill['status'] = 'learned'
                        current_skill = None  # Reset to look for next skill
                        continue
            
            logger.info("All Marvel skills have been learned!")
            return None
            
        except Exception as e:
            logger.error(f"Error finding next Marvel skill: {e}")
            return None
    
    def _build_marvel_skill_context(
        self, 
        skill: Dict[str, Any], 
        lines: List[str], 
        start_line: int
    ) -> Dict[str, Any]:
        """
        Build context information for a Marvel skill.
        
        Args:
            skill: Basic skill information
            lines: All lines from the roadmap
            start_line: Line number where we found the skill
            
        Returns:
            Dictionary with complete skill context
        """
        # Extract description, requirements, and acceptance criteria
        description = ""
        requirements = []
        acceptance_criteria = []
        scripts_needed = []
        
        in_requirements = False
        in_acceptance = False
        in_scripts = False
        
        # Look ahead to extract details
        for i in range(start_line, min(start_line + 100, len(lines))):
            line = lines[i]
            
            # Stop at next skill
            if line.startswith('### ') and i > start_line + 5:
                break
            
            # Extract description
            if '**Descrição**:' in line:
                description = line.split('**Descrição**:')[1].strip()
            
            # Track sections
            if '**Habilidades Necessárias**:' in line:
                in_requirements = True
                in_acceptance = False
                in_scripts = False
                continue
            elif '**Critérios de Aprovação (Metabolismo)**:' in line:
                in_requirements = False
                in_acceptance = True
                in_scripts = False
                continue
            elif '**Scripts Necessários**:' in line:
                in_requirements = False
                in_acceptance = False
                in_scripts = True
                continue
            elif line.startswith('**') and line.endswith('**:'):
                in_requirements = False
                in_acceptance = False
                in_scripts = False
            
            # Extract items from current section
            if line.startswith('- '):
                item = line[2:].strip()
                if in_requirements:
                    requirements.append(item)
                elif in_acceptance:
                    # Remove checkbox markers
                    item = re.sub(r'\[[ xX]\]\s*', '', item)
                    acceptance_criteria.append(item)
                elif in_scripts:
                    scripts_needed.append(item)
        
        return {
            'skill': skill,
            'description': description,
            'requirements': requirements,
            'acceptance_criteria': acceptance_criteria,
            'scripts_needed': scripts_needed,
            'priority': 'marvel',
            'section': 'MARVEL_LEVEL'
        }
    
    def mark_marvel_skill_as_learned(self, skill_number: int) -> bool:
        """
        Mark a Marvel skill as learned in MARVEL_ROADMAP.md.
        
        Args:
            skill_number: The skill number (1-9)
            
        Returns:
            True if skill was marked, False otherwise
        """
        if not self.roadmap_path.exists():
            logger.error(f"Marvel roadmap not found: {self.roadmap_path}")
            return False
        
        if not 1 <= skill_number <= 9:
            logger.error(f"Invalid skill number: {skill_number}. Must be 1-9.")
            return False
        
        try:
            content = self.roadmap_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            modified = False
            
            # Find the skill and mark its status
            for i, line in enumerate(lines):
                # Look for "### {skill_number}. " pattern
                if re.match(f'^### {skill_number}\\.\\s+', line):
                    # Found the skill header, now find its status line
                    for j in range(i, min(i + 10, len(lines))):
                        if '**Status**:' in lines[j]:
                            if '[ ]' in lines[j]:
                                lines[j] = lines[j].replace('[ ]', '[x]')
                                modified = True
                                logger.info(f"Marked Marvel skill {skill_number} as learned")
                                break
                            elif '[x]' in lines[j] or '[X]' in lines[j]:
                                logger.info(f"Marvel skill {skill_number} already marked as learned")
                                return True
                    break
            
            if modified:
                # Also update the status list at the bottom
                for i, line in enumerate(lines):
                    if f'- [ ] Habilidade {skill_number}:' in line:
                        lines[i] = line.replace('[ ]', '[x]')
                
                # Write back
                new_content = '\n'.join(lines)
                self.roadmap_path.write_text(new_content, encoding='utf-8')
                logger.info("Successfully updated MARVEL_ROADMAP.md")
                return True
            else:
                logger.warning(f"Could not find skill {skill_number} to mark as learned")
                return False
                
        except Exception as e:
            logger.error(f"Error marking Marvel skill as learned: {e}")
            return False
    
    def get_marvel_progress(self) -> Dict[str, Any]:
        """
        Get progress statistics for Marvel skills.
        
        Returns:
            Dictionary with completion percentages and statistics
        """
        if not self.roadmap_path.exists():
            return {
                'error': 'Marvel roadmap not found',
                'roadmap_path': str(self.roadmap_path)
            }
        
        try:
            content = self.roadmap_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            total_skills = 9
            learned_skills = 0
            
            # Count learned skills in the status section
            for line in lines:
                if re.match(r'- \[x\] Habilidade \d+:', line, re.IGNORECASE):
                    learned_skills += 1
            
            progress_percentage = (learned_skills / total_skills * 100) if total_skills > 0 else 0
            
            return {
                'total_skills': total_skills,
                'learned': learned_skills,
                'not_learned': total_skills - learned_skills,
                'progress_percentage': round(progress_percentage, 2),
                'roadmap_path': str(self.roadmap_path),
                'level': 'Marvel' if learned_skills == total_skills else 'Em Progresso'
            }
            
        except Exception as e:
            logger.error(f"Error getting Marvel progress: {e}")
            return {
                'error': str(e),
                'roadmap_path': str(self.roadmap_path)
            }
    
    def generate_progress_report(
        self, 
        skill_name: str, 
        tests_passed: int, 
        tests_total: int, 
        learning_time: str = "N/A"
    ) -> str:
        """
        Generate a Portuguese progress report for a learned skill.
        
        Args:
            skill_name: Name of the skill that was learned
            tests_passed: Number of tests that passed
            tests_total: Total number of tests
            learning_time: Time taken to learn (e.g., "2 horas", "1 dia")
            
        Returns:
            Formatted progress report in Portuguese
        """
        progress = self.get_marvel_progress()
        
        if 'error' in progress:
            return f"❌ Erro ao gerar relatório: {progress['error']}"
        
        learned = progress['learned']
        total = progress['total_skills']
        percentage = progress['progress_percentage']
        
        report = f"""
🤖 Comandante, mais uma habilidade do Jarvis Marvel foi integrada ao meu DNA.

Habilidade Aprendida: {skill_name}
Testes Passaram: {tests_passed}/{tests_total} ({tests_passed/tests_total*100:.0f}%)
Tempo de Aprendizado: {learning_time}

📈 Progresso Geral: {learned}/{total} habilidades Marvel ({percentage:.1f}% completo)
Estamos {percentage:.1f}% mais próximos do Xerife Marvel.
"""
        
        # Add next mission if not all skills learned
        if learned < total:
            next_skill = self.find_next_marvel_skill()
            if next_skill:
                next_name = next_skill['skill']['name']
                report += f"\nPróxima Missão: {next_name}\n"
        else:
            report += "\n🎉 TODAS AS HABILIDADES MARVEL FORAM APRENDIDAS! Jarvis Marvel está completo!\n"
        
        return report.strip()
    
    def is_skill_validated_by_metabolismo(
        self, 
        skill_number: int, 
        test_results: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Validate if a skill passes the Metabolismo (stress tests).
        
        Args:
            skill_number: The skill number (1-9)
            test_results: Optional test results dictionary with:
                - passed: number of tests passed
                - total: total number of tests
                - success_rate: percentage of tests passed
                
        Returns:
            True if skill passes validation (all tests pass), False otherwise
        """
        if test_results is None:
            logger.warning("No test results provided, cannot validate skill")
            return False
        
        passed = test_results.get('passed', 0)
        total = test_results.get('total', 0)
        
        if total == 0:
            logger.warning(f"No tests found for skill {skill_number}")
            return False
        
        # All tests must pass for skill to be considered learned
        success = passed == total
        
        if success:
            logger.info(f"Skill {skill_number} passed Metabolismo: {passed}/{total} tests passed")
        else:
            logger.warning(f"Skill {skill_number} failed Metabolismo: {passed}/{total} tests passed")
        
        return success
