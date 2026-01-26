"""
State Management Tools for Agentic Workflow MCP Server

Wraps the WorkflowState class to provide MCP tool implementations for
workflow state management operations.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


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


def get_tasks_dir() -> Path:
    return Path.cwd() / ".tasks"


def find_task_dir(task_id: Optional[str] = None) -> Optional[Path]:
    if task_id:
        task_dir = get_tasks_dir() / task_id
        if task_dir.exists():
            return task_dir
        for d in get_tasks_dir().iterdir():
            if d.is_dir() and d.name.lower() == task_id.lower():
                return d
        return None

    return _find_active_task_dir()


def _find_active_task_dir() -> Optional[Path]:
    tasks_dir = get_tasks_dir()
    if not tasks_dir.exists():
        return None

    active_tasks = []
    for task_dir in tasks_dir.iterdir():
        if task_dir.is_dir():
            state_file = task_dir / "state.json"
            if state_file.exists():
                with open(state_file) as f:
                    state = json.load(f)
                    completed = set(state.get("phases_completed", []))
                    if state.get("phase"):
                        completed.add(state["phase"])
                    missing = [p for p in REQUIRED_PHASES if p not in completed]
                    if missing:
                        active_tasks.append((task_dir, state.get("updated_at", "")))

    if active_tasks:
        active_tasks.sort(key=lambda x: x[1], reverse=True)
        return active_tasks[0][0]

    return None


def _load_state(task_dir: Path) -> dict:
    state_file = task_dir / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return _create_default_state(task_dir.name)


def _create_default_state(task_id: str) -> dict:
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


def _save_state(task_dir: Path, state: dict) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat()
    state_file = task_dir / "state.json"
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def _get_next_task_id() -> str:
    tasks_dir = get_tasks_dir()
    if not tasks_dir.exists():
        return "TASK_001"

    existing = []
    for d in tasks_dir.iterdir():
        if d.is_dir():
            match = re.match(r"TASK_(\d+)", d.name)
            if match:
                existing.append(int(match.group(1)))

    next_num = max(existing, default=0) + 1
    return f"TASK_{next_num:03d}"


def _can_transition(state: dict, to_phase: str) -> tuple[bool, str]:
    if to_phase not in PHASE_ORDER:
        return False, f"Invalid phase: {to_phase}"

    current = state.get("phase")
    phases_completed = state.get("phases_completed", [])

    if current is None:
        if to_phase == "architect":
            return True, "Starting workflow with architect"
        return False, "Workflow must start with architect phase"

    if to_phase == current:
        return True, "Re-running current phase"

    if to_phase in phases_completed:
        if to_phase == "developer" and state.get("review_issues"):
            return True, "Looping back to developer due to review issues"
        return False, f"Phase {to_phase} already completed"

    current_idx = PHASE_ORDER.index(current)
    to_idx = PHASE_ORDER.index(to_phase)

    if to_idx == current_idx + 1:
        return True, f"Valid forward transition from {current} to {to_phase}"

    if to_phase == "developer" and current in ("reviewer", "skeptic"):
        return True, f"Valid loop-back from {current} to developer"

    return False, f"Cannot skip from {current} to {to_phase}"


def workflow_initialize(
    task_id: Optional[str] = None,
    description: Optional[str] = None
) -> dict[str, Any]:
    if not task_id:
        task_id = _get_next_task_id()

    task_dir = get_tasks_dir() / task_id

    if task_dir.exists():
        state_file = task_dir / "state.json"
        if state_file.exists():
            return {
                "success": False,
                "error": f"Task {task_id} already exists",
                "task_id": task_id
            }

    state = _create_default_state(task_id)
    state["phase"] = "architect"
    if description:
        state["description"] = description

    _save_state(task_dir, state)

    return {
        "success": True,
        "task_id": task_id,
        "task_dir": str(task_dir),
        "phase": "architect",
        "message": f"Initialized workflow for {task_id}, starting with architect phase"
    }


def workflow_transition(
    to_phase: str,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    can, reason = _can_transition(state, to_phase)

    if not can:
        return {
            "success": False,
            "error": reason,
            "current_phase": state.get("phase"),
            "phases_completed": state.get("phases_completed", [])
        }

    old_phase = state.get("phase")

    if old_phase and old_phase != to_phase and old_phase not in state["phases_completed"]:
        state["phases_completed"].append(old_phase)

    if to_phase == "developer" and old_phase in ("reviewer", "skeptic"):
        state["iteration"] = state.get("iteration", 1) + 1
        state["review_issues"] = []

    state["phase"] = to_phase
    _save_state(task_dir, state)

    return {
        "success": True,
        "from_phase": old_phase,
        "to_phase": to_phase,
        "reason": reason,
        "iteration": state.get("iteration", 1),
        "task_id": state.get("task_id")
    }


def workflow_get_state(task_id: Optional[str] = None) -> dict[str, Any]:
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    completed = set(state.get("phases_completed", []))
    if state.get("phase"):
        completed.add(state["phase"])
    missing = [p for p in REQUIRED_PHASES if p not in completed]
    is_complete = len(missing) == 0

    return {
        "task_id": state.get("task_id"),
        "task_dir": str(task_dir),
        "phase": state.get("phase"),
        "phases_completed": state.get("phases_completed", []),
        "iteration": state.get("iteration", 1),
        "review_issues": state.get("review_issues", []),
        "docs_needed": state.get("docs_needed", []),
        "is_complete": is_complete,
        "missing_phases": missing,
        "created_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
        "description": state.get("description")
    }


def workflow_add_review_issue(
    issue_type: str,
    description: str,
    task_id: Optional[str] = None,
    step: Optional[str] = None,
    severity: str = "medium"
) -> dict[str, Any]:
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    issue = {
        "type": issue_type,
        "description": description,
        "severity": severity,
        "added_at": datetime.now().isoformat()
    }
    if step:
        issue["step"] = step

    if "review_issues" not in state:
        state["review_issues"] = []
    state["review_issues"].append(issue)

    _save_state(task_dir, state)

    return {
        "success": True,
        "issue": issue,
        "total_issues": len(state["review_issues"]),
        "task_id": state.get("task_id")
    }


def workflow_mark_docs_needed(
    files: list[str],
    task_id: Optional[str] = None
) -> dict[str, Any]:
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    existing = set(state.get("docs_needed", []))
    new_files = [f for f in files if f not in existing]
    existing.update(files)
    state["docs_needed"] = list(existing)

    _save_state(task_dir, state)

    return {
        "success": True,
        "added": new_files,
        "total": len(state["docs_needed"]),
        "all_files": state["docs_needed"],
        "task_id": state.get("task_id")
    }


def workflow_complete_phase(task_id: Optional[str] = None) -> dict[str, Any]:
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    current = state.get("phase")

    if not current:
        return {
            "success": False,
            "error": "No current phase to complete"
        }

    if current not in state.get("phases_completed", []):
        if "phases_completed" not in state:
            state["phases_completed"] = []
        state["phases_completed"].append(current)
        _save_state(task_dir, state)

    completed = set(state.get("phases_completed", []))
    completed.add(current)
    missing = [p for p in REQUIRED_PHASES if p not in completed]

    return {
        "success": True,
        "completed_phase": current,
        "phases_completed": state["phases_completed"],
        "remaining_phases": missing,
        "task_id": state.get("task_id")
    }


def workflow_is_complete(task_id: Optional[str] = None) -> dict[str, Any]:
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    completed = set(state.get("phases_completed", []))
    if state.get("phase"):
        completed.add(state["phase"])

    missing = [p for p in REQUIRED_PHASES if p not in completed]
    is_complete = len(missing) == 0

    return {
        "is_complete": is_complete,
        "missing_phases": missing,
        "phases_completed": list(completed),
        "task_id": state.get("task_id")
    }


def workflow_can_transition(
    to_phase: str,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "can_transition": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    can, reason = _can_transition(state, to_phase)

    return {
        "can_transition": can,
        "reason": reason,
        "current_phase": state.get("phase"),
        "to_phase": to_phase,
        "task_id": state.get("task_id")
    }


def workflow_can_stop(task_id: Optional[str] = None) -> dict[str, Any]:
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "can_stop": True,
            "reason": "No active workflow task"
        }

    state = _load_state(task_dir)

    if state.get("phase") is None:
        return {
            "can_stop": True,
            "reason": "Workflow not started"
        }

    completed = set(state.get("phases_completed", []))
    if state.get("phase"):
        completed.add(state["phase"])

    missing = [p for p in REQUIRED_PHASES if p not in completed]

    if not missing:
        return {
            "can_stop": True,
            "reason": "All required phases completed",
            "phases_completed": list(completed)
        }

    phase_names = {
        "architect": "Architect",
        "developer": "Developer",
        "reviewer": "Reviewer",
        "implementer": "Implementer",
        "technical_writer": "Technical Writer"
    }

    missing_names = [phase_names.get(p, p) for p in missing]

    return {
        "can_stop": False,
        "reason": f"Workflow incomplete. Missing phases: {', '.join(missing_names)}",
        "missing_phases": missing,
        "current_phase": state.get("phase"),
        "phases_completed": state.get("phases_completed", []),
        "task_id": state.get("task_id")
    }


def list_tasks() -> list[dict[str, Any]]:
    tasks_dir = get_tasks_dir()
    if not tasks_dir.exists():
        return []

    tasks = []
    for task_dir in sorted(tasks_dir.iterdir()):
        if task_dir.is_dir():
            state_file = task_dir / "state.json"
            if state_file.exists():
                state = _load_state(task_dir)
                completed = set(state.get("phases_completed", []))
                if state.get("phase"):
                    completed.add(state["phase"])
                missing = [p for p in REQUIRED_PHASES if p not in completed]

                tasks.append({
                    "task_id": task_dir.name,
                    "phase": state.get("phase"),
                    "iteration": state.get("iteration", 1),
                    "is_complete": len(missing) == 0,
                    "updated_at": state.get("updated_at")
                })

    return tasks


def get_active_task() -> Optional[str]:
    task_dir = _find_active_task_dir()
    if task_dir:
        return task_dir.name
    return None
