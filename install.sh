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

# Copy commands
echo "Installing commands..."
cp "$SCRIPT_DIR/commands/"*.md "$CLAUDE_DIR/commands/"
echo "  ✓ workflow.md"
echo "  ✓ workflow-config.md"
echo "  ✓ workflow-status.md"
echo "  ✓ workflow-resume.md"

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
echo "  /workflow \"Your task description\""
echo ""
echo "Loop mode (autonomous):"
echo "  /workflow --loop-mode --verify tests \"Fix failing tests\""
echo ""
echo "See README.md for full documentation."
echo ""
