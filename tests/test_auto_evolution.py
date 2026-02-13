# -*- coding: utf-8 -*-
"""Tests for Auto Evolution Service"""

import pytest
from app.application.services.auto_evolution import AutoEvolutionService


class TestAutoEvolutionService:
    """Test cases for AutoEvolutionService"""
    
    @pytest.fixture
    def auto_evolution_service(self):
        """Create an auto evolution service instance"""
        return AutoEvolutionService()
    
    @pytest.fixture
    def sample_roadmap_content(self):
        """Sample roadmap content for testing"""
        return """# Roadmap do Projeto Jarvis

## 🚀 **AGORA**: Estabilização do Worker

### Objetivos Principais:
1. **Estabilizar TaskRunner com Venvs Efêmeros**
   - ✅ Criação e destruição automática de ambientes virtuais
   - 🔄 Graceful failure em instalações de pip
   - 📋 Logs estruturados com mission_id

2. **Fortalecer Playwright Integration**
   - ✅ Contexto persistente via CDP
   - 🔄 Extension manager para automações complexas
   - 📋 Testes de integração com Playwright

### Métricas de Sucesso:
- [ ] 100% das missões com logs estruturados
- [x] 95%+ de cobertura de testes no TaskRunner

## 📅 **PRÓXIMO**: Interface de Comando de Voz

### 1. Interface de Comando de Voz Aprimorada
- 🔄 Wake Word Detection Local
- 📋 Streaming Voice Recognition
- 📋 Voice Feedback Melhorado
"""
    
    def test_initialization(self, auto_evolution_service):
        """Test service initialization"""
        assert auto_evolution_service.roadmap_path.name == "ROADMAP.md"
        assert "docs" in str(auto_evolution_service.roadmap_path)
    
    def test_parse_roadmap_file_exists(self, auto_evolution_service):
        """Test parsing existing roadmap file"""
        result = auto_evolution_service.parse_roadmap()
        
        # Should have sections
        assert 'sections' in result
        assert isinstance(result['sections'], list)
        
        # Should not have error if file exists
        if auto_evolution_service.roadmap_path.exists():
            assert 'error' not in result
            assert result['total_sections'] >= 0
    
    def test_parse_roadmap_file_not_exists(self):
        """Test parsing when roadmap doesn't exist"""
        service = AutoEvolutionService(roadmap_path="/nonexistent/path/ROADMAP.md")
        result = service.parse_roadmap()
        
        assert 'error' in result
        assert result['error'] == 'Roadmap file not found'
        assert result['sections'] == []
    
    def test_parse_mission_line_completed(self, auto_evolution_service):
        """Test parsing completed mission line"""
        line = "   - ✅ Criação e destruição automática de ambientes virtuais"
        mission = auto_evolution_service._parse_mission_line(line)
        
        assert mission is not None
        assert mission['status'] == 'completed'
        assert 'ambientes virtuais' in mission['description']
    
    def test_parse_mission_line_in_progress(self, auto_evolution_service):
        """Test parsing in-progress mission line"""
        line = "   - 🔄 Graceful failure em instalações de pip"
        mission = auto_evolution_service._parse_mission_line(line)
        
        assert mission is not None
        assert mission['status'] == 'in_progress'
        assert 'Graceful failure' in mission['description']
    
    def test_parse_mission_line_planned(self, auto_evolution_service):
        """Test parsing planned mission line"""
        line = "   - 📋 Logs estruturados com mission_id"
        mission = auto_evolution_service._parse_mission_line(line)
        
        assert mission is not None
        assert mission['status'] == 'planned'
        assert 'Logs estruturados' in mission['description']
    
    def test_parse_mission_line_checkbox_unchecked(self, auto_evolution_service):
        """Test parsing unchecked checkbox mission"""
        line = "- [ ] 100% das missões com logs estruturados"
        mission = auto_evolution_service._parse_mission_line(line)
        
        assert mission is not None
        assert mission['status'] == 'planned'
        assert 'logs estruturados' in mission['description']
    
    def test_parse_mission_line_checkbox_checked(self, auto_evolution_service):
        """Test parsing checked checkbox mission"""
        line = "- [x] 95%+ de cobertura de testes no TaskRunner"
        mission = auto_evolution_service._parse_mission_line(line)
        
        assert mission is not None
        assert mission['status'] == 'completed'
        assert 'cobertura de testes' in mission['description']
    
    def test_parse_mission_line_invalid(self, auto_evolution_service):
        """Test parsing invalid mission line"""
        line = "Just some random text without markers"
        mission = auto_evolution_service._parse_mission_line(line)
        
        assert mission is None
    
    def test_find_next_mission_file_exists(self, auto_evolution_service):
        """Test finding next mission from real roadmap"""
        if not auto_evolution_service.roadmap_path.exists():
            pytest.skip("Roadmap file not found")
        
        result = auto_evolution_service.find_next_mission()
        
        # Result can be None if all missions are completed
        # or a dict with mission data
        if result:
            assert 'mission' in result
            assert 'section' in result
            assert 'priority' in result
            assert result['section'] in ['AGORA', 'PRÓXIMO']
            assert result['priority'] in ['high', 'medium', 'low']
    
    def test_get_roadmap_context(self, auto_evolution_service):
        """Test getting context for a mission"""
        mission = {
            'mission': {
                'description': 'Test mission description',
                'status': 'in_progress',
                'original_line': '- 🔄 Test mission description'
            },
            'section': 'AGORA',
            'priority': 'high'
        }
        
        context = auto_evolution_service.get_roadmap_context(mission)
        
        assert 'Test mission description' in context
        assert 'AGORA' in context
        assert 'high' in context
        assert 'in_progress' in context
    
    def test_get_roadmap_context_none(self, auto_evolution_service):
        """Test getting context with no mission"""
        context = auto_evolution_service.get_roadmap_context(None)
        
        assert context == "No mission context available"
    
    def test_is_auto_evolution_pr_true_keyword_in_title(self, auto_evolution_service):
        """Test detecting auto-evolution PR by title keyword"""
        assert auto_evolution_service.is_auto_evolution_pr("[Auto-Evolution] Fix bug")
        assert auto_evolution_service.is_auto_evolution_pr("Auto evolution: new feature")
        assert auto_evolution_service.is_auto_evolution_pr("JARVIS EVOLUTION test")
        assert auto_evolution_service.is_auto_evolution_pr("Self-evolution update")
    
    def test_is_auto_evolution_pr_true_keyword_in_body(self, auto_evolution_service):
        """Test detecting auto-evolution PR by body keyword"""
        title = "Regular PR"
        body = "This is an auto-evolution PR from Jarvis"
        
        assert auto_evolution_service.is_auto_evolution_pr(title, body)
    
    def test_is_auto_evolution_pr_false(self, auto_evolution_service):
        """Test non-auto-evolution PR detection"""
        assert not auto_evolution_service.is_auto_evolution_pr("Fix typo in README")
        assert not auto_evolution_service.is_auto_evolution_pr("Add new feature", "Some description")
    
    def test_get_success_metrics_file_exists(self, auto_evolution_service):
        """Test getting success metrics from real roadmap"""
        if not auto_evolution_service.roadmap_path.exists():
            pytest.skip("Roadmap file not found")
        
        metrics = auto_evolution_service.get_success_metrics()
        
        # Should not have error
        if 'error' not in metrics:
            assert 'total_missions' in metrics
            assert 'completed' in metrics
            assert 'in_progress' in metrics
            assert 'planned' in metrics
            assert 'completion_percentage' in metrics
            
            # Metrics should be non-negative
            assert metrics['total_missions'] >= 0
            assert metrics['completed'] >= 0
            assert metrics['in_progress'] >= 0
            assert metrics['planned'] >= 0
            assert 0 <= metrics['completion_percentage'] <= 100
    
    def test_get_success_metrics_file_not_exists(self):
        """Test getting metrics when file doesn't exist"""
        service = AutoEvolutionService(roadmap_path="/nonexistent/ROADMAP.md")
        metrics = service.get_success_metrics()
        
        assert 'error' in metrics


