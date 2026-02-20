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
    "feedback",
    "technical_writer"
]

REQUIRED_PHASES = [
    "architect",
    "developer",
    "reviewer",
    "implementer",
    "technical_writer"
]


def normalize_phase(phase: str) -> str:
    return phase.strip().lower().replace("-", "_")


class WorkflowState:
    """Manages workflow state for a single task."""

    def __init__(self, task_dir: str):
        self.task_dir = Path(task_dir)
        self.state_file = self.task_dir / "state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Load state from JSON file or create default state."""
        if self.state_file.exists():
            with open(self.state_file, "r", encoding="utf-8") as f:
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
            "implementation_progress": {
                "total_steps": 0,
                "current_step": 0,
                "steps_completed": []
            },
            "human_decisions": [],
            "knowledge_base_inventory": {
                "path": None,
                "files": []
            },
            "concerns": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

    def _save_state(self) -> None:
        """Persist state to JSON file."""
        self.task_dir.mkdir(parents=True, exist_ok=True)
        self._state["updated_at"] = datetime.now().isoformat()
        with open(self.state_file, "w", encoding="utf-8") as f:
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

        Respects workflow_mode.phases if set — in turbo mode the sequence
        is developer→implementer→technical_writer, so skipping architect/
        reviewer/skeptic is expected.

        Returns:
            Tuple of (can_transition, reason)
        """
        to_phase = normalize_phase(to_phase)

        # Use mode-specific phase order if available, else full PHASE_ORDER
        mode_phases = self._state.get("workflow_mode", {}).get("phases")
        phase_order = [normalize_phase(p) for p in mode_phases] if mode_phases else PHASE_ORDER

        if to_phase not in phase_order:
            # Phase not in this mode's pipeline — allow if it's a known phase
            if to_phase in PHASE_ORDER:
                return True, f"Phase {to_phase} not in current mode pipeline, allowed"
            return False, f"Invalid phase: {to_phase}"

        current = self.phase

        if current is None:
            first_phase = phase_order[0] if phase_order else "architect"
            if to_phase == first_phase:
                return True, f"Starting workflow with {first_phase}"
            return False, f"Workflow must start with {first_phase} phase"

        if to_phase == current:
            return True, "Re-running current phase"

        if to_phase in self.phases_completed:
            if to_phase == "developer" and self.review_issues:
                return True, "Looping back to developer due to review issues"
            return False, f"Phase {to_phase} already completed"

        # Check forward transition using mode-aware phase order
        current_norm = normalize_phase(current)
        if current_norm in phase_order and to_phase in phase_order:
            current_idx = phase_order.index(current_norm)
            to_idx = phase_order.index(to_phase)

            if to_idx == current_idx + 1:
                return True, f"Valid forward transition from {current} to {to_phase}"
        elif to_phase in phase_order:
            # Current phase not in mode pipeline (e.g. optional agent ran) — allow forward
            return True, f"Forward transition to {to_phase} after out-of-pipeline phase"

        if to_phase == "developer" and current in ("reviewer", "skeptic"):
            return True, f"Valid loop-back from {current} to developer"

        return False, f"Cannot skip from {current} to {to_phase}"

    def transition(self, to_phase: str) -> tuple[bool, str]:
        """
        Transition to a new phase if valid.

        Returns:
            Tuple of (success, message)
        """
        to_phase = normalize_phase(to_phase)
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

    def set_implementation_progress(self, total_steps: int, current_step: int = 0) -> None:
        """Set total implementation steps and optionally current step."""
        if "implementation_progress" not in self._state:
            self._state["implementation_progress"] = {
                "total_steps": 0,
                "current_step": 0,
                "steps_completed": []
            }
        self._state["implementation_progress"]["total_steps"] = total_steps
        self._state["implementation_progress"]["current_step"] = current_step
        self._save_state()

    def complete_implementation_step(self, step_id: str) -> None:
        """Mark an implementation step as completed."""
        if "implementation_progress" not in self._state:
            self._state["implementation_progress"] = {
                "total_steps": 0,
                "current_step": 0,
                "steps_completed": []
            }
        progress = self._state["implementation_progress"]
        if step_id not in progress["steps_completed"]:
            progress["steps_completed"].append(step_id)
        progress["current_step"] = len(progress["steps_completed"])
        self._save_state()

    def add_human_decision(self, checkpoint: str, decision: str, notes: str = "") -> None:
        """Record a human decision at a checkpoint."""
        if "human_decisions" not in self._state:
            self._state["human_decisions"] = []
        self._state["human_decisions"].append({
            "checkpoint": checkpoint,
            "decision": decision,
            "notes": notes,
            "timestamp": datetime.now().isoformat()
        })
        self._save_state()

    def set_knowledge_base_inventory(self, path: str, files: list) -> None:
        """Store knowledge base path and file inventory."""
        self._state["knowledge_base_inventory"] = {
            "path": path,
            "files": files
        }
        self._save_state()

    def add_concern(self, source: str, severity: str, description: str,
                    concern_id: Optional[str] = None) -> str:
        """Add a concern from an agent. Returns the concern ID."""
        if "concerns" not in self._state:
            self._state["concerns"] = []
        if concern_id is None:
            concern_id = f"C{len(self._state['concerns']) + 1:03d}"
        self._state["concerns"].append({
            "id": concern_id,
            "source": source,
            "severity": severity,
            "description": description,
            "addressed_by": [],
            "created_at": datetime.now().isoformat()
        })
        self._save_state()
        return concern_id

    def address_concern(self, concern_id: str, addressed_by: str) -> bool:
        """Mark a concern as addressed by a step or action."""
        if "concerns" not in self._state:
            return False
        for concern in self._state["concerns"]:
            if concern["id"] == concern_id:
                if addressed_by not in concern["addressed_by"]:
                    concern["addressed_by"].append(addressed_by)
                self._save_state()
                return True
        return False

    def is_complete(self) -> tuple[bool, Optional[str]]:
        """
        Check if workflow is complete (all required phases done).

        Respects workflow_mode phases if set (turbo/fast/minimal skip some phases).
        Falls back to REQUIRED_PHASES for workflows without a mode.

        Returns:
            Tuple of (is_complete, missing_phase or None)
        """
        # Check explicit completion status first
        if self._state.get("status") == "completed":
            return True, None

        completed = set(normalize_phase(p) for p in self.phases_completed)
        if self.phase:
            completed.add(normalize_phase(self.phase))

        # Use mode-specific phases if available, otherwise fall back to REQUIRED_PHASES
        mode_phases = self._state.get("workflow_mode", {}).get("phases")
        required = [normalize_phase(p) for p in mode_phases] if mode_phases else REQUIRED_PHASES

        for phase in required:
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


def _resolve_tasks_dir() -> Path:
    """Resolve .tasks/ to the main repo when running in a git worktree."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            git_common_dir = Path(result.stdout.strip())
            if git_common_dir.is_absolute():
                # Worktree: resolve to main repo
                return git_common_dir.parent / ".tasks"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return Path(".tasks")


