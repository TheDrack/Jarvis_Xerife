# -*- coding: utf-8 -*-
"""Tests for Marvel Evolution Service"""

import pytest
from pathlib import Path
from app.application.services.marvel_evolution import MarvelEvolutionService


class TestMarvelEvolutionService:
    """Test cases for MarvelEvolutionService"""
    
    @pytest.fixture
    def marvel_service(self):
        """Create a Marvel evolution service instance"""
        return MarvelEvolutionService()
    
    @pytest.fixture
    def sample_marvel_roadmap(self):
        """Sample Marvel roadmap content for testing"""
        return """# Apostila de Evolução: Jarvis Marvel

## 🎯 As 9 Habilidades do Jarvis Marvel

### 1. Interface Holográfica - Antecipar Necessidades do Usuário
**ID da Capacidade**: 94  
**Status**: [ ] Não Aprendida  
**Descrição**: Capacidade de antecipar as necessidades do usuário.

**Habilidades Necessárias**:
- Análise de padrões de comportamento
- Aprendizado de rotinas

**Critérios de Aprovação (Metabolismo)**:
- [ ] Testes de predição com precisão >70%
- [ ] Sistema de cache funcional

**Scripts Necessários**:
- `app/domain/services/need_anticipation.py` - Serviço de antecipação
- `tests/test_need_anticipation.py` - Testes de validação

---

### 2. Diagnóstico de Armadura - Propor Soluções Proativamente
**ID da Capacidade**: 95  
**Status**: [x] Aprendida  
**Descrição**: Propor soluções antes de requisições explícitas.

**Habilidades Necessárias**:
- Sistema de detecção de problemas

**Critérios de Aprovação (Metabolismo)**:
- [x] Detecção automática de problemas

**Scripts Necessários**:
- `app/domain/services/proactive_solution.py`

---

## 🎓 Status de Evolução

### Capítulo 9: Marvel Level (Status: 11% - Esta Apostila)
- [ ] Habilidade 1: Interface Holográfica
- [x] Habilidade 2: Diagnóstico de Armadura
- [ ] Habilidade 3: Controle de Periféricos
"""
    
    @pytest.fixture
    def temp_marvel_roadmap(self, tmp_path, sample_marvel_roadmap):
        """Create a temporary Marvel roadmap file"""
        roadmap_file = tmp_path / "MARVEL_ROADMAP.md"
        roadmap_file.write_text(sample_marvel_roadmap, encoding='utf-8')
        return roadmap_file
    
    def test_initialization(self, marvel_service):
        """Test service initialization"""
        assert marvel_service.roadmap_path.name == "MARVEL_ROADMAP.md"
        assert "docs" in str(marvel_service.roadmap_path)
    
    def test_marvel_capability_ids(self):
        """Test that Marvel capability IDs are correct"""
        assert len(MarvelEvolutionService.MARVEL_CAPABILITY_IDS) == 9
        assert MarvelEvolutionService.MARVEL_CAPABILITY_IDS[0] == 94
        assert MarvelEvolutionService.MARVEL_CAPABILITY_IDS[-1] == 102
    
    def test_marvel_skills_mapping(self):
        """Test that all Marvel skills are properly mapped"""
        assert len(MarvelEvolutionService.MARVEL_SKILLS) == 9
        
        # Check some key skills
        assert 94 in MarvelEvolutionService.MARVEL_SKILLS
        assert "Interface Holográfica" in MarvelEvolutionService.MARVEL_SKILLS[94]
        
        assert 102 in MarvelEvolutionService.MARVEL_SKILLS
        assert "Infraestrutura Cognitiva" in MarvelEvolutionService.MARVEL_SKILLS[102]
    
    def test_find_next_marvel_skill(self, temp_marvel_roadmap):
        """Test finding next Marvel skill to learn"""
        service = MarvelEvolutionService(marvel_roadmap_path=str(temp_marvel_roadmap))
        
        result = service.find_next_marvel_skill()
        
        # Should find skill #1 (not learned)
        assert result is not None
        assert result['skill']['number'] == 1
        assert result['skill']['name'] == 'Interface Holográfica - Antecipar Necessidades do Usuário'
        assert result['skill']['capability_id'] == 94
        assert result['skill']['status'] == 'not_learned'
    
    def test_find_next_marvel_skill_with_context(self, temp_marvel_roadmap):
        """Test that skill context is properly extracted"""
        service = MarvelEvolutionService(marvel_roadmap_path=str(temp_marvel_roadmap))
        
        result = service.find_next_marvel_skill()
        
        assert result is not None
        
        # Check description
        assert 'antecipar' in result['description'].lower()
        
        # Check requirements
        assert len(result['requirements']) == 2
        assert any('padrões' in req.lower() for req in result['requirements'])
        
        # Check acceptance criteria
        assert len(result['acceptance_criteria']) >= 1
        assert any('70%' in criterion for criterion in result['acceptance_criteria'])
        
        # Check scripts needed
        assert len(result['scripts_needed']) == 2
        assert any('need_anticipation' in script for script in result['scripts_needed'])
    
    def test_find_next_skill_skips_learned(self, temp_marvel_roadmap):
        """Test that learned skills are skipped"""
        service = MarvelEvolutionService(marvel_roadmap_path=str(temp_marvel_roadmap))
        
        # Should skip skill #2 (marked with [x]) and find skill #1
        result = service.find_next_marvel_skill()
        
        assert result is not None
        assert result['skill']['number'] == 1  # Not 2, which is learned
    
    def test_find_next_skill_no_skills_available(self, tmp_path):
        """Test when all skills are learned"""
        # Create roadmap with all skills learned
        all_learned = """# Apostila de Evolução: Jarvis Marvel

## 🎯 As 9 Habilidades do Jarvis Marvel

### 1. Skill One
**ID da Capacidade**: 94  
**Status**: [x] Aprendida  

### 2. Skill Two
**ID da Capacidade**: 95  
**Status**: [x] Aprendida  
"""
        roadmap_file = tmp_path / "MARVEL_ROADMAP.md"
        roadmap_file.write_text(all_learned, encoding='utf-8')
        
        service = MarvelEvolutionService(marvel_roadmap_path=str(roadmap_file))
        result = service.find_next_marvel_skill()
        
        # Should return None when all skills learned
        assert result is None
    
    def test_mark_marvel_skill_as_learned(self, temp_marvel_roadmap):
        """Test marking a skill as learned"""
        service = MarvelEvolutionService(marvel_roadmap_path=str(temp_marvel_roadmap))
        
        # Mark skill #1 as learned
        result = service.mark_marvel_skill_as_learned(1)
        assert result is True
        
        # Verify it was updated in the file
        content = temp_marvel_roadmap.read_text(encoding='utf-8')
        
        # Check skill header section
        assert '[x]' in content or '[X]' in content
        
        # Verify skill 1 status changed but skill 2 didn't
        lines = content.split('\n')
        found_skill_1 = False
        for i, line in enumerate(lines):
            if '### 1.' in line:
                # Look for status in next few lines
                for j in range(i, min(i+10, len(lines))):
                    if '**Status**:' in lines[j]:
                        assert '[x]' in lines[j] or '[X]' in lines[j]
                        found_skill_1 = True
                        break
                break
        
        assert found_skill_1
    
    def test_mark_already_learned_skill(self, temp_marvel_roadmap):
        """Test marking an already learned skill"""
        service = MarvelEvolutionService(marvel_roadmap_path=str(temp_marvel_roadmap))
        
        # Skill #2 is already marked as learned
        result = service.mark_marvel_skill_as_learned(2)
        assert result is True  # Should return True since it's already learned
    
    def test_mark_invalid_skill_number(self, temp_marvel_roadmap):
        """Test marking skill with invalid number"""
        service = MarvelEvolutionService(marvel_roadmap_path=str(temp_marvel_roadmap))
        
        # Invalid skill numbers
        assert service.mark_marvel_skill_as_learned(0) is False
        assert service.mark_marvel_skill_as_learned(10) is False
        assert service.mark_marvel_skill_as_learned(-1) is False
    
    def test_get_marvel_progress(self, temp_marvel_roadmap):
        """Test getting Marvel progress statistics"""
        service = MarvelEvolutionService(marvel_roadmap_path=str(temp_marvel_roadmap))
        
        progress = service.get_marvel_progress()
        
        assert 'error' not in progress
        assert progress['total_skills'] == 9
        assert progress['learned'] == 1  # Skill #2 is marked as learned
        assert progress['not_learned'] == 8
        assert 0 <= progress['progress_percentage'] <= 100
        assert progress['level'] in ['Marvel', 'Em Progresso']
    
    def test_get_marvel_progress_file_not_exists(self):
        """Test progress when roadmap doesn't exist"""
        service = MarvelEvolutionService(marvel_roadmap_path="/nonexistent/MARVEL_ROADMAP.md")
        
        progress = service.get_marvel_progress()
        
        assert 'error' in progress
        assert progress['error'] == 'Marvel roadmap not found'
    
    def test_generate_progress_report(self, temp_marvel_roadmap):
        """Test generating a progress report"""
        service = MarvelEvolutionService(marvel_roadmap_path=str(temp_marvel_roadmap))
        
        report = service.generate_progress_report(
            skill_name="Interface Holográfica",
            tests_passed=4,
            tests_total=4,
            learning_time="2 horas"
        )
        
        # Check report contains expected elements
        assert "Comandante" in report
        assert "Jarvis Marvel" in report
        assert "Interface Holográfica" in report
        assert "4/4" in report
        assert "100%" in report
        assert "2 horas" in report
        assert "Xerife Marvel" in report
        
        # Should mention next mission since not all skills learned
        assert "Próxima Missão" in report
    
    def test_generate_progress_report_all_learned(self, tmp_path):
        """Test progress report when all skills are learned"""
        # Create roadmap with all learned
        all_learned = """# Apostila de Evolução: Jarvis Marvel

## 🎓 Status de Evolução

### Capítulo 9: Marvel Level
- [x] Habilidade 1: Skill One
- [x] Habilidade 2: Skill Two
- [x] Habilidade 3: Skill Three
- [x] Habilidade 4: Skill Four
- [x] Habilidade 5: Skill Five
- [x] Habilidade 6: Skill Six
- [x] Habilidade 7: Skill Seven
- [x] Habilidade 8: Skill Eight
- [x] Habilidade 9: Skill Nine
"""
        roadmap_file = tmp_path / "MARVEL_ROADMAP.md"
        roadmap_file.write_text(all_learned, encoding='utf-8')
        
        service = MarvelEvolutionService(marvel_roadmap_path=str(roadmap_file))
        
        report = service.generate_progress_report(
            skill_name="Final Skill",
            tests_passed=3,
            tests_total=3,
            learning_time="1 hora"
        )
        
        # Should indicate completion
        assert "TODAS AS HABILIDADES MARVEL" in report or "100%" in report
    
    def test_is_skill_validated_by_metabolismo_success(self, marvel_service):
        """Test Metabolismo validation with all tests passing"""
        test_results = {
            'passed': 5,
            'total': 5,
            'success_rate': 100.0
        }
        
        is_valid = marvel_service.is_skill_validated_by_metabolismo(1, test_results)
        assert is_valid is True
    
    def test_is_skill_validated_by_metabolismo_failure(self, marvel_service):
        """Test Metabolismo validation with some tests failing"""
        test_results = {
            'passed': 3,
            'total': 5,
            'success_rate': 60.0
        }
        
        is_valid = marvel_service.is_skill_validated_by_metabolismo(1, test_results)
        assert is_valid is False
    
    def test_is_skill_validated_by_metabolismo_no_tests(self, marvel_service):
        """Test Metabolismo validation with no tests"""
        test_results = {
            'passed': 0,
            'total': 0,
            'success_rate': 0.0
        }
        
        is_valid = marvel_service.is_skill_validated_by_metabolismo(1, test_results)
        assert is_valid is False
    
    def test_is_skill_validated_by_metabolismo_no_results(self, marvel_service):
        """Test Metabolismo validation with no results provided"""
        is_valid = marvel_service.is_skill_validated_by_metabolismo(1, None)
        assert is_valid is False


