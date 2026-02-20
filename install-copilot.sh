#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION=$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo "unknown")

echo "========================================"
echo "  Agentic Workflow Copilot Installer v${VERSION}"
echo "========================================"
echo ""

# Check prerequisites
echo "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    echo "  X Python 3 not found"
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
            echo "  X Could not detect package manager. Please install python3 manually."
            exit 1
        fi
    else
        echo "  X Python 3 is required. Please install it and re-run."
        exit 1
    fi
fi
echo "  + Python 3 found: $(python3 --version)"

if command -v copilot &> /dev/null; then
    echo "  + Copilot CLI found"
else
    echo "  ! Copilot CLI not found"
    echo "    Install with: gh extension install github/gh-copilot"
    echo "    See: https://docs.github.com/en/copilot/github-copilot-in-the-cli"
fi
echo ""

# Build agents to user-level (~/.copilot/agents/)
echo "Installing agents (global)..."
python3 "$SCRIPT_DIR/scripts/build-agents.py" copilot --output "$HOME" || {
    echo "  X Failed to build global agents"
    exit 1
}

# Also build agents to project-level (.github/agents/)
echo ""
echo "Installing agents (project)..."
python3 "$SCRIPT_DIR/scripts/build-agents.py" copilot --output "$SCRIPT_DIR" || {
    echo "  ! Failed to build project-local agents (non-fatal)"
}

# Copy config
COPILOT_DIR="$HOME/.copilot"
echo ""
echo "Installing config..."
mkdir -p "$COPILOT_DIR"
if [ -f "$COPILOT_DIR/workflow-config.yaml" ]; then
    echo "  ! Existing config found, creating backup..."
    cp "$COPILOT_DIR/workflow-config.yaml" "$COPILOT_DIR/workflow-config.yaml.backup.$(date +%Y%m%d%H%M%S)"
fi
cp "$SCRIPT_DIR/config/workflow-config.yaml" "$COPILOT_DIR/"
echo "  + workflow-config.yaml"

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
        echo "  ! pip not found, skipping MCP server installation"
        echo "    Install with: pip install -e $MCP_SERVER_DIR"
        PIP_CMD=""
    fi

    if [ -n "$PIP_CMD" ]; then
        echo "  Installing Python package..."
        MCP_INSTALL_OK=false
        $PIP_CMD install -q -e "$MCP_SERVER_DIR" 2>/dev/null && MCP_INSTALL_OK=true || {
            echo "  ! Failed to install MCP server package"
            echo "    Try manually: $PIP_CMD install -e $MCP_SERVER_DIR"
        }
        if [ "$MCP_INSTALL_OK" = "true" ]; then
            echo "  + MCP server package installed"
        fi
    fi
else
    echo "  ! MCP server directory not found: $MCP_SERVER_DIR"
fi

# Register MCP server in Copilot config
echo ""
echo "Registering MCP server..."

python3 << 'PYTHON_SCRIPT'
import json, os

config_path = os.path.expanduser("~/.copilot/mcp-config.json")
os.makedirs(os.path.dirname(config_path), exist_ok=True)

config = {}
if os.path.isfile(config_path):
    try:
        with open(config_path) as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError):
        pass

servers = config.setdefault("mcpServers", {})
servers["agentic-workflow"] = {
    "command": "python3",
    "args": ["-m", "agentic_workflow_server.server"],
    "env": {}
}

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print("  + MCP server registered in " + config_path)
PYTHON_SCRIPT

echo ""
echo "========================================"
echo "  Installation complete! (v${VERSION})"
echo "========================================"
echo ""
echo "Quick start:"
echo "  copilot"
echo "  > Use crew-architect to analyze adding a caching layer"
echo ""
echo "See README.md for full documentation."
echo ""
