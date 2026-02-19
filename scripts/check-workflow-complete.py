#!/usr/bin/env python3
"""
Stop Hook: Check Workflow Completion (Session-Isolated)

This hook runs when Claude is about to stop and ensures the workflow has
completed all required phases.

Session isolation strategy:
1. Read .tasks/.active_task — if it points to a valid task, use that
2. Try worktree detection (match cwd to worktree paths) — use matched task
3. Otherwise: no crew workflow in this session → allow exit (exit 0)

Stale tasks from previous sessions never block unrelated sessions.

Usage in .claude/settings.json:
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "python scripts/check-workflow-complete.py"
      }]
    }]
  }
}
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from workflow_state import WorkflowState, _resolve_tasks_dir, _detect_worktree_task_id


def check_env_skip():
    """Check if workflow validation should be skipped."""
    return os.environ.get("CREW_SKIP_VALIDATION") == "1"


def _find_session_task():
    """Find the task for THIS session only.

    1. .tasks/.active_task file (written by crew_orchestrator on init/resume)
    2. Worktree detection (match cwd to worktree paths)
    3. None — no crew workflow in this session
    """
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

    # 3. No crew workflow in this session
    return None


def main():
    if check_env_skip():
        sys.exit(0)

    task_dir = _find_session_task()
    if not task_dir:
        # No crew workflow in this session — allow exit
        sys.exit(0)

    state = WorkflowState(task_dir)

    if state.phase is None:
        sys.exit(0)

    # Allow exit if a worktree was just created — work continues in the other terminal
    worktree = state._state.get("worktree")
    if worktree and worktree.get("status") == "active":
        sys.exit(0)

    is_complete, missing_phase = state.is_complete()

    if is_complete:
        sys.exit(0)

    phase_names = {
        "architect": "Architect",
        "developer": "Developer",
        "reviewer": "Reviewer",
        "skeptic": "Skeptic",
        "implementer": "Implementer",
        "feedback": "Feedback",
        "technical_writer": "Technical Writer",
        "technical-writer": "Technical Writer",
    }

    missing_name = phase_names.get(missing_phase, missing_phase)
    completed_names = [phase_names.get(p, p) for p in state.phases_completed]

    response = {
        "decision": "block",
        "reason": (
            f"Workflow incomplete: {missing_name} has not run yet. "
            f"Completed phases: {', '.join(completed_names) if completed_names else 'none'}. "
            f"Current phase: {phase_names.get(state.phase, state.phase)}. "
            f"Please complete the workflow before stopping."
        )
    }

    print(json.dumps(response))
    sys.exit(2)


if __name__ == "__main__":
    main()
