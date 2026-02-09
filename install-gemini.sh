#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GEMINI_DIR="$HOME/.gemini"
VERSION=$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo "unknown")

echo "========================================"
echo "  Agentic Workflow Gemini Installer v${VERSION}"
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

if command -v gemini &> /dev/null; then
    echo "  ✓ Gemini CLI found"
else
    echo "  ⚠ Gemini CLI not found"
    echo "    Install with: npm install -g @anthropic-ai/gemini-cli"
    echo "    See: https://github.com/google-gemini/gemini-cli"
fi
echo ""

# Build agents using multi-platform build script
echo "Installing agents..."
python3 "$SCRIPT_DIR/scripts/build-agents.py" gemini --output "$HOME" || {
  echo "  ✗ Failed to build agents"
  exit 1
}

# Copy config (backup existing if present)
echo ""
echo "Installing config..."
mkdir -p "$GEMINI_DIR"
if [ -f "$GEMINI_DIR/workflow-config.yaml" ]; then
  echo "  ⚠ Existing config found, creating backup..."
  cp "$GEMINI_DIR/workflow-config.yaml" "$GEMINI_DIR/workflow-config.yaml.backup.$(date +%Y%m%d%H%M%S)"
fi
cp "$SCRIPT_DIR/config/workflow-config.yaml" "$GEMINI_DIR/"
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
    echo "  Installing Python package..."
    $PIP_CMD install -q -e "$MCP_SERVER_DIR" 2>/dev/null || {
      echo "  ⚠ Failed to install MCP server package"
      echo "    Try manually: $PIP_CMD install -e $MCP_SERVER_DIR"
    }
    echo "  ✓ MCP server package installed"
  fi
else
  echo "  ⚠ MCP server directory not found: $MCP_SERVER_DIR"
fi

# Configure settings.json with MCP server and experimental agents
echo ""
echo "Configuring settings.json..."
SETTINGS_FILE="$GEMINI_DIR/settings.json"

python3 << PYTHON_SCRIPT
import json
import os

settings_file = os.path.expanduser("~/.gemini/settings.json")

# Read existing settings or start fresh
if os.path.exists(settings_file):
    with open(settings_file, 'r') as f:
        try:
            settings = json.load(f)
        except json.JSONDecodeError:
            settings = {}
else:
    settings = {}

# Enable experimental agents
if "experimental" not in settings:
    settings["experimental"] = {}
settings["experimental"]["enableAgents"] = True

# Add MCP server
if "mcpServers" not in settings:
    settings["mcpServers"] = {}

settings["mcpServers"]["agentic-workflow"] = {
    "command": "python3",
    "args": ["-m", "agentic_workflow_server.server"]
}

# Write back
with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')

print("  ✓ Experimental agents enabled")
print("  ✓ MCP server registered: agentic-workflow")
PYTHON_SCRIPT

echo ""
echo "========================================"
echo "  Installation complete! (v${VERSION})"
echo "========================================"
echo ""
echo "Installed components:"
echo "  • Agents:   $GEMINI_DIR/agents/crew-*.md"
echo "  • Config:   $GEMINI_DIR/workflow-config.yaml"
echo "  • Settings: $GEMINI_DIR/settings.json"
echo "  • MCP:      agentic-workflow (Python package)"
echo ""
echo "Note: Gemini CLI sub-agents are experimental."
echo "  The installer enabled them in settings.json:"
echo "    \"experimental\": { \"enableAgents\": true }"
echo ""
echo "Quick start:"
echo "  gemini"
echo "  > Use crew-orchestrator to implement user authentication"
echo ""
echo "Or invoke individual agents:"
echo "  > Use crew-architect to analyze adding a caching layer"
echo "  > Use crew-skeptic to find edge cases in this design"
echo ""
echo "MCP tools available in Gemini CLI:"
echo "  agentic-workflow__workflow_initialize"
echo "  agentic-workflow__workflow_transition"
echo "  agentic-workflow__workflow_get_state"
echo "  agentic-workflow__workflow_save_discovery"
echo "  (52 tools total — use /mcp to list)"
echo ""
echo "See README.md for full documentation."
echo ""
