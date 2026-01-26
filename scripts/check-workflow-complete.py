#!/usr/bin/env python3
"""
Stop Hook: Check Workflow Completion

This hook runs when Claude is about to stop and ensures the workflow has
completed all required phases, especially Technical Writer.

The hook:
- Checks for an active workflow task
- Verifies all required phases are complete
- Blocks stopping if Technical Writer hasn't run (exit 2)
- Allows stopping if workflow is complete or no active workflow

Required phases: architect, developer, reviewer, implementer, technical_writer

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
from workflow_state import WorkflowState, find_active_task, REQUIRED_PHASES


def check_env_skip():
    """Check if workflow validation should be skipped."""
    return os.environ.get("CREW_SKIP_VALIDATION") == "1"


def main():
    if check_env_skip():
        sys.exit(0)

    task_dir = find_active_task()
    if not task_dir:
        sys.exit(0)

    state = WorkflowState(task_dir)

    if state.phase is None:
        sys.exit(0)

    is_complete, missing_phase = state.is_complete()

    if is_complete:
        sys.exit(0)

    phase_names = {
        "architect": "Architect",
        "developer": "Developer",
        "reviewer": "Reviewer",
        "implementer": "Implementer",
        "technical_writer": "Technical Writer"
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
