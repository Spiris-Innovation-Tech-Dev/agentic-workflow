#!/usr/bin/env python3
"""
Workflow State Management Library

Manages state for the enforced multi-agent workflow. State is stored in JSON files
within each task directory (.tasks/TASK_XXX/state.json).

The workflow follows this phase order:
    architect -> developer -> reviewer -> skeptic -> implementer -> technical_writer

Usage:
    from workflow_state import WorkflowState

    state = WorkflowState(".tasks/TASK_001")
    state.transition("developer")
    state.add_review_issue({"type": "missing_test", "step": "2.3"})
    state.mark_docs_needed(["src/base/Service.ts"])
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


PHASE_ORDER = [
    "architect",
    "developer",
    "reviewer",
    "skeptic",
    "implementer",
    "technical_writer"
]

REQUIRED_PHASES = [
    "architect",
    "developer",
    "reviewer",
    "implementer",
    "technical_writer"
]


class WorkflowState:
    """Manages workflow state for a single task."""

    def __init__(self, task_dir: str):
        self.task_dir = Path(task_dir)
        self.state_file = self.task_dir / "state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Load state from JSON file or create default state."""
        if self.state_file.exists():
            with open(self.state_file, "r") as f:
                return json.load(f)
        return self._create_default_state()

    def _create_default_state(self) -> dict:
        """Create initial workflow state."""
        task_id = self.task_dir.name
        return {
            "task_id": task_id,
            "phase": None,
            "phases_completed": [],
            "review_issues": [],
            "iteration": 1,
            "docs_needed": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

    def _save_state(self) -> None:
        """Persist state to JSON file."""
        self.task_dir.mkdir(parents=True, exist_ok=True)
        self._state["updated_at"] = datetime.now().isoformat()
        with open(self.state_file, "w") as f:
            json.dump(self._state, f, indent=2)

    @property
    def phase(self) -> Optional[str]:
        """Get current phase."""
        return self._state.get("phase")

    @property
    def phases_completed(self) -> list:
        """Get list of completed phases."""
        return self._state.get("phases_completed", [])

    @property
    def iteration(self) -> int:
        """Get current iteration number."""
        return self._state.get("iteration", 1)

    @property
    def review_issues(self) -> list:
        """Get list of review issues."""
        return self._state.get("review_issues", [])

    @property
    def docs_needed(self) -> list:
        """Get list of files needing documentation."""
        return self._state.get("docs_needed", [])

    def initialize(self) -> None:
        """Initialize workflow state for new task, starting with architect."""
        self._state = self._create_default_state()
        self._state["phase"] = "architect"
        self._save_state()

    def get_next_phase(self) -> Optional[str]:
        """Get the next phase in the workflow sequence."""
        current = self.phase
        if current is None:
            return "architect"

        try:
            current_idx = PHASE_ORDER.index(current)
            if current_idx + 1 < len(PHASE_ORDER):
                return PHASE_ORDER[current_idx + 1]
        except ValueError:
            pass
        return None

    def can_transition(self, to_phase: str) -> tuple[bool, str]:
        """
        Check if transition to given phase is valid.

        Returns:
            Tuple of (can_transition, reason)
        """
        if to_phase not in PHASE_ORDER:
            return False, f"Invalid phase: {to_phase}"

        current = self.phase

        if current is None:
            if to_phase == "architect":
                return True, "Starting workflow with architect"
            return False, "Workflow must start with architect phase"

        if to_phase == current:
            return True, "Re-running current phase"

        if to_phase in self.phases_completed:
            if to_phase == "developer" and self.review_issues:
                return True, "Looping back to developer due to review issues"
            return False, f"Phase {to_phase} already completed"

        current_idx = PHASE_ORDER.index(current)
        to_idx = PHASE_ORDER.index(to_phase)

        if to_idx == current_idx + 1:
            return True, f"Valid forward transition from {current} to {to_phase}"

        if to_phase == "developer" and current in ("reviewer", "skeptic"):
            return True, f"Valid loop-back from {current} to developer"

        return False, f"Cannot skip from {current} to {to_phase}"

    def transition(self, to_phase: str) -> tuple[bool, str]:
        """
        Transition to a new phase if valid.

        Returns:
            Tuple of (success, message)
        """
        can, reason = self.can_transition(to_phase)
        if not can:
            return False, reason

        old_phase = self.phase

        if old_phase and old_phase != to_phase and old_phase not in self._state["phases_completed"]:
            self._state["phases_completed"].append(old_phase)

        if to_phase == "developer" and old_phase in ("reviewer", "skeptic"):
            self._state["iteration"] = self.iteration + 1
            self._state["review_issues"] = []

        self._state["phase"] = to_phase
        self._save_state()

        return True, f"Transitioned to {to_phase}"

    def complete_phase(self) -> None:
        """Mark current phase as complete."""
        current = self.phase
        if current and current not in self._state["phases_completed"]:
            self._state["phases_completed"].append(current)
            self._save_state()

    def add_review_issue(self, issue: dict) -> None:
        """
        Add a review issue that may require looping back.

        Args:
            issue: Dict with at least 'type' and 'description' keys
        """
        issue["added_at"] = datetime.now().isoformat()
        self._state["review_issues"].append(issue)
        self._save_state()

    def clear_review_issues(self) -> None:
        """Clear all review issues (e.g., after developer addresses them)."""
        self._state["review_issues"] = []
        self._save_state()

    def mark_docs_needed(self, files: list) -> None:
        """
        Mark files as needing documentation.

        Args:
            files: List of file paths that need documentation
        """
        existing = set(self._state.get("docs_needed", []))
        existing.update(files)
        self._state["docs_needed"] = list(existing)
        self._save_state()

    def is_complete(self) -> tuple[bool, Optional[str]]:
        """
        Check if workflow is complete (all required phases done).

        Returns:
            Tuple of (is_complete, missing_phase or None)
        """
        completed = set(self.phases_completed)
        if self.phase:
            completed.add(self.phase)

        for phase in REQUIRED_PHASES:
            if phase not in completed:
                return False, phase

        return True, None

    def get_state_summary(self) -> dict:
        """Get a summary of the current state for display."""
        complete, missing = self.is_complete()
        return {
            "task_id": self._state.get("task_id"),
            "current_phase": self.phase,
            "phases_completed": self.phases_completed,
            "iteration": self.iteration,
            "review_issues_count": len(self.review_issues),
            "docs_needed_count": len(self.docs_needed),
            "is_complete": complete,
            "missing_phase": missing
        }

    def to_json(self) -> str:
        """Serialize state to JSON string."""
        return json.dumps(self._state, indent=2)


def get_state(task_dir: str) -> dict:
    """Read current state from JSON file."""
    state = WorkflowState(task_dir)
    return state._state


def transition(task_dir: str, to_phase: str) -> tuple[bool, str]:
    """Validate and update phase."""
    state = WorkflowState(task_dir)
    return state.transition(to_phase)


def add_review_issue(task_dir: str, issue: dict) -> None:
    """Track issues for loop-back."""
    state = WorkflowState(task_dir)
    state.add_review_issue(issue)


def mark_docs_needed(task_dir: str, files: list) -> None:
    """Architect flags undocumented code."""
    state = WorkflowState(task_dir)
    state.mark_docs_needed(files)


def is_complete(task_dir: str) -> tuple[bool, Optional[str]]:
    """Check if all required phases done."""
    state = WorkflowState(task_dir)
    return state.is_complete()


def find_active_task() -> Optional[str]:
    """Find the currently active task directory."""
    tasks_dir = Path(".tasks")
    if not tasks_dir.exists():
        return None

    active_tasks = []
    for task_dir in tasks_dir.iterdir():
        if task_dir.is_dir():
            state_file = task_dir / "state.json"
            if state_file.exists():
                with open(state_file) as f:
                    state = json.load(f)
                    complete, _ = WorkflowState(str(task_dir)).is_complete()
                    if not complete:
                        active_tasks.append((task_dir, state.get("updated_at", "")))

    if active_tasks:
        active_tasks.sort(key=lambda x: x[1], reverse=True)
        return str(active_tasks[0][0])

    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Workflow state management")
    parser.add_argument("command", choices=["get", "transition", "complete", "summary"])
    parser.add_argument("--task-dir", "-d", help="Task directory path")
    parser.add_argument("--phase", "-p", help="Target phase for transition")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    task_dir = args.task_dir or find_active_task()
    if not task_dir:
        print("Error: No task directory specified and no active task found", file=sys.stderr)
        sys.exit(1)

    state = WorkflowState(task_dir)

    if args.command == "get":
        print(state.to_json())

    elif args.command == "transition":
        if not args.phase:
            print("Error: --phase required for transition", file=sys.stderr)
            sys.exit(1)
        success, message = state.transition(args.phase)
        if args.json:
            print(json.dumps({"success": success, "message": message}))
        else:
            print(message)
        sys.exit(0 if success else 1)

    elif args.command == "complete":
        state.complete_phase()
        print(f"Marked {state.phase} as complete")

    elif args.command == "summary":
        summary = state.get_state_summary()
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"Task: {summary['task_id']}")
            print(f"Phase: {summary['current_phase']}")
            print(f"Completed: {', '.join(summary['phases_completed']) or 'none'}")
            print(f"Iteration: {summary['iteration']}")
            print(f"Review issues: {summary['review_issues_count']}")
            print(f"Docs needed: {summary['docs_needed_count']}")
            print(f"Complete: {summary['is_complete']}")
            if summary['missing_phase']:
                print(f"Missing: {summary['missing_phase']}")
