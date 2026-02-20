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
echo "  ✓ crew-checkpoint.md"
echo "  ✓ crew-cost-report.md"

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
echo "  ✓ check-bash-safety.py (Bash safety hook)"
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

# Copy worktree permissions template
mkdir -p "$CLAUDE_DIR/config"
cp "$SCRIPT_DIR/config/worktree-permissions.json" "$CLAUDE_DIR/config/"
echo "  ✓ worktree-permissions.json"

# Add default worktree base to additionalDirectories for global access
echo ""
echo "Configuring worktree permissions..."
python3 -c "
import json, os
settings_file = os.path.expanduser('~/.claude/settings.local.json')
d = json.load(open(settings_file)) if os.path.isfile(settings_file) else {}
dirs = d.setdefault('additionalDirectories', [])
repo = os.path.dirname(os.path.abspath('$SCRIPT_DIR'))
wt_base = os.path.normpath(os.path.join(repo, '..', os.path.basename(repo) + '-worktrees'))
if wt_base not in dirs:
    dirs.append(wt_base)
    with open(settings_file, 'w') as f:
        json.dump(d, f, indent=2)
        f.write('\n')
    print('  Added worktree base to additionalDirectories: ' + wt_base)
else:
    print('  Worktree base already in additionalDirectories')
" 2>/dev/null && echo "  ✓ Claude settings updated" || echo "  ⚠ Could not update Claude settings (non-fatal)"

# Add worktree base to Gemini trustedFolders (if ~/.gemini/ exists)
if [ -d "$HOME/.gemini" ]; then
  python3 -c "
import json, os
trust_file = os.path.expanduser('~/.gemini/trustedFolders.json')
d = {}
if os.path.isfile(trust_file):
    with open(trust_file) as f:
        d = json.load(f)
repo = os.path.dirname(os.path.abspath('$SCRIPT_DIR'))
wt_base = os.path.normpath(os.path.join(repo, '..', os.path.basename(repo) + '-worktrees'))
if wt_base not in d:
    d[wt_base] = 'TRUST_FOLDER'
    with open(trust_file, 'w') as f:
        json.dump(d, f, indent=2)
        f.write('\n')
    print('  Added worktree base to Gemini trustedFolders: ' + wt_base)
else:
    print('  Worktree base already in Gemini trustedFolders')
" 2>/dev/null && echo "  ✓ Gemini settings updated" || echo "  ⚠ Could not update Gemini settings (non-fatal)"
fi

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
    MCP_INSTALL_OK=false
    $PIP_CMD install -q -e "$MCP_SERVER_DIR" 2>/dev/null && MCP_INSTALL_OK=true || {
      echo "  ⚠ Failed to install MCP server package"
      echo "    Try manually: $PIP_CMD install -e $MCP_SERVER_DIR"
    }

    # Register MCP server with Claude only if package installed successfully
    if [ "$MCP_INSTALL_OK" != "true" ]; then
      echo "  ⚠ Skipping MCP registration (package not installed)"
    elif command -v claude &> /dev/null; then
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
            },
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 ~/.claude/scripts/check-bash-safety.py"
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

# Install Windows Terminal color schemes (WSL only)
echo ""
echo "Installing terminal color schemes..."
if grep -qi microsoft /proc/version 2>/dev/null; then
  # Running in WSL — look for Windows Terminal settings.json
  WT_SETTINGS=""
  for CANDIDATE in \
    "/mnt/c/Users/$(cmd.exe /C 'echo %USERNAME%' 2>/dev/null | tr -d '\r')/AppData/Local/Packages/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json" \
    "/mnt/c/Users/$(cmd.exe /C 'echo %USERNAME%' 2>/dev/null | tr -d '\r')/AppData/Local/Packages/Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe/LocalState/settings.json" \
    "/mnt/c/Users/$(whoami)/AppData/Local/Packages/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json"; do
    if [ -f "$CANDIDATE" ]; then
      WT_SETTINGS="$CANDIDATE"
      break
    fi
  done

  if [ -n "$WT_SETTINGS" ]; then
    python3 << PYEOF
import json, sys, os

schemes_file = os.path.join("$SCRIPT_DIR", "config", "terminal-colorschemes.json")
wt_settings_file = """$WT_SETTINGS"""

try:
    with open(schemes_file) as f:
        crew_schemes = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"  ⚠ Could not read color schemes: {e}")
    sys.exit(0)

try:
    with open(wt_settings_file) as f:
        raw_content = f.read()
    # Strip JSON comments (// style) for parsing only
    import re
    clean_content = re.sub(r'^\s*//.*$', '', raw_content, flags=re.MULTILINE)
    settings = json.loads(clean_content)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"  ⚠ Could not read WT settings.json: {e}")
    sys.exit(0)

if "schemes" not in settings:
    settings["schemes"] = []

existing_names = {s.get("name") for s in settings["schemes"]}
new_schemes = [s for s in crew_schemes if s["name"] not in existing_names]

if new_schemes:
    # Inject schemes into the raw file content to preserve comments.
    # Find the "schemes" array and append before its closing bracket.
    schemes_json = ",\n".join(json.dumps(s, indent=4) for s in new_schemes)
    # Try to find existing schemes array closing bracket
    schemes_match = re.search(r'("schemes"\s*:\s*\[)(.*?)(\])', raw_content, re.DOTALL)
    if schemes_match:
        inner = schemes_match.group(2).rstrip()
        separator = ",\n        " if inner.strip() else "\n        "
        new_content = (
            raw_content[:schemes_match.end(2)]
            + separator + schemes_json + "\n    "
            + raw_content[schemes_match.start(3):]
        )
    else:
        # No schemes array found — fall back to full rewrite (loses comments)
        settings["schemes"].extend(new_schemes)
        new_content = json.dumps(settings, indent=4) + "\n"
    # Backup before writing
    import shutil
    shutil.copy2(wt_settings_file, wt_settings_file + ".bak")
    with open(wt_settings_file, "w") as f:
        f.write(new_content)
    print(f"  ✓ Added {len(new_schemes)} Crew color schemes to Windows Terminal")
    print(f"  ✓ Backup saved to settings.json.bak")
else:
    print("  ✓ Crew color schemes already present in Windows Terminal")
PYEOF
  else
    echo "  ⚠ Windows Terminal settings.json not found, skipping"
  fi
else
  echo "  - Not running in WSL, skipping Windows Terminal scheme injection"
fi

echo ""
echo "========================================"
echo "  Installation complete! (v${VERSION})"
echo "========================================"
echo ""
echo "Enforced workflow now active with:"
echo "  • MCP server: Structured state & config tools"
echo "  • PreToolUse hook (Task): Validates agent transitions"
echo "  • PreToolUse hook (Bash): Warns about unsafe git commands"
echo "  • Stop hook: Ensures workflow completes + session-close reminders"
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
