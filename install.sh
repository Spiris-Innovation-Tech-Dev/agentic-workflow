#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

echo "========================================"
echo "  Agentic Workflow Installer"
echo "========================================"
echo ""

# Create directories if they don't exist
mkdir -p "$CLAUDE_DIR/commands"
mkdir -p "$CLAUDE_DIR/agents"

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

# Copy config (backup existing if present)
echo ""
echo "Installing config..."
if [ -f "$CLAUDE_DIR/workflow-config.yaml" ]; then
  echo "  ⚠ Existing config found, creating backup..."
  cp "$CLAUDE_DIR/workflow-config.yaml" "$CLAUDE_DIR/workflow-config.yaml.backup.$(date +%Y%m%d%H%M%S)"
fi
cp "$SCRIPT_DIR/config/workflow-config.yaml" "$CLAUDE_DIR/"
echo "  ✓ workflow-config.yaml"

echo ""
echo "========================================"
echo "  Installation complete!"
echo "========================================"
echo ""
echo "Quick start:"
echo "  /crew \"Your task description\""
echo ""
echo "Loop mode (autonomous):"
echo "  /crew --loop-mode --verify tests \"Fix failing tests\""
echo ""
echo "See README.md for full documentation."
echo ""
