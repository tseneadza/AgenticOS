#!/usr/bin/env python3
"""
AgenticOS MCP Server
Enables Claude to run build, test, and git commands directly on macOS
"""

import subprocess
import json
from pathlib import Path

# Project root
PROJECT_ROOT = Path("/Users/tonyseneadza/Codehome/AgenticOS")
GUI_DESKTOP = PROJECT_ROOT / "gui/desktop"


def run_command(cmd, cwd=None, capture=True):
    """Execute shell command and return output"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd or PROJECT_ROOT,
            capture_output=capture,
            text=True,
            timeout=300
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out after 5 minutes"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_tests():
    """Run the full test suite"""
    return run_command(
        "npm test -- --run",
        cwd=str(GUI_DESKTOP)
    )


def run_tests_watch():
    """Run tests in watch mode (interactive)"""
    return run_command(
        "npm test",
        cwd=str(GUI_DESKTOP),
        capture=False
    )


def build_app():
    """Build the Tauri app"""
    return run_command(
        "npm run build",
        cwd=str(GUI_DESKTOP)
    )


def build_debug():
    """Build debug bundle for testing"""
    return run_command(
        "cd gui/desktop && npm run tauri -- build --debug --bundles app",
        cwd=str(PROJECT_ROOT)
    )


def dev_server():
    """Start dev server (interactive)"""
    return run_command(
        "npm run tauri dev",
        cwd=str(GUI_DESKTOP),
        capture=False
    )


def verify_build():
    """Run build verification script"""
    return run_command(
        "bash build-and-verify.sh",
        cwd=str(PROJECT_ROOT)
    )


def git_status():
    """Get git status"""
    return run_command(
        "git status --short"
    )


def git_log_recent():
    """Show recent commits"""
    return run_command(
        "git log --oneline -20"
    )


def git_add(pattern="."):
    """Stage files for commit using git add"""
    return run_command(
        f'git add "{pattern}"'
    )


def git_commit(message):
    """Create a commit with the given message"""
    # Escape quotes in message for shell safety
    safe_message = message.replace('"', '\\"')
    return run_command(
        f'git commit -m "{safe_message}"'
    )


def git_push(remote="origin", branch=None):
    """Push commits to remote repository"""
    if branch:
        cmd = f"git push {remote} {branch}"
    else:
        # Push current branch
        cmd = f"git push {remote}"
    return run_command(cmd)


def check_components():
    """List all extracted components"""
    components_dir = GUI_DESKTOP / "src/components"
    components = sorted([f.stem for f in components_dir.glob("*.jsx") if not f.name.startswith("_")])
    return {"success": True, "components": components, "count": len(components)}


def count_lines():
    """Count lines in component files"""
    components_dir = GUI_DESKTOP / "src/components"
    results = {}
    for f in sorted(components_dir.glob("*.jsx")):
        if not f.name.startswith("_"):
            lines = len(f.read_text().splitlines())
            results[f.name] = lines
    return {"success": True, "files": results}


# MCP Tool Definitions (for registration)
TOOLS = [
    {
        "name": "run_tests",
        "description": "Run full test suite (all 238 tests)",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "run_tests_watch",
        "description": "Run tests in watch mode (interactive, for development)",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "build_app",
        "description": "Build the Tauri app for distribution",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "build_debug",
        "description": "Build debug bundle for local testing",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "dev_server",
        "description": "Start dev server with hot reload (interactive)",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "verify_build",
        "description": "Run build verification script (quick check)",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "git_status",
        "description": "Check git status",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "git_log_recent",
        "description": "Show last 20 commits",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "git_add",
        "description": "Stage files for commit (git add). Default: stage all files ('.')",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "File pattern to stage (e.g., '.', 'src/', 'docs/CHANGELOG.md')",
                    "default": "."
                }
            }
        }
    },
    {
        "name": "git_commit",
        "description": "Create a commit with the given message",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message (required)"
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "git_push",
        "description": "Push commits to remote repository (default: origin, current branch)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote": {
                    "type": "string",
                    "description": "Remote name (e.g., 'origin', 'upstream')",
                    "default": "origin"
                },
                "branch": {
                    "type": "string",
                    "description": "Branch name (optional; if omitted, pushes current branch)"
                }
            }
        }
    },
    {
        "name": "check_components",
        "description": "List all extracted components",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "count_lines",
        "description": "Count lines in each component file",
        "inputSchema": {"type": "object", "properties": {}}
    }
]


def execute_tool(tool_name, input_args=None):
    """Execute a tool by name with optional arguments"""
    # Tools that don't take arguments
    no_arg_tools = {
        "run_tests": run_tests,
        "run_tests_watch": run_tests_watch,
        "build_app": build_app,
        "build_debug": build_debug,
        "dev_server": dev_server,
        "verify_build": verify_build,
        "git_status": git_status,
        "git_log_recent": git_log_recent,
        "check_components": check_components,
        "count_lines": count_lines,
    }

    # Tools that take arguments
    arg_tools = {
        "git_add": git_add,
        "git_commit": git_commit,
        "git_push": git_push,
    }

    if tool_name in no_arg_tools:
        return no_arg_tools[tool_name]()
    elif tool_name in arg_tools:
        if input_args is None:
            input_args = {}
        return arg_tools[tool_name](**input_args)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: mcp_server.py <tool_name> [args...]")
        print("\nAvailable tools:")
        for tool in TOOLS:
            print(f"\n  {tool['name']}")
            print(f"    {tool['description']}")
            props = tool.get("inputSchema", {}).get("properties", {})
            if props:
                print(f"    Parameters:")
                for prop_name, prop_info in props.items():
                    print(f"      - {prop_name}: {prop_info.get('description', '')}")
        print("\nExamples:")
        print("  mcp_server.py git_status")
        print("  mcp_server.py git_add .")
        print("  mcp_server.py git_commit 'Initial commit'")
        print("  mcp_server.py git_push origin main")
        sys.exit(1)

    tool_name = sys.argv[1]

    # Parse arguments based on tool
    input_args = {}
    if tool_name == "git_add" and len(sys.argv) > 2:
        input_args["pattern"] = sys.argv[2]
    elif tool_name == "git_commit" and len(sys.argv) > 2:
        input_args["message"] = sys.argv[2]
    elif tool_name == "git_push":
        if len(sys.argv) > 2:
            input_args["remote"] = sys.argv[2]
        if len(sys.argv) > 3:
            input_args["branch"] = sys.argv[3]

    result = execute_tool(tool_name, input_args)
    print(json.dumps(result, indent=2))