class TestMarvelEvolutionIntegration:
    """Integration tests for Marvel evolution system"""
    
    def test_integration_with_auto_evolution(self):
        """Test that MarvelEvolutionService extends AutoEvolutionService correctly"""
        from app.application.services.auto_evolution import AutoEvolutionService
        
        marvel_service = MarvelEvolutionService()
        
        # Should be an instance of AutoEvolutionService
        assert isinstance(marvel_service, AutoEvolutionService)
        
        # Should have all parent methods
        assert hasattr(marvel_service, 'parse_roadmap')
        assert hasattr(marvel_service, 'mark_mission_as_completed')
        assert hasattr(marvel_service, 'is_auto_evolution_pr')
        
        # Should have Marvel-specific methods
        assert hasattr(marvel_service, 'find_next_marvel_skill')
        assert hasattr(marvel_service, 'mark_marvel_skill_as_learned')
        assert hasattr(marvel_service, 'get_marvel_progress')
        assert hasattr(marvel_service, 'generate_progress_report')
        assert hasattr(marvel_service, 'is_skill_validated_by_metabolismo')
    
    def test_full_learning_cycle(self, tmp_path):
        """Test complete learning cycle for a Marvel skill"""
        # Create a simple roadmap
        roadmap_content = """# Apostila de Evolução: Jarvis Marvel

## 🎯 As 9 Habilidades do Jarvis Marvel

### 1. Test Skill
**ID da Capacidade**: 94  
**Status**: [ ] Não Aprendida  
**Descrição**: A test skill

**Critérios de Aprovação (Metabolismo)**:
- [ ] Test 1
- [ ] Test 2

---

## 🎓 Status de Evolução

### Capítulo 9: Marvel Level
- [ ] Habilidade 1: Test Skill
"""
        roadmap_file = tmp_path / "MARVEL_ROADMAP.md"
        roadmap_file.write_text(roadmap_content, encoding='utf-8')
        
        service = MarvelEvolutionService(marvel_roadmap_path=str(roadmap_file))
        
        # Step 1: Find next skill
        next_skill = service.find_next_marvel_skill()
        assert next_skill is not None
        assert next_skill['skill']['number'] == 1
        
        # Step 2: Validate with Metabolismo (simulate tests passing)
        test_results = {'passed': 2, 'total': 2, 'success_rate': 100.0}
        is_valid = service.is_skill_validated_by_metabolismo(1, test_results)
        assert is_valid is True
        
        # Step 3: Mark as learned
        marked = service.mark_marvel_skill_as_learned(1)
        assert marked is True
        
        # Step 4: Generate progress report
        report = service.generate_progress_report(
            skill_name="Test Skill",
            tests_passed=2,
            tests_total=2,
            learning_time="1 hora"
        )
        assert "Comandante" in report
        assert "Test Skill" in report
        
        # Step 5: Verify progress
        progress = service.get_marvel_progress()
        assert progress['learned'] == 1
        assert progress['progress_percentage'] > 0
