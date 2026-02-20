#!/bin/bash
set -e

COPILOT_DIR="$HOME/.copilot"

echo "========================================"
echo "  Agentic Workflow Copilot Uninstaller"
echo "========================================"
echo ""

# Remove global agents (~/.copilot/agents/)
echo "Removing global agents..."
removed=0
for f in "$COPILOT_DIR/agents/crew-"*.agent.md "$COPILOT_DIR/agents/crew.agent.md"; do
  [ -f "$f" ] || continue
  rm -f "$f"
  echo "  + Removed $f"
  removed=$((removed + 1))
done

if [ "$removed" -eq 0 ]; then
  echo "  No global agents found to remove"
fi

# Remove project-level agents (.github/agents/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo ""
echo "Removing project agents..."
removed=0
for f in "$SCRIPT_DIR/.github/agents/crew-"*.agent.md "$SCRIPT_DIR/.github/agents/crew.agent.md"; do
  [ -f "$f" ] || continue
  rm -f "$f"
  echo "  + Removed $f"
  removed=$((removed + 1))
done

if [ "$removed" -eq 0 ]; then
  echo "  No project agents found to remove"
fi

# Remove config
echo ""
echo "Removing config..."
if [ -f "$COPILOT_DIR/workflow-config.yaml" ]; then
  rm -f "$COPILOT_DIR/workflow-config.yaml"
  echo "  + Removed $COPILOT_DIR/workflow-config.yaml"
else
  echo "  Config file not found"
fi

# Remove MCP server from config (~/.copilot/mcp-config.json)
echo ""
echo "Removing MCP server registration..."
if [ -f "$COPILOT_DIR/mcp-config.json" ]; then
  python3 << 'PYTHON_SCRIPT'
import json, os

config_path = os.path.expanduser("~/.copilot/mcp-config.json")

with open(config_path, 'r') as f:
    config = json.load(f)

changed = False

if "mcpServers" in config and "agentic-workflow" in config["mcpServers"]:
    del config["mcpServers"]["agentic-workflow"]
    changed = True
    print("  + Removed agentic-workflow from MCP config")
else:
    print("  No agentic-workflow MCP server found")

if changed:
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
        f.write('\n')
PYTHON_SCRIPT
else
  echo "  No mcp-config.json found"
fi

# Uninstall Python package
echo ""
echo "Uninstalling Python package..."
pip3 uninstall -y agentic-workflow-server 2>/dev/null && {
  echo "  + Python package uninstalled"
} || {
  echo "  Package not found or already uninstalled"
}

echo ""
echo "========================================"
echo "  Uninstallation Complete!"
echo "========================================"
echo ""
echo "Note: Preserved:"
echo "  * .tasks/ (workflow state)"
echo ""
echo "To reinstall, run: ./install-copilot.sh"
echo ""
