# agentic-mcp-tools Skill

A comprehensive Claude skill that wraps the AgenticOS MCP server, providing direct access to build, test, and git commands without leaving the Claude interface.

## Contents

- **SKILL.md** — Main skill definition with all 13 tools documented
  - 5 build/test tools (run_tests, build_app, build_debug, dev_server, verify_build)
  - 5 git tools (git_status, git_log_recent, git_add, git_commit, git_push)
  - 3 inspection tools (check_components, count_lines)

- **evals/evals.json** — 7 comprehensive test cases covering:
  - Unit + integration test execution
  - Git workflow (status → add → commit → push)
  - Build verification and debugging
  - Component inspection and metrics
  - Error handling and edge cases

- **references/mcp-server-api.md** — Detailed API documentation
  - Server location and invocation syntax
  - Each tool's parameters, output format, and behavior
  - Common workflows and examples
  - Error handling and troubleshooting

## Installation

### Option 1: Copy to Cowork Skills Directory
```bash
cp -r /Users/tonyseneadza/Codehome/AgenticOS/agentic-mcp-skill \
  ~/.cowork/skills/
```

### Option 2: Manual Installation in Claude Settings
1. Cowork Settings > Capabilities > Skills
2. Add new skill directory pointing to this folder
3. Restart Cowork

## Usage

Once installed, reference the skill in Claude:

> "I finished Phase 7 integration tests. Run the full test suite to verify everything passes."

Claude will automatically use the agentic-mcp-tools skill to execute tests.

## Key Features

✅ **13 Integrated Tools** — All AgenticOS build, test, and git operations  
✅ **Secure Git Auth** — Uses SSH keys, no credentials stored in code  
✅ **Comprehensive Docs** — SKILL.md + detailed API reference  
✅ **Test Coverage** — 7 realistic test cases with assertions  
✅ **Error Handling** — Graceful failures with helpful messages  

## Phase 7 Integration

This skill is designed for Phase 7+ AgenticOS development:
- Verifies 238 unit tests + 98 integration tests pass
- Automates commit/push workflow after test verification
- Supports all build modes (debug, production, verification)
- Inspects component structure and code metrics

## Common Commands

**Run tests after changes:**
```
"Run the full test suite and tell me if Phase 6 + 7 tests pass"
```

**Commit and push changes:**
```
"Stage all changes, commit with 'Phase 7 integration tests complete', and push to main"
```

**Check build before release:**
```
"Run build verification and list all components"
```

**Inspect recent history:**
```
"Show me the last 20 commits to see what's been done"
```

## Security

- **SSH Authentication:** git_push uses ~/.ssh keys (no passwords)
- **No Credential Storage:** No tokens, passwords, or keys in skill code
- **Local Execution:** All commands run on your Mac (not in Claude cloud)
- **Safe for AI:** Credentials never appear in Claude's API calls

## Architecture

```
agentic-mcp-skill/
├── SKILL.md                 (Main skill definition)
├── README.md               (This file)
├── evals/
│   └── evals.json         (Test cases with assertions)
└── references/
    └── mcp-server-api.md  (Detailed API documentation)
```

The skill wraps `/Users/tonyseneadza/Codehome/AgenticOS/mcp_server.py`, which is the actual MCP server that orchestrates all commands.

## Testing

Test cases verify:
1. ✅ Test suite execution and output parsing
2. ✅ Git workflow (status → add → commit → push)
3. ✅ Build verification and debugging
4. ✅ Component introspection
5. ✅ Error handling for auth/timeout scenarios
6. ✅ Proper JSON response formatting
7. ✅ Git history inspection

## Support

For issues or questions:
1. Check **references/mcp-server-api.md** for detailed API docs
2. Review **SKILL.md** for tool descriptions and examples
3. Check **evals/evals.json** for expected behavior
4. Run `git_status` to verify git is working
5. Run `verify_build` for project health check

## Related Documentation

- **CLAUDE.md** — AgenticOS project rules and conventions
- **PHASE7_INTEGRATION_STRATEGY.md** — Integration testing strategy
- **TESTING_GUIDE.md** — Unit test patterns and conventions
- **CONTINUATION.md** — Session memory and current phase status

---

**Version:** 1.0  
**Created:** 2026-06-30  
**Phase:** 7+ (Integration Testing & Beyond)  
**Status:** Ready for Installation