class TestAutoEvolutionAutoComplete:
    """Test cases for auto-completion functionality"""
    
    @pytest.fixture
    def temp_roadmap_file(self, tmp_path):
        """Create a temporary roadmap file for testing"""
        roadmap_content = """# Roadmap do Projeto Jarvis

## 🚀 **AGORA**: Test Section

### Objetivos Principais:
1. **Test Objectives**
   - ✅ Completed mission 1
   - 🔄 In progress mission 1
   - 📋 Planned mission 1
   - [ ] Unchecked mission 1
"""
        roadmap_file = tmp_path / "ROADMAP.md"
        roadmap_file.write_text(roadmap_content, encoding='utf-8')
        return roadmap_file
    
    def test_mark_mission_as_completed_in_progress(self, temp_roadmap_file):
        """Test marking an in-progress mission as completed"""
        service = AutoEvolutionService(roadmap_path=str(temp_roadmap_file))
        
        # Mark the in-progress mission as completed
        result = service.mark_mission_as_completed("In progress mission 1")
        assert result is True
        
        # Verify the file was updated
        content = temp_roadmap_file.read_text(encoding='utf-8')
        assert '✅ In progress mission 1' in content
        assert '🔄 In progress mission 1' not in content
    
    def test_mark_mission_as_completed_planned(self, temp_roadmap_file):
        """Test marking a planned mission as completed"""
        service = AutoEvolutionService(roadmap_path=str(temp_roadmap_file))
        
        result = service.mark_mission_as_completed("Planned mission 1")
        assert result is True
        
        content = temp_roadmap_file.read_text(encoding='utf-8')
        assert '✅ Planned mission 1' in content
        assert '📋 Planned mission 1' not in content
    
    def test_mark_mission_as_completed_checkbox(self, temp_roadmap_file):
        """Test marking a checkbox mission as completed"""
        service = AutoEvolutionService(roadmap_path=str(temp_roadmap_file))
        
        result = service.mark_mission_as_completed("Unchecked mission 1")
        assert result is True
        
        content = temp_roadmap_file.read_text(encoding='utf-8')
        assert '[x] Unchecked mission 1' in content
        assert '[ ] Unchecked mission 1' not in content
    
    def test_mark_mission_as_completed_already_completed(self, temp_roadmap_file):
        """Test marking an already completed mission"""
        service = AutoEvolutionService(roadmap_path=str(temp_roadmap_file))
        
        result = service.mark_mission_as_completed("Completed mission 1")
        assert result is True  # Should still return True since it's completed
        
        # File should remain unchanged
        content = temp_roadmap_file.read_text(encoding='utf-8')
        assert '✅ Completed mission 1' in content
    
    def test_mark_mission_as_completed_not_found(self, temp_roadmap_file):
        """Test marking a non-existent mission"""
        service = AutoEvolutionService(roadmap_path=str(temp_roadmap_file))
        
        result = service.mark_mission_as_completed("Non-existent mission")
        assert result is False
    
    def test_mark_mission_as_completed_file_not_exists(self):
        """Test marking mission when roadmap doesn't exist"""
        service = AutoEvolutionService(roadmap_path="/nonexistent/ROADMAP.md")
        
        result = service.mark_mission_as_completed("Some mission")
        assert result is False
    
    def test_is_mission_likely_completed(self):
        """Test heuristic check for mission completion"""
        service = AutoEvolutionService()
        
        # Currently returns False as it's a placeholder
        result = service.is_mission_likely_completed("Test mission")
        assert isinstance(result, bool)
    
    def test_find_next_mission_with_auto_complete(self, temp_roadmap_file):
        """Test finding next mission with auto-complete functionality"""
        service = AutoEvolutionService(roadmap_path=str(temp_roadmap_file))
        
        # Should find the in-progress mission
        result = service.find_next_mission_with_auto_complete()
        
        assert result is not None
        assert 'mission' in result
        assert 'section' in result


class TestAutoEvolutionIntegration:
    """Integration tests for auto evolution with evolution loop"""
    
    def test_integration_with_evolution_loop(self):
        """Test that auto evolution can work with evolution loop service"""
        from app.application.services.auto_evolution import AutoEvolutionService
        
        # Just test that service can be instantiated
        # Actual integration would require database setup
        service = AutoEvolutionService()
        assert service is not None
        
        # Verify methods are available
        assert hasattr(service, 'find_next_mission')
        assert hasattr(service, 'is_auto_evolution_pr')
        assert hasattr(service, 'get_success_metrics')
