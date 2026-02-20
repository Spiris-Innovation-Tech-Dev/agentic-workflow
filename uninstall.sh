#!/bin/bash
set -e

CLAUDE_DIR="$HOME/.claude"

echo "========================================"
echo "  Agentic Workflow Uninstaller"
echo "========================================"
echo ""

read -p "This will remove agentic-workflow files from ~/.claude. Continue? [y/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Cancelled."
  exit 0
fi

echo ""
echo "Removing commands..."
rm -f "$CLAUDE_DIR/commands/crew.md"
rm -f "$CLAUDE_DIR/commands/crew-config.md"
rm -f "$CLAUDE_DIR/commands/crew-resume.md"
rm -f "$CLAUDE_DIR/commands/crew-worktree.md"
rm -f "$CLAUDE_DIR/commands/crew-status.md"
rm -f "$CLAUDE_DIR/commands/crew-checkpoint.md"
rm -f "$CLAUDE_DIR/commands/crew-cost-report.md"
# Legacy names (pre-rename)
rm -f "$CLAUDE_DIR/commands/workflow.md"
rm -f "$CLAUDE_DIR/commands/workflow-config.md"
rm -f "$CLAUDE_DIR/commands/workflow-status.md"
rm -f "$CLAUDE_DIR/commands/workflow-resume.md"
echo "  + Commands removed"

echo ""
echo "Removing agents..."
rm -f "$CLAUDE_DIR/agents/architect.md"
rm -f "$CLAUDE_DIR/agents/developer.md"
rm -f "$CLAUDE_DIR/agents/reviewer.md"
rm -f "$CLAUDE_DIR/agents/skeptic.md"
rm -f "$CLAUDE_DIR/agents/implementer.md"
rm -f "$CLAUDE_DIR/agents/feedback.md"
rm -f "$CLAUDE_DIR/agents/technical-writer.md"
rm -f "$CLAUDE_DIR/agents/orchestrator.md"
rm -f "$CLAUDE_DIR/agents/security-auditor.md"
rm -f "$CLAUDE_DIR/agents/performance-analyst.md"
rm -f "$CLAUDE_DIR/agents/api-guardian.md"
rm -f "$CLAUDE_DIR/agents/accessibility-reviewer.md"
echo "  + Agents removed"

echo ""
echo "Removing enforcement scripts..."
rm -f "$CLAUDE_DIR/scripts/validate-transition.py"
rm -f "$CLAUDE_DIR/scripts/check-bash-safety.py"
rm -f "$CLAUDE_DIR/scripts/check-workflow-complete.py"
rm -f "$CLAUDE_DIR/scripts/workflow_state.py"
echo "  + Scripts removed"

echo ""
echo "Removing enforcement hooks from settings.json..."
if [ -f "$CLAUDE_DIR/settings.json" ]; then
  python3 << 'PYTHON_SCRIPT'
import json, os

settings_file = os.path.expanduser("~/.claude/settings.json")
with open(settings_file, 'r') as f:
    settings = json.load(f)

changed = False
for hook_type in ["PreToolUse", "Stop"]:
    if "hooks" in settings and hook_type in settings["hooks"]:
        original_len = len(settings["hooks"][hook_type])
        settings["hooks"][hook_type] = [
            h for h in settings["hooks"][hook_type]
            if not any(
                "validate-transition.py" in hh.get("command", "") or
                "check-bash-safety.py" in hh.get("command", "") or
                "check-workflow-complete.py" in hh.get("command", "")
                for hh in h.get("hooks", [])
                if hh.get("type") == "command"
            )
        ]
        if len(settings["hooks"][hook_type]) != original_len:
            changed = True
        if not settings["hooks"][hook_type]:
            del settings["hooks"][hook_type]

if changed:
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')
    print("  + Hooks removed from settings.json")
else:
    print("  No hooks found to remove")
PYTHON_SCRIPT
else
  echo "  No settings.json found"
fi

echo ""
echo "Removing MCP server registration..."
if command -v claude &> /dev/null; then
  claude mcp remove agentic-workflow 2>/dev/null && {
    echo "  + MCP server unregistered"
  } || {
    echo "  MCP server not found in registry"
  }
else
  echo "  Claude CLI not found, skipping MCP removal"
fi

echo ""
echo "Uninstalling Python package..."
pip3 uninstall -y agentic-workflow-server 2>/dev/null && {
  echo "  + Python package uninstalled"
} || {
  echo "  Package not found or already uninstalled"
}

echo ""
read -p "Remove workflow-config.yaml? [y/N] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
  rm -f "$CLAUDE_DIR/workflow-config.yaml"
  echo "  + Config removed"
else
  echo "  + Config kept"
fi

echo ""
echo "========================================"
echo "  Uninstallation complete!"
echo "========================================"
echo ""
echo "Note: Preserved:"
echo "  * .tasks/ directories (workflow state)"
echo "  * ~/.claude/config/ (worktree permissions template)"
echo ""
echo "To reinstall, run: ./install.sh"
echo ""
