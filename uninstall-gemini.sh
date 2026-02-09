#!/bin/bash
set -e

GEMINI_DIR="$HOME/.gemini"

echo "========================================"
echo "  Agentic Workflow Gemini Uninstaller"
echo "========================================"
echo ""

# Remove agents
echo "Removing agents..."
removed=0
for f in "$GEMINI_DIR/agents/crew-"*.md; do
  [ -f "$f" ] || continue
  rm -f "$f"
  echo "  ✓ Removed $(basename "$f")"
  removed=$((removed + 1))
done

if [ "$removed" -eq 0 ]; then
  echo "  No agents found to remove"
fi

# Remove config
echo ""
echo "Removing config..."
if [ -f "$GEMINI_DIR/workflow-config.yaml" ]; then
  rm -f "$GEMINI_DIR/workflow-config.yaml"
  echo "  ✓ Removed workflow-config.yaml"
else
  echo "  Config file not found"
fi

# Remove MCP server from settings.json
echo ""
echo "Removing MCP server registration..."
if [ -f "$GEMINI_DIR/settings.json" ]; then
  python3 << 'PYTHON_SCRIPT'
import json
import os

settings_file = os.path.expanduser("~/.gemini/settings.json")

with open(settings_file, 'r') as f:
    settings = json.load(f)

changed = False

if "mcpServers" in settings and "agentic-workflow" in settings["mcpServers"]:
    del settings["mcpServers"]["agentic-workflow"]
    changed = True
    print("  ✓ Removed agentic-workflow from MCP servers")
else:
    print("  No agentic-workflow MCP server found")

with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')
PYTHON_SCRIPT
else
  echo "  Settings file not found"
fi

# Uninstall Python package
echo ""
echo "Uninstalling Python package..."
pip3 uninstall -y agentic-workflow-server 2>/dev/null && {
  echo "  ✓ Python package uninstalled"
} || {
  echo "  Package not found or already uninstalled"
}

echo ""
echo "========================================"
echo "  Uninstallation Complete!"
echo "========================================"
echo ""
echo "Note: Preserved:"
echo "  • ~/.gemini/settings.json (experimental.enableAgents still enabled)"
echo "  • .tasks/ (workflow state)"
echo ""
echo "To reinstall, run: ./install-gemini.sh"
echo ""
