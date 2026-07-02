# Anthropic Usage & Settings Tool - Setup Guide

## Overview

A secure, flexible tool to access your Anthropic API account data, usage metrics, models, and rate limits from Claude Code, the command line, or the AgenticOS MCP server.

**Created**: 2026-07-02  
**Status**: Ready to use

## What You Can Access

- **Account Information** - Account ID, tier, organization details
- **Usage Metrics** - API tokens used, requests made, costs
- **Available Models** - List of Claude models you have access to
- **Rate Limits** - Current rate limits and quota information
- **All Data** - Combined account + models + metrics in one call

## Files Created

```
AgenticOS/
├── .env.template              ← Copy to .env.local and fill in your API key
├── requirements.txt           ← Updated: added python-dotenv
├── mcp_server.py             ← Updated: added Anthropic tool registration
├── tools/
│   ├── anthropic_usage.py           ← Main tool implementation
│   ├── ANTHROPIC_USAGE.md            ← User documentation
│   ├── ANTHROPIC_USAGE_EXAMPLES.py   ← Code examples
│   └── (existing tools)
└── docs/
    └── ANTHROPIC_USAGE_TOOL_SETUP.md ← This file
```

## Quick Start (3 steps)

### Step 1: Get Your API Key

```bash
# Visit and copy your key from:
# https://console.anthropic.com/account/keys
```

### Step 2: Configure `.env.local`

```bash
cd ~/Codehome/AgenticOS
cp .env.template .env.local

# Edit .env.local and add your API key:
# ANTHROPIC_API_KEY=sk-ant-...
```

### Step 3: Test It

```bash
# Install dependencies (first time only)
pip install -r requirements.txt

# Try it out
python tools/anthropic_usage.py all

# Or via Claude Code (if using the agentic-mcp-tools skill)
# The tool will be available as a callable function
```

## Usage Methods

### 1. Command Line

```bash
# All data (default, table format)
python tools/anthropic_usage.py all

# Specific queries
python tools/anthropic_usage.py account      # Account info only
python tools/anthropic_usage.py usage        # Usage metrics
python tools/anthropic_usage.py models       # Available models
python tools/anthropic_usage.py limits       # Rate limits

# Change output format
python tools/anthropic_usage.py all --format json
python tools/anthropic_usage.py all --format table
python tools/anthropic_usage.py all --format csv
```

### 2. Python/Claude Code

```python
from tools.anthropic_usage import AnthropicUsageClient

client = AnthropicUsageClient()

# Get data
account = client.get_account_info()      # Dict with account info
usage = client.get_usage_metrics()       # Dict with usage data
models = client.get_models()             # Dict with available models
limits = client.get_rate_limits()        # Dict with rate limit info
all_data = client.get_all_data()         # Combined data

# Check for errors
if account.get("success"):
    print(account["data"])
else:
    print(f"Error: {account['error']}")
```

### 3. MCP Server (AgenticOS)

The tool is registered in `mcp_server.py` and available as MCP tools:

- `get_anthropic_account` - Account information
- `get_anthropic_usage` - Usage metrics
- `get_anthropic_models` - Available models
- `get_anthropic_limits` - Rate limits
- `get_anthropic_all` - All data combined

These can be called from Claude when using the agentic-mcp-tools skill.

## Security

✅ **Best Practices Implemented:**

1. **Secrets not in Git** - `.env.local` is in `.gitignore`
2. **Template Provided** - `.env.template` shows structure (no real keys)
3. **Flexible Loading** - Reads from environment variables, `.env.local`, or parameter
4. **No Hardcoding** - Keys loaded at runtime, not baked into code

⚠️ **Important Security Notes:**

- 🔒 Never commit `.env.local` to GitHub
- 🔒 Never paste your API key in chat or shared documents
- 🔒 Treat API keys like passwords
- 🔒 Rotate keys regularly at https://console.anthropic.com/account/keys
- 🔒 Use separate keys for dev/prod/staging if possible

## Troubleshooting

### "ANTHROPIC_API_KEY not found"

The tool can't find your API key. Fix:

```bash
# Check if .env.local exists
ls -la ~/.env.local

# Check if it has your key
grep ANTHROPIC ~/.env.local

# If missing, create it:
cp .env.template .env.local
# Edit with your real key
```

### "ModuleNotFoundError: No module named 'anthropic_usage'"

```bash
# Install dependencies
pip install -r requirements.txt

# Or run from project root:
cd ~/Codehome/AgenticOS
python tools/anthropic_usage.py all
```

### "API Error: 401 Unauthorized"

Your API key is invalid or expired:

```bash
# Generate a new key at:
# https://console.anthropic.com/account/keys

# Update .env.local with the new key
```

### "API Error: 403 Forbidden"

Your API key doesn't have permission for this operation:

- Some endpoints may only work with certain account tiers
- Contact Anthropic support if you think this is wrong

## Examples

### Example: Check Daily Usage

```python
from tools.anthropic_usage import AnthropicUsageClient

client = AnthropicUsageClient()
usage = client.get_usage_metrics()

if usage.get("success"):
    print(f"Usage data: {usage['data']}")
else:
    print(f"Error: {usage['error']}")
```

### Example: List Available Models

```python
from tools.anthropic_usage import AnthropicUsageClient

client = AnthropicUsageClient()
models = client.get_models()

if models.get("success"):
    for model in models["data"].get("data", []):
        print(f"- {model['id']}")
```

### Example: Display As Table

```bash
# Pretty-printed table (default)
python tools/anthropic_usage.py all

# JSON output for processing
python tools/anthropic_usage.py all --format json | jq .
```

## Extending the Tool

Want to add more features? The tool is designed to be modular:

```python
# In tools/anthropic_usage.py, add a new method:
def get_billing_info(self):
    """Get billing information"""
    return self._make_request("/billing")  # Add this endpoint when available

# Add to TOOLS list for MCP registration
# Add to execute_tool() for CLI support
```

## Future Enhancements

- [ ] Historical usage charts (daily/weekly/monthly)
- [ ] Cost breakdown by model
- [ ] Billing invoice access
- [ ] Usage alerts (notify when approaching limits)
- [ ] Export to CSV/JSON for reporting
- [ ] Integration with cost tracking dashboard in AgenticOS GUI
- [ ] Webhook support for usage events

## References

- **Anthropic API Docs**: https://docs.anthropic.com
- **API Console**: https://console.anthropic.com
- **API Keys Page**: https://console.anthropic.com/account/keys
- **Models Available**: https://docs.anthropic.com/claude/reference/getting-started-with-the-api

## Support

If you encounter issues:

1. Check `.env.local` exists and has your API key
2. Verify the key is valid at https://console.anthropic.com/account/keys
3. Run `python tools/anthropic_usage.py account` to test connectivity
4. Check the error message for specific issues (401 = invalid key, 403 = permissions)
5. Review the troubleshooting section above

## Notes

- All API calls are to Anthropic's official API (`https://api.anthropic.com/v1`)
- Requests are read-only (no modifications to your account)
- API responses are returned as-is (no caching or transformation by default)
- Timeout is set to 10 seconds per request
- Works on macOS, Linux, and Windows

---

**Last Updated**: 2026-07-02  
**Ready for**: Production use, Claude Code integration, MCP server integration
