#!/bin/bash
set -e

OPENCODE_GLOBAL="$HOME/.config/opencode"
OPENCODE_LEGACY="$HOME/.opencode"

echo "========================================"
echo "  Agentic Workflow OpenCode Uninstaller"
echo "========================================"
echo ""

# Remove agents from both global and legacy locations
echo "Removing agents..."
removed=0
for dir in "$OPENCODE_GLOBAL" "$OPENCODE_LEGACY"; do
  for f in "$dir/agents/crew-"*.md "$dir/agents/crew.md"; do
    [ -f "$f" ] || continue
    rm -f "$f"
    echo "  + Removed $f"
    removed=$((removed + 1))
  done
done

if [ "$removed" -eq 0 ]; then
  echo "  No agents found to remove"
fi

# Remove commands from both global and legacy locations
echo ""
echo "Removing commands..."
removed=0
for dir in "$OPENCODE_GLOBAL" "$OPENCODE_LEGACY"; do
  for f in "$dir/commands/crew-"*.md "$dir/commands/crew.md" "$dir/commands/crew-config.md" "$dir/commands/crew-resume.md"; do
    [ -f "$f" ] || continue
    rm -f "$f"
    echo "  + Removed $f"
    removed=$((removed + 1))
  done
done

if [ "$removed" -eq 0 ]; then
  echo "  No commands found to remove"
fi

# Remove config from both locations
echo ""
echo "Removing config..."
removed=0
for dir in "$OPENCODE_GLOBAL" "$OPENCODE_LEGACY"; do
  if [ -f "$dir/workflow-config.yaml" ]; then
    rm -f "$dir/workflow-config.yaml"
    echo "  + Removed $dir/workflow-config.yaml"
    removed=$((removed + 1))
  fi
done

if [ "$removed" -eq 0 ]; then
  echo "  Config file not found"
fi

# Remove MCP server from global config (~/.config/opencode/opencode.json)
echo ""
echo "Removing MCP server registration..."
if [ -f "$OPENCODE_GLOBAL/opencode.json" ]; then
  python3 << 'PYTHON_SCRIPT'
import json, os

config_path = os.path.expanduser("~/.config/opencode/opencode.json")

with open(config_path, 'r') as f:
    config = json.load(f)

changed = False

if "mcp" in config and "agentic-workflow" in config["mcp"]:
    del config["mcp"]["agentic-workflow"]
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
  echo "  No global opencode.json found"
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
echo "To reinstall, run: ./install-opencode.sh"
echo ""
