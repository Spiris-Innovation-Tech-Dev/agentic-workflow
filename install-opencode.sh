#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION=$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo "unknown")

echo "========================================"
echo "  Agentic Workflow — OpenCode Installer v${VERSION}"
echo "========================================"
echo ""

# Check prerequisites
echo "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    echo "  ✗ Python 3 not found. Please install python3 and re-run."
    exit 1
fi
echo "  ✓ Python 3 found: $(python3 --version)"

if ! command -v opencode &> /dev/null; then
    echo "  ⚠ OpenCode CLI not found in PATH"
    echo "    Install: npm install -g opencode (or see https://opencode.ai)"
    echo "    Continuing anyway — you can install OpenCode later."
else
    echo "  ✓ OpenCode CLI found"
fi
echo ""

# Determine config directory
# OpenCode uses ~/.config/opencode/ globally and .opencode/ per-project
OPENCODE_GLOBAL="$HOME/.config/opencode"

# Build agents to home directory (creates ~/.config/opencode/agents/)
echo "Installing agents (global)..."
python3 "$SCRIPT_DIR/scripts/build-agents.py" opencode --output "$HOME" || {
    echo "  ✗ Failed to build agents"
    exit 1
}

# Also build agents to project-local .opencode/
echo ""
echo "Installing agents (project)..."
python3 "$SCRIPT_DIR/scripts/build-agents.py" opencode --output "$SCRIPT_DIR" || {
    echo "  ⚠ Failed to build project-local agents (non-fatal)"
}

# Copy workflow config to OpenCode global config dir
echo ""
echo "Installing config..."
mkdir -p "$OPENCODE_GLOBAL"
if [ -f "$OPENCODE_GLOBAL/workflow-config.yaml" ]; then
    echo "  ⚠ Existing config found, creating backup..."
    cp "$OPENCODE_GLOBAL/workflow-config.yaml" "$OPENCODE_GLOBAL/workflow-config.yaml.backup.$(date +%Y%m%d%H%M%S)"
fi
cp "$SCRIPT_DIR/config/workflow-config.yaml" "$OPENCODE_GLOBAL/"
echo "  ✓ workflow-config.yaml → $OPENCODE_GLOBAL/"

# Also copy to .opencode/ (project-level fallback for config cascade)
mkdir -p "$SCRIPT_DIR/.opencode"
cp "$SCRIPT_DIR/config/workflow-config.yaml" "$SCRIPT_DIR/.opencode/"
echo "  ✓ workflow-config.yaml → .opencode/"

# Install MCP server
echo ""
echo "Installing MCP server..."
MCP_SERVER_DIR="$SCRIPT_DIR/mcp/agentic-workflow-server"

if [ -d "$MCP_SERVER_DIR" ]; then
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
        echo "  Installing Python package..."
        $PIP_CMD install -q -e "$MCP_SERVER_DIR" 2>/dev/null || {
            echo "  ⚠ Failed to install MCP server package"
            echo "    Try manually: $PIP_CMD install -e $MCP_SERVER_DIR"
        }
    fi
else
    echo "  ⚠ MCP server directory not found: $MCP_SERVER_DIR"
fi

# Register MCP server in global config (~/.config/opencode/opencode.json)
echo ""
echo "Registering MCP server..."

python3 << 'PYTHON_SCRIPT'
import json, os

config_path = os.path.expanduser("~/.config/opencode/opencode.json")
os.makedirs(os.path.dirname(config_path), exist_ok=True)

config = {}
if os.path.isfile(config_path):
    try:
        with open(config_path) as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError):
        pass

mcp = config.setdefault("mcp", {})
mcp["agentic-workflow"] = {
    "type": "local",
    "command": ["python3", "-m", "agentic_workflow_server.server"],
    "enabled": True
}

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print(f"  ✓ MCP server registered in {config_path}")
PYTHON_SCRIPT

echo ""
echo "========================================"
echo "  Installation complete! (v${VERSION})"
echo "========================================"
echo ""
echo "Quick start:"
echo "  opencode"
echo "  /crew \"Your task description\""
echo ""
echo "Or use the @crew agent for orchestrated workflows."
echo ""
echo "Verify MCP server:"
echo "  opencode mcp list"
echo ""
echo "See README.md for full documentation."
echo ""
