"""
Tests for config management API routes.

Tests GET/PUT/POST config endpoints for LLM configuration and feature flags.
"""

import pytest
from fastapi.testclient import TestClient
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock

# Mock the config file location
@pytest.fixture
def temp_config_dir(monkeypatch):
    """Create temporary config directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv('HOME', tmpdir)
        yield Path(tmpdir) / '.agentic-os'


@pytest.fixture
def client(temp_config_dir):
    """Create FastAPI test client with mocked config directory."""
    from gui.sidecar.routes.api_config import router, CONFIG_DIR, CONFIG_FILE
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    # Patch the CONFIG_DIR and CONFIG_FILE
    with patch('gui.sidecar.routes.api_config.CONFIG_DIR', temp_config_dir):
        with patch('gui.sidecar.routes.api_config.CONFIG_FILE', temp_config_dir / 'config.yaml'):
            yield TestClient(app)


class TestGetConfig:
    """Tests for GET /api/config endpoint."""

    def test_get_config_returns_defaults(self, client):
        """GET /api/config returns default config when no file exists."""
        response = client.get('/api/config')
        assert response.status_code == 200
        data = response.json()

        assert 'llm' in data
        assert 'flags' in data
        assert data['llm']['activeModel'] == 'ollama'
        assert data['llm']['ollama']['host'] == 'http://localhost:11434'

    def test_get_config_obfuscates_api_key(self, client):
        """GET /api/config obfuscates Anthropic API key."""
        # First, set up a config with an API key
        config_payload = {
            'llm': {
                'activeModel': 'anthropic',
                'ollama': {'host': 'http://localhost:11434'},
                'anthropic': {
                    'baseUrl': 'https://api.anthropic.com/v1',
                    'apiKey': 'sk-ant-test-key-12345'
                }
            },
            'flags': {
                'shellCommands': True,
                'brain2Integration': True,
                'hubAbsorption': False
            }
        }

        with patch('gui.sidecar.routes.api_config.test_llm_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {'status': 'connected'}
            response = client.put('/api/config', json=config_payload)
            assert response.status_code == 200

        # Now fetch and verify key is obfuscated
        response = client.get('/api/config')
        data = response.json()
        assert data['llm']['anthropic']['apiKey'] == '•••••'

    def test_get_config_includes_all_flags(self, client):
        """GET /api/config includes all feature flags."""
        response = client.get('/api/config')
        data = response.json()

        assert 'shellCommands' in data['flags']
        assert 'brain2Integration' in data['flags']
        assert 'hubAbsorption' in data['flags']


class TestPutConfig:
    """Tests for PUT /api/config endpoint."""

    def test_put_config_saves_valid_ollama_config(self, client):
        """PUT /api/config saves valid Ollama configuration."""
        config_payload = {
            'llm': {
                'activeModel': 'ollama',
                'ollama': {'host': 'http://localhost:11434'},
                'anthropic': {
                    'baseUrl': 'https://api.anthropic.com/v1',
                    'apiKey': ''
                }
            },
            'flags': {
                'shellCommands': True,
                'brain2Integration': True,
                'hubAbsorption': False
            }
        }

        with patch('gui.sidecar.routes.api_config.test_llm_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {'status': 'connected'}
            response = client.put('/api/config', json=config_payload)

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'saved'
        assert data['model'] == 'ollama'

    def test_put_config_saves_valid_anthropic_config(self, client):
        """PUT /api/config saves valid Anthropic configuration."""
        config_payload = {
            'llm': {
                'activeModel': 'anthropic',
                'ollama': {'host': 'http://localhost:11434'},
                'anthropic': {
                    'baseUrl': 'https://api.anthropic.com/v1',
                    'apiKey': 'sk-ant-test-key'
                }
            },
            'flags': {
                'shellCommands': True,
                'brain2Integration': True,
                'hubAbsorption': False
            }
        }

        with patch('gui.sidecar.routes.api_config.test_llm_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {'status': 'connected'}
            response = client.put('/api/config', json=config_payload)

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'saved'
        assert data['model'] == 'anthropic'

    def test_put_config_rejects_invalid_model(self, client):
        """PUT /api/config rejects invalid model type."""
        config_payload = {
            'llm': {
                'activeModel': 'invalid_model',
                'ollama': {'host': 'http://localhost:11434'},
                'anthropic': {'baseUrl': '', 'apiKey': ''}
            },
            'flags': {}
        }

        response = client.put('/api/config', json=config_payload)
        assert response.status_code == 400
        assert 'activeModel must be' in response.json()['detail']

    def test_put_config_rejects_invalid_ollama_host(self, client):
        """PUT /api/config rejects invalid Ollama host URL."""
        config_payload = {
            'llm': {
                'activeModel': 'ollama',
                'ollama': {'host': 'not-a-valid-url'},
                'anthropic': {'baseUrl': '', 'apiKey': ''}
            },
            'flags': {}
        }

        response = client.put('/api/config', json=config_payload)
        assert response.status_code == 400
        assert 'http://' in response.json()['detail'] or 'https://' in response.json()['detail']

    def test_put_config_rejects_missing_anthropic_key(self, client):
        """PUT /api/config rejects Anthropic config without API key."""
        config_payload = {
            'llm': {
                'activeModel': 'anthropic',
                'ollama': {'host': 'http://localhost:11434'},
                'anthropic': {
                    'baseUrl': 'https://api.anthropic.com/v1',
                    'apiKey': ''  # Missing key
                }
            },
            'flags': {}
        }

        response = client.put('/api/config', json=config_payload)
        assert response.status_code == 400

    def test_put_config_rejects_connection_failure(self, client):
        """PUT /api/config rejects config if connection test fails."""
        config_payload = {
            'llm': {
                'activeModel': 'ollama',
                'ollama': {'host': 'http://localhost:11434'},
                'anthropic': {'baseUrl': '', 'apiKey': ''}
            },
            'flags': {}
        }

        with patch('gui.sidecar.routes.api_config.test_llm_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {
                'status': 'error',
                'details': 'Connection refused'
            }
            response = client.put('/api/config', json=config_payload)

        assert response.status_code == 400
        assert 'Connection refused' in response.json()['detail']

    def test_put_config_validates_url_format(self, client):
        """PUT /api/config validates URL formats."""
        config_payload = {
            'llm': {
                'activeModel': 'anthropic',
                'ollama': {'host': 'http://localhost:11434'},
                'anthropic': {
                    'baseUrl': 'not-a-url',  # Invalid
                    'apiKey': 'sk-ant-test'
                }
            },
            'flags': {}
        }

        response = client.put('/api/config', json=config_payload)
        assert response.status_code == 400


class TestPostConfigTest:
    """Tests for POST /api/config/test endpoint."""

    def test_post_config_test_ollama_success(self, client):
        """POST /api/config/test connects to Ollama successfully."""
        config_payload = {
            'llm': {
                'activeModel': 'ollama',
                'ollama': {'host': 'http://localhost:11434'},
                'anthropic': {'baseUrl': '', 'apiKey': ''}
            }
        }

        with patch('gui.sidecar.routes.api_config.test_llm_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {'status': 'connected'}
            response = client.post('/api/config/test', json=config_payload)

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'connected'

    def test_post_config_test_ollama_failure(self, client):
        """POST /api/config/test handles Ollama connection failure."""
        config_payload = {
            'llm': {
                'activeModel': 'ollama',
                'ollama': {'host': 'http://localhost:11434'},
                'anthropic': {'baseUrl': '', 'apiKey': ''}
            }
        }

        with patch('gui.sidecar.routes.api_config.test_llm_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {
                'status': 'error',
                'details': 'Connection refused'
            }
            response = client.post('/api/config/test', json=config_payload)

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'error'
        assert 'Connection refused' in data['details']

    def test_post_config_test_anthropic_success(self, client):
        """POST /api/config/test connects to Anthropic successfully."""
        config_payload = {
            'llm': {
                'activeModel': 'anthropic',
                'ollama': {'host': ''},
                'anthropic': {
                    'baseUrl': 'https://api.anthropic.com/v1',
                    'apiKey': 'sk-ant-test-key'
                }
            }
        }

        with patch('gui.sidecar.routes.api_config.test_llm_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {'status': 'connected'}
            response = client.post('/api/config/test', json=config_payload)

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'connected'

    def test_post_config_test_anthropic_invalid_key(self, client):
        """POST /api/config/test handles invalid Anthropic API key."""
        config_payload = {
            'llm': {
                'activeModel': 'anthropic',
                'ollama': {'host': ''},
                'anthropic': {
                    'baseUrl': 'https://api.anthropic.com/v1',
                    'apiKey': 'invalid-key'
                }
            }
        }

        with patch('gui.sidecar.routes.api_config.test_llm_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {
                'status': 'error',
                'details': 'Invalid API key'
            }
            response = client.post('/api/config/test', json=config_payload)

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'error'
        assert 'API key' in data['details']


class TestConfigFilePersistence:
    """Tests for config file persistence."""

    def test_config_persists_to_yaml_file(self, client):
        """Config is saved to ~/.agentic-os/config.yaml on PUT."""
        config_payload = {
            'llm': {
                'activeModel': 'ollama',
                'ollama': {'host': 'http://localhost:9999'},
                'anthropic': {'baseUrl': '', 'apiKey': ''}
            },
            'flags': {
                'shellCommands': True,
                'brain2Integration': False,
                'hubAbsorption': False
            }
        }

        with patch('gui.sidecar.routes.api_config.test_llm_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {'status': 'connected'}
            response = client.put('/api/config', json=config_payload)

        assert response.status_code == 200

        # Verify it was saved by making a GET request
        response = client.get('/api/config')
        data = response.json()
        assert data['llm']['ollama']['host'] == 'http://localhost:9999'
        assert data['flags']['brain2Integration'] is False

    def test_config_file_has_restricted_permissions(self, client, temp_config_dir):
        """Config file is saved with mode 0600 for security."""
        config_payload = {
            'llm': {
                'activeModel': 'ollama',
                'ollama': {'host': 'http://localhost:11434'},
                'anthropic': {'baseUrl': '', 'apiKey': 'sensitive-key'}
            },
            'flags': {}
        }

        with patch('gui.sidecar.routes.api_config.test_llm_connection', new_callable=AsyncMock) as mock_test:
            mock_test.return_value = {'status': 'connected'}
            response = client.put('/api/config', json=config_payload)

        assert response.status_code == 200

        # Check file permissions (0600 = 384 in decimal)
        config_file = temp_config_dir / 'config.yaml'
        if config_file.exists():
            mode = os.stat(config_file).st_mode
            # Owner should have read+write (0600)
            assert (mode & 0o077) == 0  # No permissions for group/other