def _detect_worktree_task_id(tasks_dir: Path) -> Optional[str]:
    """If running inside a git worktree, find the task ID that owns it."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        git_common_dir = Path(result.stdout.strip())
        if not git_common_dir.is_absolute():
            return None  # Normal repo, not a worktree
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None

    cwd = str(Path.cwd().resolve())
    main_repo = git_common_dir.parent

    for task_dir in tasks_dir.iterdir():
        if task_dir.is_dir():
            state_file = task_dir / "state.json"
            if state_file.exists():
                try:
                    with open(state_file, encoding="utf-8") as f:
                        state = json.load(f)
                    wt = state.get("worktree")
                    if wt and wt.get("status") == "active" and wt.get("path"):
                        import os
                        wt_abs = str(Path(os.path.normpath(
                            os.path.join(str(main_repo), wt["path"])
                        )).resolve())
                        if wt_abs == cwd:
                            return task_dir.name
                except (json.JSONDecodeError, OSError):
                    continue
    return None


def find_active_task() -> Optional[str]:
    """Find the currently active task directory.

    Priority:
    1. Worktree detection (match cwd to worktree paths)
    2. .tasks/.active_task file (session-local marker from crew_orchestrator)
    3. Fallback: most recently updated incomplete task
    """
    tasks_dir = _resolve_tasks_dir()
    if not tasks_dir.exists():
        return None

    # In a worktree, only the task that owns this worktree is "active"
    wt_task_id = _detect_worktree_task_id(tasks_dir)
    if wt_task_id:
        task_dir = tasks_dir / wt_task_id
        if task_dir.exists():
            return str(task_dir)
        return None

    # Check .active_task file (session-local marker written by crew_orchestrator)
    active_file = tasks_dir / ".active_task"
    if active_file.exists():
        try:
            task_id = active_file.read_text().strip()
            if task_id:
                task_dir = tasks_dir / task_id
                state_file = task_dir / "state.json"
                if state_file.exists():
                    with open(state_file, encoding="utf-8") as f:
                        state = json.load(f)
                    # Only use if task isn't completed (stale marker)
                    if state.get("status") != "completed":
                        return str(task_dir)
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: find the most recently updated incomplete task
    active_tasks = []
    for task_dir in tasks_dir.iterdir():
        if task_dir.is_dir():
            state_file = task_dir / "state.json"
            if state_file.exists():
                try:
                    with open(state_file, encoding="utf-8") as f:
                        state = json.load(f)
                except (json.JSONDecodeError, OSError):
                    continue
                # Skip tasks with active worktrees — they're worked on elsewhere
                wt = state.get("worktree")
                if wt and wt.get("status") == "active":
                    continue
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
