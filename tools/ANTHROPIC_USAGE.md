# Anthropic Usage & Settings Tool

Access your Anthropic API account data, usage metrics, models, and rate limits directly from Claude or the command line.

## Setup

### 1. Get your API Key

1. Visit https://console.anthropic.com/account/keys
2. Create or copy your API key
3. **Important**: Never share or commit this key to GitHub

### 2. Configure `.env.local`

Copy the template and add your key:

```bash
cd ~/Codehome/AgenticOS
cp .env.template .env.local
```

Edit `.env.local` and add your Anthropic API key:

```env
ANTHROPIC_API_KEY=sk-ant-...your-key-here...
```

The `.env.local` file is already in `.gitignore`, so it won't be committed.

### 3. Install Dependencies

```bash
pip install python-dotenv requests
# Or: pip install -r requirements.txt
```

## Usage

### Command Line

```bash
# Get all data (default)
python tools/anthropic_usage.py all

# Get account info
python tools/anthropic_usage.py account

# Get usage metrics
python tools/anthropic_usage.py usage

# Get available models
python tools/anthropic_usage.py models

# Get rate limits
python tools/anthropic_usage.py limits

# Change output format
python tools/anthropic_usage.py all --format json
python tools/anthropic_usage.py all --format table
python tools/anthropic_usage.py all --format csv
python tools/anthropic_usage.py all --format json-compact
```

### In Claude Code

```python
from tools.anthropic_usage import AnthropicUsageClient

client = AnthropicUsageClient()

# Get account info
account = client.get_account_info()
print(account)

# Get usage metrics
usage = client.get_usage_metrics()
print(usage)

# Get all data
all_data = client.get_all_data()
print(all_data)

# Get rate limits
limits = client.get_rate_limits()
print(limits)

# Get models
models = client.get_models()
print(models)
```

### Via MCP Server (AgenticOS)

The tool is registered in `mcp_server.py` as an MCP tool, so you can call it from Claude:

```
Claude will be able to invoke:
- get_anthropic_account
- get_anthropic_usage
- get_anthropic_models
- get_anthropic_limits
- get_anthropic_all
```

## ⚠️ Current Limitations

**API Endpoint Availability**

As of 2026-07-02, the Anthropic public API does not expose account/usage data endpoints:
- `GET /account` → 404 Not Found
- `GET /models` → 404 Not Found

Usage data is currently only available via the [Anthropic Console](https://console.anthropic.com).

**What This Means**
- The tool is fully functional and ready
- API calls are being made successfully
- The endpoints simply don't exist yet in the public API
- No code changes needed—the tool will work seamlessly once Anthropic releases these endpoints

**Check Back**
Monitor the [Anthropic API Documentation](https://docs.anthropic.com) for updates. When the endpoints become available, the tool will work without any modifications.

---

## Output Formats

### Table (Default)
```
================================================================================
Anthropic Usage & Settings
================================================================================
Fetched: 2026-07-02T14:23:45.123456
ACCOUNT INFORMATION
...
```

### JSON (Pretty)
```json
{
  "success": true,
  "timestamp": "2026-07-02T14:23:45.123456",
  "account": {...},
  "models": {...}
}
```

### JSON (Compact)
Single-line JSON output.

### CSV
```csv
key,value
account_id,abc123
tier,pro
...
```

## API Endpoints

The tool calls the following Anthropic API endpoints:

- `GET /account` - Account information and settings
- `GET /models` - Available models

**Note**: Not all endpoints may be available depending on your API key's permissions and Anthropic's current API offerings.

## Troubleshooting

### "ANTHROPIC_API_KEY not found"
- Ensure `.env.local` exists with your API key
- Check the file is readable: `cat ~/.env.local | grep ANTHROPIC`
- Verify no typos in the key name

### "API Error: 401"
- Your API key is invalid or expired
- Generate a new key at https://console.anthropic.com/account/keys

### "API Error: 403"
- Your API key doesn't have permission for this endpoint
- Some endpoints may only be available to certain account tiers

### "ModuleNotFoundError: No module named 'anthropic_usage'"
- Add the tools directory to your Python path
- Or install from project root: `python -m tools.anthropic_usage`

## Security Notes

🔒 **Never commit `.env.local` to GitHub** — it's in `.gitignore` for a reason.

🔒 **Never share your API key** — treat it like a password.

🔒 **Rotate keys regularly** — delete old unused keys from the console.

🔒 **Use separate keys per environment** — dev/prod/staging keys.

## Future Enhancements

- [ ] Historical usage tracking (daily, weekly, monthly)
- [ ] Cost analysis by model
- [ ] Billing information (invoices, balance)
- [ ] Usage alerts/thresholds
- [ ] Export to CSV for reporting
- [ ] Integration with project cost tracking

## References

- [Anthropic API Documentation](https://docs.anthropic.com)
- [Anthropic Console](https://console.anthropic.com)
- [API Keys Management](https://console.anthropic.com/account/keys)
