#!/bin/bash
set -e

CLAUDE_DIR="$HOME/.claude"

echo "========================================"
echo "  Agentic Workflow Uninstaller"
echo "========================================"
echo ""

read -p "This will remove agentic-workflow files. Continue? [y/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Cancelled."
  exit 0
fi

echo ""
echo "Removing commands..."
rm -f "$CLAUDE_DIR/commands/workflow.md"
rm -f "$CLAUDE_DIR/commands/workflow-config.md"
rm -f "$CLAUDE_DIR/commands/workflow-status.md"
rm -f "$CLAUDE_DIR/commands/workflow-resume.md"
echo "  ✓ Commands removed"

echo ""
echo "Removing agents..."
rm -f "$CLAUDE_DIR/agents/architect.md"
rm -f "$CLAUDE_DIR/agents/developer.md"
rm -f "$CLAUDE_DIR/agents/reviewer.md"
rm -f "$CLAUDE_DIR/agents/skeptic.md"
rm -f "$CLAUDE_DIR/agents/implementer.md"
rm -f "$CLAUDE_DIR/agents/feedback.md"
rm -f "$CLAUDE_DIR/agents/technical-writer.md"
echo "  ✓ Agents removed"

echo ""
read -p "Remove workflow-config.yaml? [y/N] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
  rm -f "$CLAUDE_DIR/workflow-config.yaml"
  echo "  ✓ Config removed"
else
  echo "  ✓ Config kept"
fi

echo ""
echo "========================================"
echo "  Uninstallation complete!"
echo "========================================"
echo ""
echo "Note: Task files in .tasks/ directories were not removed."
echo ""
