#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
VERSION=$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo "unknown")

echo "========================================"
echo "  Agentic Workflow Installer v${VERSION}"
echo "========================================"
echo ""

# Check prerequisites
echo "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    echo "  ✗ Python 3 not found"
    echo ""
    read -p "Install python3? (requires sudo) [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y python3
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y python3
        elif command -v brew &> /dev/null; then
            brew install python3
        else
            echo "  ✗ Could not detect package manager. Please install python3 manually."
            exit 1
        fi
    else
        echo "  ✗ Python 3 is required. Please install it and re-run."
        exit 1
    fi
fi
echo "  ✓ Python 3 found: $(python3 --version)"
echo ""

# Create directories if they don't exist
mkdir -p "$CLAUDE_DIR/commands"
mkdir -p "$CLAUDE_DIR/agents"
mkdir -p "$CLAUDE_DIR/scripts"

# Remove old workflow commands (renamed to crew) - only if they're ours
if [ -f "$CLAUDE_DIR/commands/workflow.md" ]; then
  # Check if it's our agentic-workflow file by looking for a marker
  if grep -q "Agentic Development Workflow" "$CLAUDE_DIR/commands/workflow.md" 2>/dev/null; then
    echo "Removing old workflow commands (renamed to /crew)..."
    rm -f "$CLAUDE_DIR/commands/workflow.md"
    rm -f "$CLAUDE_DIR/commands/workflow-config.md"
    rm -f "$CLAUDE_DIR/commands/workflow-status.md"
    rm -f "$CLAUDE_DIR/commands/workflow-resume.md"
    echo "  ✓ Removed legacy /workflow commands"
    echo ""
  else
    echo "  ⚠ Found workflow.md but it's not from agentic-workflow - keeping it"
    echo ""
  fi
fi

# Copy commands
echo "Installing commands..."
cp "$SCRIPT_DIR/commands/"*.md "$CLAUDE_DIR/commands/"
echo "  ✓ crew.md"
echo "  ✓ crew-config.md"
echo "  ✓ crew-resume.md"

# Build agents using multi-platform build script
echo ""
echo "Installing agents..."
python3 "$SCRIPT_DIR/scripts/build-agents.py" claude --output "$HOME/.claude" || {
  echo "  ✗ Failed to build agents"
  exit 1
}

# Copy scripts for workflow enforcement
echo ""
echo "Installing enforcement scripts..."
cp "$SCRIPT_DIR/scripts/"*.py "$CLAUDE_DIR/scripts/"
chmod +x "$CLAUDE_DIR/scripts/"*.py
echo "  ✓ workflow_state.py (state management)"
echo "  ✓ validate-transition.py (PreToolUse hook)"
echo "  ✓ check-workflow-complete.py (Stop hook)"

# Copy config (backup existing if present)
echo ""
echo "Installing config..."
if [ -f "$CLAUDE_DIR/workflow-config.yaml" ]; then
  echo "  ⚠ Existing config found, creating backup..."
  cp "$CLAUDE_DIR/workflow-config.yaml" "$CLAUDE_DIR/workflow-config.yaml.backup.$(date +%Y%m%d%H%M%S)"
fi
cp "$SCRIPT_DIR/config/workflow-config.yaml" "$CLAUDE_DIR/"
echo "  ✓ workflow-config.yaml"

# Install MCP server
echo ""
echo "Installing MCP server..."
MCP_SERVER_DIR="$SCRIPT_DIR/mcp/agentic-workflow-server"

if [ -d "$MCP_SERVER_DIR" ]; then
  # Check if pip/pip3 is available
  if command -v pip3 &> /dev/null; then
    PIP_CMD="pip3"
  elif command -v pip &> /dev/null; then
    PIP_CMD="pip"
  else
    echo "  ⚠ pip not found, skipping MCP server installation"
    echo "    Install with: pip install -e $MCP_SERVER_DIR"
    PIP_CMD=""
  fi

  if [ -n "$PIP_CMD" ]; then
    # Install in editable mode for development
    echo "  Installing Python package..."
    $PIP_CMD install -q -e "$MCP_SERVER_DIR" 2>/dev/null || {
      echo "  ⚠ Failed to install MCP server package"
      echo "    Try manually: $PIP_CMD install -e $MCP_SERVER_DIR"
    }

    # Register MCP server with Claude if claude CLI is available
    if command -v claude &> /dev/null; then
      echo "  Registering MCP server with Claude..."
      # Remove existing registration if present
      claude mcp remove agentic-workflow 2>/dev/null || true
      # Add new registration using stdio transport
      claude mcp add agentic-workflow -s user -- python3 -m agentic_workflow_server.server 2>/dev/null && {
        echo "  ✓ MCP server registered: agentic-workflow"
      } || {
        echo "  ⚠ Failed to register MCP server"
        echo "    Try manually: claude mcp add agentic-workflow -s user -- python3 -m agentic_workflow_server.server"
      }
    else
      echo "  ⚠ Claude CLI not found, skipping MCP registration"
      echo "    Register manually with: claude mcp add agentic-workflow -s user -- python3 -m agentic_workflow_server.server"
    fi
  fi
