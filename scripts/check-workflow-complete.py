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


def _check_session_close_protocol(task_dir: str):
    """Check session-close protocol and emit reminders (non-blocking).

    This runs when the workflow IS complete but we want to remind about:
    - Uncommitted changes (git status)
    - Beads sync (bd sync --from-main)
    """
    import subprocess

    reminders = []

    # Check for uncommitted changes
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            changed_count = len(result.stdout.strip().splitlines())
            reminders.append(
                f"{changed_count} uncommitted change(s) detected — "
                "consider: git add <files> && git commit"
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Check if beads is available and has open issues
    try:
        result = subprocess.run(
            ["bd", "list", "--status=in_progress"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
            if lines:
                reminders.append(
                    "Open in-progress beads issues — "
                    "consider: bd close <id> && bd sync --from-main"
                )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    if reminders:
        response = {
            "decision": "warn",
            "reason": (
                "Session-close reminders:\n"
                + "\n".join(f"  - {r}" for r in reminders)
            )
        }
        print(json.dumps(response))


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

    # Allow exit if THIS task's worktree is active AND we're NOT inside it.
    # The orchestrator session (main repo) can exit after creating a worktree
    # because work continues in the worktree terminal.
    worktree = state._state.get("worktree")
    if worktree and worktree.get("status") == "active":
        wt_path = worktree.get("path", "")
        cwd = str(Path.cwd().resolve())
        # Only allow exit from the main repo session, not the worktree session
        if wt_path and not cwd.startswith(str(Path(wt_path).resolve())):
            sys.exit(0)

    is_complete, missing_phase = state.is_complete()

    if is_complete:
        # Workflow is done — check session-close protocol reminders
        _check_session_close_protocol(task_dir)
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
