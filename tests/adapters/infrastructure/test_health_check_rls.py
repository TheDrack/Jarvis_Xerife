from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""Additional tests for the RLS security health check endpoint"""

from unittest.mock import Mock, patch
import pytest
from fastapi.testclient import TestClient

from app.adapters.infrastructure import create_api_server
from app.application.services import AssistantService


# Test data constants
TEST_TABLES_WITH_RLS = [
    ('public', 'evolution_rewards', True),
    ('public', 'jarvis_capabilities', True),
]

TEST_TABLES_WITHOUT_RLS = [
    ('public', 'evolution_rewards', False),
    ('public', 'jarvis_capabilities', False),
]


class TestHealthCheckRLS(NexusComponent):

    def execute(self, context: dict):
        """Execução automática JARVIS."""
        pass
    """Test cases for RLS security health checks"""

    @pytest.fixture
    def mock_assistant_service(self):
        """Create a mocked AssistantService"""
        service = Mock(spec=AssistantService)
        service.wake_word = "xerife"
        service.is_running = False
        service._command_history = []
        service.interpreter = Mock()
        return service

    @pytest.fixture
    def client(self, mock_assistant_service):
        """Create a test client with mocked service"""
        app = create_api_server(mock_assistant_service)
        return TestClient(app), mock_assistant_service

    def test_health_check_sqlite(self, client):
        """Test health check with SQLite database (RLS N/A)"""
        test_client, _ = client
        
        with patch('app.core.config.settings.database_url', 'sqlite:///jarvis.db'):
            response = test_client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            
            # Validate SQLite response
            assert data["database"]["type"] == "sqlite"
            assert data["database"]["connected"] is True
            assert data["security"]["rls_enabled"] == "n/a"
            assert "note" in data["security"]
            assert "SQLite does not support Row Level Security" in data["security"]["note"]

    def test_health_check_postgresql_with_rls(self, client):
        """Test health check with PostgreSQL database and RLS enabled"""
        test_client, _ = client
        
        # Mock database adapter with PostgreSQL engine
        with patch('app.core.config.settings.database_url', 
                   'postgresql://user:pass@localhost/jarvis'):
            # Mock the db_adapter.engine to test PostgreSQL scenario
            mock_engine = Mock()
            
            # Create mock session context manager
            class MockSession:
                def __init__(self, engine):
                    self.engine = engine
                    
                def exec(self, query):
                    # Mock result for RLS query
                    result = Mock()
                    result.fetchall.return_value = TEST_TABLES_WITH_RLS
                    return result
                    
                def __enter__(self):
                    return self
                    
                def __exit__(self, *args):
                    return None
            
            # Patch the Session class in sqlmodel
            with patch('sqlmodel.Session', MockSession):
                response = test_client.get("/health")
                
                assert response.status_code == 200
                data = response.json()
                
                # Validate PostgreSQL response with RLS
                assert data["status"] == "healthy"
                assert data["database"]["type"] == "postgresql"
                assert data["database"]["connected"] is True
                assert data["security"]["rls_enabled"] is True
                assert len(data["security"]["tables_checked"]) == 2
                assert len(data["security"]["tables_without_rls"]) == 0

    def test_health_check_postgresql_without_rls(self, client):
        """Test health check with PostgreSQL database and RLS disabled"""
        test_client, _ = client
        
        # Mock database adapter with PostgreSQL engine
        with patch('app.core.config.settings.database_url', 
                   'postgresql://user:pass@localhost/jarvis'):
            # Create mock session context manager
            class MockSession:
                def __init__(self, engine):
                    self.engine = engine
                    
                def exec(self, query):
                    # Mock result for RLS query - tables without RLS
                    result = Mock()
                    result.fetchall.return_value = TEST_TABLES_WITHOUT_RLS
                    return result
                    
                def __enter__(self):
                    return self
                    
                def __exit__(self, *args):
                    return None
            
            # Patch the Session class in sqlmodel
            with patch('sqlmodel.Session', MockSession):
                response = test_client.get("/health")
                
                assert response.status_code == 200
                data = response.json()
                
                # Validate PostgreSQL response without RLS
                assert data["status"] == "degraded"
                assert data["database"]["type"] == "postgresql"
                assert data["database"]["connected"] is True
                assert data["security"]["rls_enabled"] is False
                assert len(data["security"]["tables_without_rls"]) == 2
                assert "warning" in data["security"]
                assert "evolution_rewards" in data["security"]["warning"]
                assert "jarvis_capabilities" in data["security"]["warning"]

    def test_health_check_database_connection_error(self, client):
        """Test health check when database connection fails"""
        test_client, _ = client
        
        # Mock database connection error
        with patch('app.core.config.settings.database_url', 
                   'postgresql://user:pass@localhost/jarvis'):
            # Create mock session that raises an error
            class MockSession:
                def __init__(self, engine):
                    self.engine = engine
                    
                def exec(self, query):
                    raise Exception("Connection refused")
                    
                def __enter__(self):
                    return self
                    
                def __exit__(self, *args):
                    return None
            
            # Patch the Session class in sqlmodel
            with patch('sqlmodel.Session', MockSession):
                response = test_client.get("/health")
                
                assert response.status_code == 200
                data = response.json()
                
                # Validate error response
                assert data["status"] == "unhealthy"
                assert data["database"]["connected"] is False
                assert "error" in data