else
  echo "  ⚠ MCP server directory not found: $MCP_SERVER_DIR"
fi

# Set up hooks in settings.json
echo ""
echo "Configuring enforcement hooks..."

SETTINGS_FILE="$CLAUDE_DIR/settings.json"
HOOKS_TEMPLATE="$SCRIPT_DIR/config/hooks-settings.json"

if [ -f "$SETTINGS_FILE" ]; then
  echo "  Existing settings.json found, merging hooks..."

  # Use Python to merge JSON (more reliable than jq for complex merging)
  python3 << 'PYTHON_SCRIPT'
import json
import sys
import os

settings_file = os.path.expanduser("~/.claude/settings.json")
hooks_file = os.path.join(os.path.dirname(os.path.abspath("$SCRIPT_DIR")), "config/hooks-settings.json")

# Read existing settings
with open(settings_file, 'r') as f:
    settings = json.load(f)

# Read hooks template
hooks_template = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Task",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 ~/.claude/scripts/validate-transition.py"
                    }
                ]
            }
        ],
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 ~/.claude/scripts/check-workflow-complete.py"
                    }
                ]
            }
        ]
    }
}

# Merge hooks
if "hooks" not in settings:
    settings["hooks"] = {}

for hook_type, hook_configs in hooks_template["hooks"].items():
    if hook_type not in settings["hooks"]:
        settings["hooks"][hook_type] = []

    # Check if our hooks are already present
    existing_commands = set()
    for hook in settings["hooks"][hook_type]:
        for h in hook.get("hooks", []):
            if h.get("type") == "command":
                existing_commands.add(h.get("command", ""))

    # Add our hooks if not present
    for new_hook in hook_configs:
        for h in new_hook.get("hooks", []):
            if h.get("type") == "command" and h.get("command") not in existing_commands:
                settings["hooks"][hook_type].append(new_hook)
                break

# Write back
with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)

print("  ✓ Merged hooks into settings.json")
PYTHON_SCRIPT

else
  echo "  Creating new settings.json with hooks..."
  cp "$HOOKS_TEMPLATE" "$SETTINGS_FILE"
  echo "  ✓ Created settings.json with hooks"
fi

echo ""
echo "========================================"
echo "  Installation complete! (v${VERSION})"
echo "========================================"
echo ""
echo "Enforced workflow now active with:"
echo "  • MCP server: Structured state & config tools"
echo "  • PreToolUse hook: Validates agent transitions"
echo "  • Stop hook: Ensures Technical Writer runs"
echo ""
echo "MCP Tools available:"
echo "  Core:"
echo "    workflow_initialize       - Create new task"
echo "    workflow_transition       - Execute phase transition"
echo "    workflow_get_state        - Read current state"
echo ""
echo "  Memory Preservation:"
echo "    workflow_save_discovery   - Save learnings to memory"
echo "    workflow_get_discoveries  - Retrieve saved learnings"
echo "    workflow_flush_context    - Get all discoveries before compaction"
echo ""
echo "  Context Management:"
echo "    workflow_get_context_usage   - Check context pressure"
echo "    workflow_prune_old_outputs   - Prune large files"
echo ""
echo "  Cross-Task Memory:"
echo "    workflow_search_memories  - Search across task memories"
echo "    workflow_link_tasks       - Link related tasks"
echo ""
echo "  Model Resilience:"
echo "    workflow_get_available_model - Get model with failover"
echo "    workflow_record_model_error  - Track API errors"
echo ""
echo "Quick start:"
echo "  /crew \"Your task description\""
echo ""
echo "Loop mode (autonomous):"
echo "  /crew --loop-mode --verify tests \"Fix failing tests\""
echo ""
echo "Verify MCP server:"
echo "  claude mcp list"
echo ""
echo "Disable enforcement for a session:"
echo "  export CREW_SKIP_VALIDATION=1"
echo ""
echo "See README.md for full documentation."
echo ""
