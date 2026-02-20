#!/usr/bin/env python3
"""
PreToolUse Hook: Bash Command Safety Gate (Session-Isolated)

This hook runs before Bash tool calls during crew workflows to enforce
safe practices:

1. Warns about `git commit` if the workflow hasn't reached implementation
2. Warns about `git push` during active workflows (work should be merged locally)
3. Warns about destructive git commands (reset --hard, clean -fd, checkout .)

Session isolation: only activates when a crew workflow is active in this
session (via .active_task file or worktree detection). Non-crew sessions
are never affected.

Usage in .claude/settings.json:
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.claude/scripts/check-bash-safety.py"
      }]
    }]
  }
}
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from workflow_state import WorkflowState, _resolve_tasks_dir, _detect_worktree_task_id


# Destructive commands that should always warn during crew workflows
DESTRUCTIVE_PATTERNS = [
    (r"git\s+reset\s+--hard", "git reset --hard discards all uncommitted changes"),
    (r"git\s+clean\s+-[fd]", "git clean removes untracked files permanently"),
    (r"git\s+checkout\s+\.", "git checkout . discards all working tree changes"),
    (r"git\s+restore\s+\.", "git restore . discards all working tree changes"),
    (r"git\s+stash\s+drop", "git stash drop permanently removes stashed changes"),
    (r"git\s+push\s+--force", "force push rewrites remote history"),
    (r"git\s+branch\s+-D", "git branch -D force-deletes a branch"),
]


def _find_session_task():
    """Find the task for THIS session only."""
    tasks_dir = _resolve_tasks_dir()

    # 1. Check .active_task file
    active_file = tasks_dir / ".active_task"
    if active_file.exists():
        try:
            task_id = active_file.read_text().strip()
            if task_id:
                task_dir = tasks_dir / task_id
                if task_dir.exists() and (task_dir / "state.json").exists():
                    return str(task_dir)
        except OSError:
            pass

    # 2. Worktree detection
    wt_task_id = _detect_worktree_task_id(tasks_dir)
    if wt_task_id:
        task_dir = tasks_dir / wt_task_id
        if task_dir.exists():
            return str(task_dir)

    return None


def check_command(command: str, state: WorkflowState | None) -> tuple[bool, str]:
    """Check a bash command for safety issues.

    Returns (should_warn, reason) — warnings don't block, they inform.
    """
    cmd_lower = command.strip().lower()

    # Check destructive patterns (always warn in crew workflows)
    for pattern, reason in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, cmd_lower):
            return True, f"Destructive command detected: {reason}"

    # Check git push during active workflow
    if re.search(r"git\s+push\b", cmd_lower) and state:
        phase = state.phase
        if phase and phase not in ("complete", "done"):
            return True, (
                "git push during active workflow — work on ephemeral branches "
                "should be merged to main locally, not pushed to remote"
            )

    # Check git commit before implementation phase
    if re.search(r"git\s+commit\b", cmd_lower) and state:
        phase = state.phase
        phases_done = state.phases_completed or []
        # Warn if we haven't reached implementation yet
        if phase and "implementer" not in phases_done and phase != "implementer":
            return True, (
                f"git commit during planning phase ({phase}) — "
                "typically commits happen after implementation"
            )

    return False, ""


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command:
        sys.exit(0)

    # Only activate during crew workflows
    task_dir = _find_session_task()
    if not task_dir:
        sys.exit(0)

    state = WorkflowState(task_dir)

    should_warn, reason = check_command(command, state)

    if should_warn:
        # Emit a warning (not a block) — let the user decide
        response = {
            "decision": "warn",
            "reason": f"Safety check: {reason}"
        }
        print(json.dumps(response))
        # Exit 0 = allow, but the warning is displayed
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
