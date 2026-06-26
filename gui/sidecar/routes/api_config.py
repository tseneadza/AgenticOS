"""
Configuration management routes for Agentic OS.

Handles:
- GET /api/config — Fetch current LLM config + feature flags
- PUT /api/config — Save config changes (validates + tests connection)
- POST /api/config/test — Test LLM connection

Config is persisted to ~/.agentic-os/config.yaml
"""

from fastapi import APIRouter, HTTPException, Body
import os
import yaml
from pathlib import Path
import httpx
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Config file location
CONFIG_DIR = Path.home() / '.agentic-os'
CONFIG_FILE = CONFIG_DIR / 'config.yaml'

# Default config
DEFAULT_CONFIG = {
    'llm': {
        'activeModel': 'ollama',
        'ollama': {
            'host': 'http://localhost:12434'
        },
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


def ensure_config_dir():
    """Ensure config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config_file():
    """Load config from YAML file or return defaults."""
    ensure_config_dir()

    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, 'r') as f:
            loaded = yaml.safe_load(f) or {}
        # Merge with defaults to ensure all keys exist
        return {
            'llm': {**DEFAULT_CONFIG['llm'], **loaded.get('llm', {})},
            'flags': {**DEFAULT_CONFIG['flags'], **loaded.get('flags', {})}
        }
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return DEFAULT_CONFIG.copy()


def save_config_file(config):
    """Save config to YAML file with restricted permissions (0600)."""
    ensure_config_dir()

    try:
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        # Restrict permissions on config file (contains API keys)
        os.chmod(CONFIG_FILE, 0o600)
        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


async def test_llm_connection(config: dict) -> dict:
    """
    Test connection to configured LLM.

    Returns:
        {'status': 'connected'} on success
        {'status': 'error', 'details': '...'} on failure
    """
    try:
        active_model = config.get('llm', {}).get('activeModel')

        if active_model == 'ollama':
            host = config['llm']['ollama'].get('host', 'http://localhost:12434')
            test_url = f"{host}/api/tags"
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(test_url)
                if response.status_code == 200:
                    return {'status': 'connected'}
                else:
                    return {
                        'status': 'error',
                        'details': f"Ollama responded with status {response.status_code}"
                    }

        elif active_model == 'anthropic':
            base_url = config['llm']['anthropic'].get('baseUrl', 'https://api.anthropic.com/v1')
            api_key = config['llm']['anthropic'].get('apiKey', '')

            if not api_key:
                return {'status': 'error', 'details': 'API key is required for Anthropic'}

            # Test with a simple models list endpoint
            test_url = f"{base_url}/models"
            headers = {'x-api-key': api_key}
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(test_url, headers=headers)
                if response.status_code == 200:
                    return {'status': 'connected'}
                elif response.status_code == 401:
                    return {'status': 'error', 'details': 'Invalid API key'}
                else:
                    return {
                        'status': 'error',
                        'details': f"Anthropic responded with status {response.status_code}"
                    }

        else:
            return {'status': 'error', 'details': 'Unknown model type'}

    except httpx.ConnectError:
        return {'status': 'error', 'details': 'Connection refused — is the service running?'}
    except httpx.TimeoutException:
        return {'status': 'error', 'details': 'Connection timeout'}
    except Exception as e:
        return {'status': 'error', 'details': str(e)}


@router.get("/api/config")
async def get_config():
    """
    Fetch current LLM configuration.

    Returns the config from ~/.agentic-os/config.yaml or defaults.
    API keys are obfuscated in the response.
    """
    config = load_config_file()

    # Obfuscate API key in response
    if config['llm']['anthropic'].get('apiKey'):
        config['llm']['anthropic']['apiKey'] = '•••••'

    return config


@router.put("/api/config")
async def put_config(payload: dict):
    """
    Save configuration changes.

    Validates:
    - Model selection is valid (ollama or anthropic)
    - URLs are properly formatted
    - Required fields are present

    Tests connection before saving.
    """
    try:
        # Validate structure
        if 'llm' not in payload or 'flags' not in payload:
            raise HTTPException(status_code=400, detail="Missing 'llm' or 'flags' key")

        llm_config = payload['llm']
        active_model = llm_config.get('activeModel')

        if active_model not in ['ollama', 'anthropic']:
            raise HTTPException(status_code=400, detail="activeModel must be 'ollama' or 'anthropic'")

        # Validate Ollama config
        if active_model == 'ollama':
            ollama_host = llm_config.get('ollama', {}).get('host', '')
            if not ollama_host:
                raise HTTPException(status_code=400, detail="Ollama host is required")
            if not (ollama_host.startswith('http://') or ollama_host.startswith('https://')):
                raise HTTPException(status_code=400, detail="Ollama host must start with http:// or https://")

        # Validate Anthropic config
        if active_model == 'anthropic':
            anthropic_base_url = llm_config.get('anthropic', {}).get('baseUrl', '')
            anthropic_key = llm_config.get('anthropic', {}).get('apiKey', '')

            if not anthropic_base_url:
                raise HTTPException(status_code=400, detail="Anthropic baseUrl is required")
            if not (anthropic_base_url.startswith('http://') or anthropic_base_url.startswith('https://')):
                raise HTTPException(status_code=400, detail="Anthropic baseUrl must start with http:// or https://")
            if not anthropic_key or anthropic_key == '•••••':
                # If key wasn't changed, load current value
                current = load_config_file()
                payload['llm']['anthropic']['apiKey'] = current['llm']['anthropic'].get('apiKey', '')

        # Test connection
        test_result = await test_llm_connection(payload)
        if test_result['status'] != 'connected':
            raise HTTPException(
                status_code=400,
                detail=f"Connection test failed: {test_result.get('details', 'Unknown error')}"
            )

        # Save config
        if save_config_file(payload):
            logger.info(f"Config saved: {active_model} model selected")
            return {'status': 'saved', 'model': active_model}
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in put_config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/config/test")
async def post_config_test(payload: dict = Body(...)):
    """
    Test connection to the LLM endpoint.

    Request body:
    {
        "llm": { "activeModel": "ollama", ... },
        ...
    }

    Returns:
    {
        "status": "connected" | "error",
        "details": "..."
    }
    """
    try:
        result = await test_llm_connection(payload)
        return result
    except Exception as e:
        logger.error(f"Error in post_config_test: {e}")
        return {
            'status': 'error',
            'details': str(e)
        }
