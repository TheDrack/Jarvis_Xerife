# -*- coding: utf-8 -*-
"""Auto Evolution Service - Self-improvement system for JARVIS"""

import logging
import re
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

class AutoEvolutionService:
    """
    Gerencia a auto-evolução baseada no ROADMAP.md.
    Prioridade: 🔄 (em andamento) > 📋 (planejado) > ✅ (concluído - ignorado)
    """

    MAX_AUTO_COMPLETE_ATTEMPTS = 10

    def __init__(self, roadmap_path: Optional[str] = None):
        if roadmap_path:
            self.roadmap_path = Path(roadmap_path)
        else:
            # Tenta localizar docs/ROADMAP.md subindo a partir de services
            # Ajustado para ser resiliente a diferentes ambientes de execução
            base_path = Path(__file__).resolve().parent.parent.parent.parent
            self.roadmap_path = base_path / "docs" / "ROADMAP.md"

        logger.info(f"AutoEvolutionService carregado: {self.roadmap_path}")

    def parse_roadmap(self) -> Dict[str, Any]:
        if not self.roadmap_path.exists():
            logger.error(f"Roadmap não encontrado: {self.roadmap_path}")
            return {'error': 'File not found', 'sections': []}

        try:
            content = self.roadmap_path.read_text(encoding='utf-8')
            sections = self._parse_sections(content)
            return {'sections': sections}
        except Exception as e:
            logger.error(f"Erro ao ler roadmap: {e}")
            return {'error': str(e), 'sections': []}

    def _parse_sections(self, content: str) -> List[Dict[str, Any]]:
        sections = []
        section_pattern = r'^## (.+)$'
        lines = content.split('\n')

        current_section = None
        current_missions = []

        for line in lines:
            section_match = re.match(section_pattern, line)
            if section_match:
                if current_section:
                    sections.append({'title': current_section, 'missions': current_missions})
                current_section = section_match.group(1).strip()
                current_missions = []
                continue

            if current_section:
                mission = self._parse_mission_line(line)
                if mission:
                    current_missions.append(mission)

        if current_section:
            sections.append({'title': current_section, 'missions': current_missions})
        return sections

    def _parse_mission_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse robusto para identificar missões independente do marcador de lista."""
        # Regex atualizada: Ignora o marcador inicial (-, *, o) e foca no emoji + descrição
        # Aceita: "  o 🔄 Descrição", "- ✅ Descrição", "* 📋 Descrição"
        pattern = r'^\s*[-*o]?\s*(✅|🔄|📋|\[[ xX]\])\s+(.+)$'
        match = re.match(pattern, line)
        
        if match:
            status_raw, description = match.groups()
            
            # Normalização de Status
            if status_raw in ['✅', '[x]', '[X]']:
                status = 'completed'
            elif status_raw == '🔄':
                status = 'in_progress'
            else:
                status = 'planned'
                
            return {
                'description': description.strip(),
                'status': status,
                'original_line': line.strip()
            }
        return None

    def mark_mission_as_completed(self, mission_description: str) -> bool:
        """Marca a missão como concluída preservando a estrutura original da linha."""
        if not self.roadmap_path.exists(): return False

        try:
            lines = self.roadmap_path.read_text(encoding='utf-8').splitlines()
            modified = False

            for i, line in enumerate(lines):
                # Busca parcial: se a descrição da missão está na linha e não está concluída
                if mission_description in line and '✅' not in line and '[x]' not in line:
                    # Substitui qualquer marcador de progresso/pendente pelo de check
                    new_line = line.replace('🔄', '✅').replace('📋', '✅').replace('[ ]', '[x]')
                    if new_line != line:
                        lines[i] = new_line
                        modified = True
                        break

            if modified:
                self.roadmap_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
                return True
        except Exception as e:
            logger.error(f"Erro ao atualizar ROADMAP: {e}")
        return False


    def find_next_mission(self) -> Optional[Dict[str, Any]]:
        roadmap_data = self.parse_roadmap()
        if 'error' in roadmap_data: return None

        # Procura primeiro na seção AGORA (mais prioritária)
        for section in roadmap_data['sections']:
            title = section['title'].upper()
            if 'AGORA' in title or 'NOW' in title:
                # Prioridade 1: O que já está em andamento (🔄)
                for m in section['missions']:
                    if m['status'] == 'in_progress':
                        return {'mission': m, 'section': section['title'], 'priority': 'high'}
                # Prioridade 2: O que está planejado (📋)
                for m in section['missions']:
                    if m['status'] == 'planned':
                        return {'mission': m, 'section': section['title'], 'priority': 'medium'}
        
        return None

    def mark_mission_as_completed(self, mission_description: str) -> bool:
        """Localiza a linha exata e troca o status para concluído."""
        if not self.roadmap_path.exists(): return False

        try:
            content = self.roadmap_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            modified = False

            for i, line in enumerate(lines):
                # Usamos in em vez de == para evitar problemas com caracteres invisíveis
                if mission_description in line and ('🔄' in line or '📋' in line):
                    # Preservamos a indentação original
                    lines[i] = line.replace('🔄', '✅').replace('📋', '✅')
                    modified = True
                    break

            if modified:
                self.roadmap_path.write_text('\n'.join(lines), encoding='utf-8')
                logger.info(f"Roadmap atualizado: {mission_description}")
                return True
        except Exception as e:
            logger.error(f"Falha ao atualizar ROADMAP: {e}")
        return False

    def find_next_mission_with_auto_complete(self) -> Optional[Dict[str, Any]]:
        # Mantemos sua lógica de buscar a próxima válida
        return self.find_next_mission()

    def get_roadmap_context(self, mission: Dict[str, Any]) -> str:
        if not mission: return ""
        return f"MISSÃO: {mission['mission']['description']}\nCONTEXTO: {mission['section']}\nPRIORIDADE: {mission['priority']}"
