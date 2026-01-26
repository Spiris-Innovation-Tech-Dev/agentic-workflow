#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

echo "========================================"
echo "  Agentic Workflow Installer"
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
echo "  ✓ crew-status.md"
echo "  ✓ crew-resume.md"

# Copy agents
echo ""
echo "Installing agents..."
cp "$SCRIPT_DIR/agents/"*.md "$CLAUDE_DIR/agents/"
echo "  ✓ architect.md"
echo "  ✓ developer.md"
echo "  ✓ reviewer.md"
echo "  ✓ skeptic.md"
echo "  ✓ implementer.md"
echo "  ✓ feedback.md"
echo "  ✓ technical-writer.md"

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
echo "  Installation complete!"
echo "========================================"
echo ""
echo "Enforced workflow now active with:"
echo "  • PreToolUse hook: Validates agent transitions"
echo "  • Stop hook: Ensures Technical Writer runs"
echo ""
echo "Quick start:"
echo "  /crew \"Your task description\""
echo ""
echo "Loop mode (autonomous):"
echo "  /crew --loop-mode --verify tests \"Fix failing tests\""
echo ""
echo "Disable enforcement for a session:"
echo "  export CREW_SKIP_VALIDATION=1"
echo ""
echo "See README.md for full documentation."
echo ""
