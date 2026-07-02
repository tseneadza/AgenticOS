#!/usr/bin/env python3
"""
Anthropic Usage and Settings Data Tool
Fetches API usage, billing, rate limits, and account settings from Anthropic
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import requests
from dotenv import load_dotenv

# Load .env.local for credentials
load_dotenv(os.path.expanduser("~/.env.local"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"


class AnthropicUsageClient:
    """Client for fetching Anthropic usage and settings data"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with API key from env or parameter"""
        self.api_key = api_key or ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. "
                "Set it in .env.local or as an environment variable."
            )
        self.base_url = ANTHROPIC_API_BASE
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }

    def _make_request(self, endpoint: str, method: str = "GET", **kwargs) -> Dict[str, Any]:
        """Make authenticated request to Anthropic API"""
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.request(
                method,
                url,
                headers=self.headers,
                timeout=10,
                **kwargs
            )
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except requests.exceptions.HTTPError as e:
            return {
                "success": False,
                "error": f"API Error: {e.response.status_code}",
                "details": str(e)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_account_info(self) -> Dict[str, Any]:
        """Get account information"""
        return self._make_request("/account")

    def get_usage_metrics(self) -> Dict[str, Any]:
        """Get API usage metrics (tokens, requests, cost)"""
        # Note: Usage data may be in /account endpoint or separate /usage endpoint
        response = self._make_request("/account")
        if response.get("success"):
            # Extract usage-related fields if available
            account_data = response.get("data", {})
            return {
                "success": True,
                "data": {
                    "account_id": account_data.get("account_id"),
                    "tier": account_data.get("tier"),
                    "usage": account_data.get("usage", {}),
                    "limits": account_data.get("limits", {}),
                    "request_limit": account_data.get("request_limit"),
                    "token_limit": account_data.get("token_limit"),
                }
            }
        return response

    def get_models(self) -> Dict[str, Any]:
        """Get available models and their info"""
        return self._make_request("/models")

    def get_rate_limits(self) -> Dict[str, Any]:
        """Get current rate limit information"""
        response = self.get_account_info()
        if response.get("success"):
            data = response.get("data", {})
            return {
                "success": True,
                "data": {
                    "rate_limits": data.get("rate_limits", {}),
                    "quota": data.get("quota", {}),
                    "request_limit": data.get("request_limit"),
                    "token_limit": data.get("token_limit"),
                }
            }
        return response

    def get_all_data(self) -> Dict[str, Any]:
        """Get all available data (account, usage, models, limits)"""
        account = self.get_account_info()
        models = self.get_models()

        return {
            "success": account.get("success", False) and models.get("success", False),
            "timestamp": datetime.now().isoformat(),
            "account": account.get("data", {}),
            "models": models.get("data", {}),
        }


def format_as_table(data: Dict[str, Any]) -> str:
    """Format data as a pretty ASCII table"""
    lines = []
    lines.append("=" * 80)
    lines.append("Anthropic Usage & Settings")
    lines.append("=" * 80)
    lines.append(f"Fetched: {datetime.now().isoformat()}")
    lines.append("")

    if "account" in data:
        account = data["account"]
        lines.append("ACCOUNT INFORMATION")
        lines.append("-" * 80)
        for key, value in account.items():
            if not key.startswith("_"):
                lines.append(f"  {key:.<40} {value}")
        lines.append("")

    if "models" in data:
        models = data["models"]
        if isinstance(models, dict) and "data" in models:
            lines.append("AVAILABLE MODELS")
            lines.append("-" * 80)
            for model in models["data"]:
                if isinstance(model, dict):
                    model_id = model.get("id", "Unknown")
                    lines.append(f"  • {model_id}")
        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)


def format_as_json(data: Dict[str, Any], pretty: bool = True) -> str:
    """Format data as JSON"""
    if pretty:
        return json.dumps(data, indent=2, default=str)
    return json.dumps(data, default=str)


def format_as_csv(data: Dict[str, Any]) -> str:
    """Format data as CSV"""
    lines = []
    lines.append("key,value")

    if "account" in data:
        account = data["account"]
        for key, value in account.items():
            if not key.startswith("_"):
                # Escape quotes for CSV
                value_str = str(value).replace('"', '""')
                lines.append(f'"{key}","{value_str}"')

    return "\n".join(lines)


def main_cli():
    """CLI interface for the tool"""
    import sys

    usage = """
    Usage: anthropic_usage.py <command> [--format FORMAT]

    Commands:
      account        Get account information
      usage          Get usage metrics
      models         Get available models
      limits         Get rate limits
      all            Get all data (default)

    Formats:
      --format json    Output as JSON (pretty-printed)
      --format json-compact  Output as compact JSON
      --format table   Output as ASCII table
      --format csv     Output as CSV

    Examples:
      python anthropic_usage.py all
      python anthropic_usage.py account --format json
      python anthropic_usage.py usage --format table
    """

    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]:
        print(usage)
        sys.exit(0)

    command = sys.argv[1]
    format_type = "table"  # default

    # Parse format flag
    for arg in sys.argv[2:]:
        if arg.startswith("--format"):
            idx = sys.argv.index(arg)
            if idx + 1 < len(sys.argv):
                format_type = sys.argv[idx + 1]

    try:
        client = AnthropicUsageClient()

        # Execute command
        if command == "account":
            result = client.get_account_info()
        elif command == "usage":
            result = client.get_usage_metrics()
        elif command == "models":
            result = client.get_models()
        elif command == "limits":
            result = client.get_rate_limits()
        elif command == "all":
            result = client.get_all_data()
        else:
            print(f"Unknown command: {command}")
            print(usage)
            sys.exit(1)

        # Format output
        if format_type == "json":
            output = format_as_json(result, pretty=True)
        elif format_type == "json-compact":
            output = format_as_json(result, pretty=False)
        elif format_type == "csv":
            output = format_as_csv(result)
        else:  # table (default)
            output = format_as_table(result)

        print(output)

    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


# Tool definitions for MCP registration
TOOLS = [
    {
        "name": "get_anthropic_account",
        "description": "Get Anthropic account information and settings",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_anthropic_usage",
        "description": "Get API usage metrics (tokens, requests, cost)",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_anthropic_models",
        "description": "Get available models and their information",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_anthropic_limits",
        "description": "Get rate limits and quota information",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_anthropic_all",
        "description": "Get all Anthropic account data (combined)",
        "inputSchema": {"type": "object", "properties": {}}
    },
]


def execute_tool(tool_name: str, input_args: Dict = None) -> Dict[str, Any]:
    """Execute an Anthropic usage tool"""
    try:
        client = AnthropicUsageClient()

        if tool_name == "get_anthropic_account":
            return client.get_account_info()
        elif tool_name == "get_anthropic_usage":
            return client.get_usage_metrics()
        elif tool_name == "get_anthropic_models":
            return client.get_models()
        elif tool_name == "get_anthropic_limits":
            return client.get_rate_limits()
        elif tool_name == "get_anthropic_all":
            return client.get_all_data()
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    main_cli()
