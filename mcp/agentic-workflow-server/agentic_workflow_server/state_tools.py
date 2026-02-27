"""
State Management Tools for Agentic Workflow MCP Server

This module provides a set of functions for managing the state of agentic workflow tasks.
It handles initialization, transitions, issue tracking, and persistence of task-specific
data to the local file system within the `.tasks/` directory. File locking is implemented
to ensure data integrity during concurrent access.
"""

import json
import os
import re
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from filelock import FileLock


# Resolve script paths at import time (immune to Path mocking in tests)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_FIX_WORKTREE_PATHS_SCRIPT = _REPO_ROOT / "scripts" / "fix-worktree-paths.py"

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

DISCOVERY_CATEGORIES = [
    "decision",
    "pattern",
    "gotcha",
    "blocker",
    "preference"
]

INTERACTION_ROLES = ["human", "agent", "system"]
INTERACTION_TYPES = [
    "message",
    "checkpoint_question",
    "checkpoint_response",
    "guidance",
    "escalation_question",
    "escalation_response",
    "state_change",
]

# 8 dark color schemes for worktree terminal tabs.  Cycled by task number.
# Each entry has: name (WT scheme name), tab (WT tab color), bg (background), fg (foreground).
CREW_COLOR_SCHEMES = [
    {"name": "Crew Ocean",    "tab": "#1A6B8A", "bg": "#0C1B2A", "fg": "#C8D6E5"},
    {"name": "Crew Forest",   "tab": "#2D7D46", "bg": "#0E1F14", "fg": "#C5D1C0"},
    {"name": "Crew Sunset",   "tab": "#C75B39", "bg": "#1F120E", "fg": "#D8C8BA"},
    {"name": "Crew Amethyst", "tab": "#7B5EA7", "bg": "#16121F", "fg": "#CCC4D8"},
    {"name": "Crew Steel",    "tab": "#5C7A8A", "bg": "#141C22", "fg": "#C0CCD4"},
    {"name": "Crew Ember",    "tab": "#B85C3A", "bg": "#1A110D", "fg": "#D4C4B4"},
    {"name": "Crew Frost",    "tab": "#4BA3C7", "bg": "#0D1820", "fg": "#C4D4E0"},
    {"name": "Crew Earth",    "tab": "#8D7B4A", "bg": "#1A170E", "fg": "#D0C8B8"},
]


_cached_tasks_dir: Optional[Path] = None


def _resolve_main_repo_tasks_dir() -> Optional[Path]:
    """Resolve .tasks/ dir to the main repo when running in a git worktree.

    Uses `git rev-parse --git-common-dir`:
    - Normal repo: returns `.git` (relative) → cwd/.tasks/
    - Worktree: returns absolute path to main .git → main_repo/.tasks/
    - Not in git: returns None → fall back to cwd/.tasks/
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None

        git_common_dir = Path(result.stdout.strip())

        if git_common_dir.is_absolute():
            # Worktree: git-common-dir is absolute path to main .git
            return git_common_dir.parent / ".tasks"
        else:
            # Normal repo: git-common-dir is relative (e.g., ".git")
            return Path.cwd() / ".tasks"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def get_tasks_dir() -> Path:
    global _cached_tasks_dir
    if _cached_tasks_dir is not None:
        return _cached_tasks_dir

    resolved = _resolve_main_repo_tasks_dir()
    _cached_tasks_dir = resolved if resolved else Path.cwd() / ".tasks"
    return _cached_tasks_dir


def find_task_dir(task_id: Optional[str] = None) -> Optional[Path]:
    if task_id:
        task_dir = get_tasks_dir() / task_id
        if task_dir.exists():
            return task_dir
        tasks_dir = get_tasks_dir()
        if tasks_dir.exists():
            for d in tasks_dir.iterdir():
                if d.is_dir() and d.name.lower() == task_id.lower():
                    return d
        return None

    return _find_active_task_dir()


def _detect_worktree_task_id() -> Optional[str]:
    """If running inside a git worktree, find the task ID that owns it.

    Checks each task's worktree metadata to see if its path matches cwd.
    Returns the task_id if found, None if not in a worktree or no match.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        git_common_dir = Path(result.stdout.strip())
        if not git_common_dir.is_absolute():
            # Not a worktree (normal repo)
            return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None

    # We're in a worktree. Match cwd against task worktree paths.
    cwd = str(Path.cwd().resolve())
    tasks_dir = get_tasks_dir()
    if not tasks_dir.exists():
        return None

    for task_dir in tasks_dir.iterdir():
        if task_dir.is_dir():
            state_file = task_dir / "state.json"
            if state_file.exists():
                try:
                    with open(state_file) as f:
                        state = json.load(f)
                    wt = state.get("worktree")
                    if wt and wt.get("status") == "active" and wt.get("path"):
                        # Resolve the worktree path relative to the main repo
                        main_repo = git_common_dir.parent
                        wt_abs = str(Path(os.path.normpath(
                            os.path.join(str(main_repo), wt["path"])
                        )).resolve())
                        if wt_abs == cwd:
                            return task_dir.name
                except (json.JSONDecodeError, OSError):
                    continue
    return None


def _find_active_task_dir() -> Optional[Path]:
    tasks_dir = get_tasks_dir()
    if not tasks_dir.exists():
        return None

    # In a worktree, only the task that owns this worktree is "active"
    wt_task_id = _detect_worktree_task_id()
    if wt_task_id:
        task_dir = tasks_dir / wt_task_id
        if task_dir.exists():
            return task_dir
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
                    with open(state_file) as f:
                        state = json.load(f)
                    # Only use if task isn't completed (stale marker cleanup)
                    if state.get("status") != "completed":
                        return task_dir
        except (OSError, json.JSONDecodeError):
            pass

    # Fallback: find the most recently updated incomplete task
    active_tasks = []
    for task_dir in tasks_dir.iterdir():
        if task_dir.is_dir():
            state_file = task_dir / "state.json"
            if state_file.exists():
                with open(state_file) as f:
                    state = json.load(f)
                    # Skip completed tasks
                    if state.get("status") == "completed":
                        continue
                    # Skip tasks with active worktrees — they're worked on elsewhere
                    wt = state.get("worktree")
                    if wt and wt.get("status") == "active":
                        continue
                    completed = set(_normalize_phase(p) for p in state.get("phases_completed", []))
                    if state.get("phase"):
                        completed.add(_normalize_phase(state["phase"]))
                    # Use mode-specific phases if available
                    mode_phases = state.get("workflow_mode", {}).get("phases")
                    required = [_normalize_phase(p) for p in mode_phases] if mode_phases else REQUIRED_PHASES
                    missing = [p for p in required if p not in completed]
                    if missing:
                        active_tasks.append((task_dir, state.get("updated_at", "")))

    if active_tasks:
        active_tasks.sort(key=lambda x: x[1], reverse=True)
        return active_tasks[0][0]

    return None


def _load_state(task_dir: Path) -> dict:
    state_file = task_dir / "state.json"
    if state_file.exists():
        lock_file = task_dir / "state.json.lock"
        with FileLock(str(lock_file)):
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
        "worktree": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }


def _log_state_changes(task_dir: Path, old_state: dict, new_state: dict) -> None:
    """Append a state_change entry to interactions.jsonl when tracked fields change."""
    try:
        changes: dict[str, Any] = {}

        # Scalar fields
        for field in ("phase", "status"):
            old_val = old_state.get(field)
            new_val = new_state.get(field)
            if old_val != new_val:
                changes[field] = {"from": old_val, "to": new_val}

        # List field — phases_completed
        old_list = old_state.get("phases_completed", [])
        new_list = new_state.get("phases_completed", [])
        if old_list != new_list:
            changes["phases_completed"] = {"from": old_list, "to": new_list}

        # Nested scalar — workflow_mode.effective
        old_mode = old_state.get("workflow_mode", {}).get("effective")
        new_mode = new_state.get("workflow_mode", {}).get("effective")
        if old_mode != new_mode:
            changes["workflow_mode.effective"] = {"from": old_mode, "to": new_mode}

        if not changes:
            return

        # Build human-readable summary
        parts = []
        for field, delta in changes.items():
            parts.append(f"{field} {delta['from']} -> {delta['to']}")
        content = "State changed: " + ", ".join(parts)

        entry = {
            "timestamp": datetime.now().isoformat(),
            "role": "system",
            "content": content,
            "type": "state_change",
            "agent": "",
            "phase": new_state.get("phase", ""),
            "metadata": {"changes": changes},
        }

        interactions_file = task_dir / "interactions.jsonl"
        lock_file = task_dir / "interactions.jsonl.lock"
        with FileLock(str(lock_file), timeout=5):
            with open(interactions_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never block state persistence


def _save_state(task_dir: Path, state: dict) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat()
    state_file = task_dir / "state.json"
    lock_file = task_dir / "state.json.lock"

    old_state = None
    with FileLock(str(lock_file)):
        if state_file.exists():
            try:
                with open(state_file, "r") as f:
                    old_state = json.load(f)
            except Exception:
                old_state = None
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

    if old_state is not None:
        _log_state_changes(task_dir, old_state, state)


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


def _normalize_phase(phase: str) -> str:
    return phase.strip().lower().replace("-", "_")


def _can_transition(state: dict, to_phase: str) -> tuple[bool, str]:
    to_phase = _normalize_phase(to_phase)

    # Build the valid phase list: PHASE_ORDER + any custom phases from the mode
    mode_phases = state.get("workflow_mode", {}).get("phases", [])
    valid_phases = list(PHASE_ORDER)
    for p in mode_phases:
        if p not in valid_phases:
            valid_phases.append(p)

    if to_phase not in valid_phases:
        return False, f"Invalid phase: {to_phase}"

    current = _normalize_phase(state["phase"]) if state.get("phase") else None
    phases_completed = [_normalize_phase(p) for p in state.get("phases_completed", [])]

    if current is None:
        if to_phase == "architect":
            return True, "Starting workflow with architect"
        # Allow starting with any phase if mode doesn't include architect
        if mode_phases and to_phase == mode_phases[0]:
            return True, f"Starting workflow with {to_phase} (mode skips architect)"
        return False, "Workflow must start with architect phase"

    if to_phase == current:
        return True, "Re-running current phase"

    if to_phase in phases_completed:
        if to_phase == "developer" and state.get("review_issues"):
            return True, "Looping back to developer due to review issues"
        return False, f"Phase {to_phase} already completed"

    # Use mode_phases as the ordering if available, else fall back to PHASE_ORDER
    ordering = mode_phases if mode_phases else PHASE_ORDER

    if current in ordering and to_phase in ordering:
        current_idx = ordering.index(current)
        to_idx = ordering.index(to_phase)

        if to_idx == current_idx + 1:
            return True, f"Valid forward transition from {current} to {to_phase}"

        # Allow forward skips when intermediate phases are not in the mode
        if to_idx > current_idx:
            if mode_phases:
                skipped = [ordering[i] for i in range(current_idx + 1, to_idx)]
                if all(p not in mode_phases for p in skipped):
                    return True, f"Valid forward skip from {current} to {to_phase} (skipped phases not in mode)"
    elif current not in ordering and to_phase in ordering:
        # Current phase is custom/unknown, allow transition to any mode phase
        return True, f"Transition from custom phase {current} to {to_phase}"

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
    to_phase = _normalize_phase(to_phase)
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

    completed = set(_normalize_phase(p) for p in state.get("phases_completed", []))
    if state.get("phase"):
        completed.add(_normalize_phase(state["phase"]))
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

    completed = set(_normalize_phase(p) for p in state.get("phases_completed", []))
    completed.add(_normalize_phase(current))
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

    # Check explicit completion status first
    if state.get("status") == "completed":
        completed = set(_normalize_phase(p) for p in state.get("phases_completed", []))
        return {
            "is_complete": True,
            "missing_phases": [],
            "phases_completed": list(completed),
            "task_id": state.get("task_id")
        }

    completed = set(_normalize_phase(p) for p in state.get("phases_completed", []))
    if state.get("phase"):
        completed.add(_normalize_phase(state["phase"]))

    # Use mode-specific phases if available, otherwise fall back to REQUIRED_PHASES
    mode_phases = state.get("workflow_mode", {}).get("phases")
    required = [_normalize_phase(p) for p in mode_phases] if mode_phases else REQUIRED_PHASES

    missing = [p for p in required if p not in completed]
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
    to_phase = _normalize_phase(to_phase)
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

    # Check explicit completion status first
    if state.get("status") == "completed":
        return {
            "can_stop": True,
            "reason": "Workflow completed",
            "task_id": state.get("task_id")
        }

    if state.get("phase") is None:
        return {
            "can_stop": True,
            "reason": "Workflow not started"
        }

    # Worktree-setup tasks: worktree active but no phases completed yet
    worktree = state.get("worktree")
    if worktree and worktree.get("status") == "active":
        if not state.get("phases_completed"):
            return {
                "can_stop": True,
                "reason": "Worktree created — workflow will run in the worktree directory",
                "task_id": state.get("task_id"),
                "worktree": worktree
            }

    completed = set(_normalize_phase(p) for p in state.get("phases_completed", []))
    if state.get("phase"):
        completed.add(_normalize_phase(state["phase"]))

    # Use mode-specific phases if available, otherwise fall back to REQUIRED_PHASES
    mode_phases = state.get("workflow_mode", {}).get("phases")
    required = [_normalize_phase(p) for p in mode_phases] if mode_phases else REQUIRED_PHASES

    missing = [p for p in required if p not in completed]

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
        "skeptic": "Skeptic",
        "implementer": "Implementer",
        "feedback": "Feedback",
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
                completed = set(_normalize_phase(p) for p in state.get("phases_completed", []))
                if state.get("phase"):
                    completed.add(_normalize_phase(state["phase"]))
                missing = [p for p in REQUIRED_PHASES if p not in completed]
                is_complete = len(missing) == 0

                # Worktree metadata
                worktree = state.get("worktree")
                wt_status = None
                wt_path = None
                wt_branch = None
                wt_action = None

                if worktree:
                    wt_status = worktree.get("status")
                    wt_path = worktree.get("path")
                    wt_branch = worktree.get("branch")

                    if wt_status == "active" and is_complete:
                        wt_action = "cleanup"
                    elif wt_status == "active" and not is_complete:
                        wt_action = "resume"
                    elif wt_status in ("cleaned", "recycled"):
                        wt_action = "done"
                    elif wt_status == "recyclable":
                        wt_action = "recyclable"

                task_entry = {
                    "task_id": task_dir.name,
                    "phase": state.get("phase"),
                    "iteration": state.get("iteration", 1),
                    "is_complete": is_complete,
                    "updated_at": state.get("updated_at"),
                    "worktree": {
                        "status": wt_status,
                        "path": wt_path,
                        "branch": wt_branch,
                        "action": wt_action,
                    } if worktree else None,
                }
                tasks.append(task_entry)

    return tasks


def get_active_task() -> Optional[str]:
    task_dir = _find_active_task_dir()
    if task_dir:
        return task_dir.name
    return None


def workflow_set_implementation_progress(
    total_steps: int,
    current_step: int = 0,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Set implementation progress tracking."""
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    if "implementation_progress" not in state:
        state["implementation_progress"] = {
            "total_steps": 0,
            "current_step": 0,
            "steps_completed": []
        }

    state["implementation_progress"]["total_steps"] = total_steps
    state["implementation_progress"]["current_step"] = current_step

    _save_state(task_dir, state)

    return {
        "success": True,
        "implementation_progress": state["implementation_progress"],
        "task_id": state.get("task_id")
    }


def workflow_complete_step(
    step_id: str,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Mark an implementation step as completed."""
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    if "implementation_progress" not in state:
        state["implementation_progress"] = {
            "total_steps": 0,
            "current_step": 0,
            "steps_completed": []
        }

    progress = state["implementation_progress"]
    if step_id not in progress["steps_completed"]:
        progress["steps_completed"].append(step_id)
    progress["current_step"] = len(progress["steps_completed"])

    _save_state(task_dir, state)

    return {
        "success": True,
        "step_id": step_id,
        "implementation_progress": progress,
        "task_id": state.get("task_id")
    }


def workflow_add_human_decision(
    checkpoint: str,
    decision: str,
    notes: str = "",
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Record a human decision at a checkpoint."""
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    if "human_decisions" not in state:
        state["human_decisions"] = []

    decision_record = {
        "checkpoint": checkpoint,
        "decision": decision,
        "notes": notes,
        "timestamp": datetime.now().isoformat()
    }
    state["human_decisions"].append(decision_record)

    _save_state(task_dir, state)

    return {
        "success": True,
        "decision": decision_record,
        "total_decisions": len(state["human_decisions"]),
        "task_id": state.get("task_id")
    }


def workflow_set_kb_inventory(
    path: str,
    files: list[str],
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Store knowledge base inventory."""
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    state["knowledge_base_inventory"] = {
        "path": path,
        "files": files
    }

    _save_state(task_dir, state)

    return {
        "success": True,
        "knowledge_base_inventory": state["knowledge_base_inventory"],
        "task_id": state.get("task_id")
    }


def workflow_add_concern(
    source: str,
    severity: str,
    description: str,
    concern_id: Optional[str] = None,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Add a concern from an agent."""
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    if "concerns" not in state:
        state["concerns"] = []

    if concern_id is None:
        concern_id = f"C{len(state['concerns']) + 1:03d}"

    concern = {
        "id": concern_id,
        "source": source,
        "severity": severity,
        "description": description,
        "addressed_by": [],
        "created_at": datetime.now().isoformat()
    }
    state["concerns"].append(concern)

    _save_state(task_dir, state)

    return {
        "success": True,
        "concern": concern,
        "total_concerns": len(state["concerns"]),
        "task_id": state.get("task_id")
    }


def workflow_address_concern(
    concern_id: str,
    addressed_by: str,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Mark a concern as addressed."""
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    if "concerns" not in state:
        return {
            "success": False,
            "error": f"Concern {concern_id} not found"
        }

    for concern in state["concerns"]:
        if concern["id"] == concern_id:
            if addressed_by not in concern["addressed_by"]:
                concern["addressed_by"].append(addressed_by)
            _save_state(task_dir, state)
            return {
                "success": True,
                "concern": concern,
                "task_id": state.get("task_id")
            }

    return {
        "success": False,
        "error": f"Concern {concern_id} not found"
    }


def workflow_get_concerns(
    task_id: Optional[str] = None,
    unaddressed_only: bool = False
) -> dict[str, Any]:
    """Get all concerns, optionally filtering to unaddressed only."""
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    concerns = state.get("concerns", [])

    if unaddressed_only:
        concerns = [c for c in concerns if not c.get("addressed_by")]

    return {
        "concerns": concerns,
        "total": len(concerns),
        "unaddressed_count": len([c for c in state.get("concerns", []) if not c.get("addressed_by")]),
        "task_id": state.get("task_id")
    }


def workflow_save_discovery(
    category: str,
    content: str,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Save a discovery to persistent memory for context preservation."""
    if category not in DISCOVERY_CATEGORIES:
        return {
            "success": False,
            "error": f"Invalid category '{category}'. Must be one of: {', '.join(DISCOVERY_CATEGORIES)}"
        }

    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    memory_dir = task_dir / "memory"
    memory_dir.mkdir(exist_ok=True)

    discovery = {
        "timestamp": datetime.now().isoformat(),
        "category": category,
        "content": content
    }

    discoveries_file = memory_dir / "discoveries.jsonl"
    with open(discoveries_file, "a") as f:
        f.write(json.dumps(discovery) + "\n")

    return {
        "success": True,
        "discovery": discovery,
        "task_id": task_dir.name
    }


def workflow_get_discoveries(
    category: Optional[str] = None,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Retrieve saved discoveries, optionally filtered by category."""
    if category is not None and category not in DISCOVERY_CATEGORIES:
        return {
            "error": f"Invalid category '{category}'. Must be one of: {', '.join(DISCOVERY_CATEGORIES)}"
        }

    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    discoveries_file = task_dir / "memory" / "discoveries.jsonl"
    if not discoveries_file.exists():
        return {
            "discoveries": [],
            "count": 0,
            "task_id": task_dir.name
        }

    discoveries = []
    with open(discoveries_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if category is None or entry.get("category") == category:
                    discoveries.append(entry)
            except json.JSONDecodeError:
                # Skip malformed lines
                continue

    return {
        "discoveries": discoveries,
        "count": len(discoveries),
        "task_id": task_dir.name
    }


def workflow_flush_context(
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Return all discoveries for context preservation before compaction."""
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    discoveries_file = task_dir / "memory" / "discoveries.jsonl"
    if not discoveries_file.exists():
        return {
            "discoveries": [],
            "count": 0,
            "by_category": {},
            "task_id": task_dir.name
        }

    discoveries = []
    by_category: dict[str, list] = {}

    with open(discoveries_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                discoveries.append(entry)
                cat = entry.get("category", "unknown")
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(entry)
            except json.JSONDecodeError:
                continue

    return {
        "discoveries": discoveries,
        "count": len(discoveries),
        "by_category": {cat: len(items) for cat, items in by_category.items()},
        "task_id": task_dir.name
    }


def workflow_get_context_usage(
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Estimate context usage for the task based on files in the task directory.

    Returns information about files that have been created/loaded during the workflow,
    helping agents understand context pressure and make pruning decisions.
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    # Estimate tokens per character (rough approximation)
    CHARS_PER_TOKEN = 4

    files_info = []
    total_size_bytes = 0
    total_tokens_estimate = 0

    # Scan task directory for relevant files
    for file_path in task_dir.rglob("*"):
        if file_path.is_file():
            try:
                size = file_path.stat().st_size
                total_size_bytes += size
                tokens_estimate = size // CHARS_PER_TOKEN
                total_tokens_estimate += tokens_estimate

                rel_path = file_path.relative_to(task_dir)
                files_info.append({
                    "path": str(rel_path),
                    "size_bytes": size,
                    "tokens_estimate": tokens_estimate,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })
            except (OSError, IOError):
                continue

    # Sort by size descending to show largest files first
    files_info.sort(key=lambda x: x["size_bytes"], reverse=True)

    # Estimate context window usage (Claude has ~200k tokens)
    # This is a rough estimate - actual usage depends on what's loaded
    MAX_CONTEXT_TOKENS = 200000
    usage_percentage = min(100, (total_tokens_estimate / MAX_CONTEXT_TOKENS) * 100)

    return {
        "task_id": task_dir.name,
        "total_size_bytes": total_size_bytes,
        "total_size_kb": round(total_size_bytes / 1024, 2),
        "total_tokens_estimate": total_tokens_estimate,
        "context_usage_percent": round(usage_percentage, 1),
        "file_count": len(files_info),
        "files": files_info[:20],  # Top 20 largest files
        "recommendation": _get_context_recommendation(usage_percentage)
    }


def _get_context_recommendation(usage_percent: float) -> str:
    """Generate a recommendation based on context usage."""
    if usage_percent < 30:
        return "Context usage is low. No action needed."
    elif usage_percent < 60:
        return "Context usage is moderate. Consider saving important discoveries."
    elif usage_percent < 80:
        return "Context usage is high. Recommend pruning old outputs and saving critical context."
    else:
        return "Context usage is critical. Prune aggressively and save all important discoveries before compaction."


def workflow_prune_old_outputs(
    keep_last_n: int = 5,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Prune old tool outputs to reduce context pressure.

    Creates summaries of pruned content and stores them, allowing context
    to be reduced while preserving key information about what was done.

    Args:
        keep_last_n: Number of recent outputs to keep intact (default: 5)
        task_id: Optional task identifier

    Returns:
        Summary of pruning actions taken
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    pruned_dir = task_dir / "pruned"
    pruned_dir.mkdir(exist_ok=True)

    # Track what we're pruning
    pruned_files = []
    preserved_files = []
    bytes_saved = 0

    # Define files that are safe to prune (verbose outputs)
    PRUNABLE_PATTERNS = [
        "repomix-output.txt",
        "gemini-analysis.md",
        "*.log",
    ]

    # Define files that should never be pruned
    PRESERVE_PATTERNS = [
        "state.json",
        "plan.md",
        "config.yaml",
        "task.md",
        "architect.md",
        "developer.md",
        "reviewer.md",
        "skeptic.md",
    ]

    # Get all files sorted by modification time (oldest first)
    all_files = []
    for file_path in task_dir.iterdir():
        if file_path.is_file():
            all_files.append((file_path, file_path.stat().st_mtime))

    all_files.sort(key=lambda x: x[1])  # Sort by mtime, oldest first

    # Categorize files
    prunable = []
    for file_path, mtime in all_files:
        name = file_path.name

        # Check if should be preserved
        should_preserve = any(
            name == pattern or (pattern.startswith("*") and name.endswith(pattern[1:]))
            for pattern in PRESERVE_PATTERNS
        )

        if should_preserve:
            preserved_files.append(name)
            continue

        # Check if prunable
        is_prunable = any(
            name == pattern or (pattern.startswith("*") and name.endswith(pattern[1:]))
            for pattern in PRUNABLE_PATTERNS
        )

        # Also prune large files (>50KB) that aren't in preserve list
        if is_prunable or file_path.stat().st_size > 50 * 1024:
            prunable.append(file_path)

    # Keep the most recent N prunable files, prune the rest
    # Note: prunable[:-0] returns empty list, so handle keep_last_n=0 specially
    if keep_last_n == 0:
        files_to_prune = prunable
    elif len(prunable) > keep_last_n:
        files_to_prune = prunable[:-keep_last_n]
    else:
        files_to_prune = []

    for file_path in files_to_prune:
        try:
            original_size = file_path.stat().st_size

            # Create a summary entry
            summary = {
                "original_file": file_path.name,
                "original_size_bytes": original_size,
                "pruned_at": datetime.now().isoformat(),
                "summary": f"Pruned {file_path.name} ({original_size} bytes)"
            }

            # For text files, keep first and last few lines as context
            if file_path.suffix in [".txt", ".md", ".log", ".json", ".jsonl"]:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()

                    if len(lines) > 20:
                        summary["head"] = "".join(lines[:10])
                        summary["tail"] = "".join(lines[-10:])
                        summary["total_lines"] = len(lines)
                    else:
                        summary["content"] = "".join(lines)
                except Exception:
                    pass

            # Save summary
            summary_file = pruned_dir / f"{file_path.stem}_summary.json"
            with open(summary_file, "w") as f:
                json.dump(summary, f, indent=2)

            # Remove original file
            file_path.unlink()

            bytes_saved += original_size
            pruned_files.append({
                "file": file_path.name,
                "size_bytes": original_size,
                "summary_at": str(summary_file.relative_to(task_dir))
            })

        except Exception as e:
            # Skip files that can't be pruned
            continue

    return {
        "success": True,
        "task_id": task_dir.name,
        "pruned_count": len(pruned_files),
        "pruned_files": pruned_files,
        "bytes_saved": bytes_saved,
        "bytes_saved_kb": round(bytes_saved / 1024, 2),
        "preserved_files": preserved_files,
        "kept_recent": min(keep_last_n, len(prunable)),
        "message": f"Pruned {len(pruned_files)} files, saved {round(bytes_saved/1024, 2)}KB"
    }


def workflow_search_memories(
    query: str,
    task_ids: Optional[list[str]] = None,
    category: Optional[str] = None,
    max_results: int = 20
) -> dict[str, Any]:
    """Search across task memories using keyword matching.

    Searches discoveries from multiple tasks, allowing agents to learn from
    past task experiences and avoid re-discovering the same patterns.

    Args:
        query: Search query (case-insensitive keyword matching)
        task_ids: Optional list of task IDs to search. If None, searches all tasks.
        category: Optional category filter (decision, pattern, gotcha, blocker, preference)
        max_results: Maximum number of results to return (default: 20)

    Returns:
        Matching discoveries across tasks, sorted by relevance
    """
    if category is not None and category not in DISCOVERY_CATEGORIES:
        return {
            "error": f"Invalid category '{category}'. Must be one of: {', '.join(DISCOVERY_CATEGORIES)}"
        }

    tasks_dir = get_tasks_dir()
    if not tasks_dir.exists():
        return {
            "results": [],
            "count": 0,
            "tasks_searched": 0
        }

    # Determine which tasks to search
    if task_ids:
        search_dirs = []
        for tid in task_ids:
            task_dir = find_task_dir(tid)
            if task_dir:
                search_dirs.append(task_dir)
    else:
        # Search all tasks
        search_dirs = [d for d in tasks_dir.iterdir() if d.is_dir()]

    results = []
    tasks_searched = 0
    query_lower = query.lower()
    query_words = query_lower.split()

    for task_dir in search_dirs:
        discoveries_file = task_dir / "memory" / "discoveries.jsonl"
        if not discoveries_file.exists():
            continue

        tasks_searched += 1

        with open(discoveries_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)

                    # Category filter
                    if category and entry.get("category") != category:
                        continue

                    # Keyword matching - check if any query word is in content
                    content_lower = entry.get("content", "").lower()
                    matches = sum(1 for word in query_words if word in content_lower)

                    if matches > 0:
                        results.append({
                            "task_id": task_dir.name,
                            "category": entry.get("category"),
                            "content": entry.get("content"),
                            "timestamp": entry.get("timestamp"),
                            "relevance": matches / len(query_words)  # 0-1 score
                        })
                except json.JSONDecodeError:
                    continue

    # Sort by relevance (highest first), then by timestamp (newest first)
    results.sort(key=lambda x: (-x["relevance"], x.get("timestamp", "") or ""), reverse=False)
    results.sort(key=lambda x: x["relevance"], reverse=True)

    # Limit results
    results = results[:max_results]

    return {
        "results": results,
        "count": len(results),
        "tasks_searched": tasks_searched,
        "query": query
    }


def workflow_link_tasks(
    task_id: str,
    related_task_ids: list[str],
    relationship: str = "related"
) -> dict[str, Any]:
    """Link related tasks for context inheritance.

    Creates bidirectional links between tasks, allowing agents to reference
    and learn from related prior work.

    Args:
        task_id: The task to add links to
        related_task_ids: List of related task IDs to link
        relationship: Type of relationship (related, builds_on, supersedes, blocked_by)

    Returns:
        Updated task links
    """
    valid_relationships = ["related", "builds_on", "supersedes", "blocked_by"]
    if relationship not in valid_relationships:
        return {
            "success": False,
            "error": f"Invalid relationship '{relationship}'. Must be one of: {', '.join(valid_relationships)}"
        }

    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": f"Task {task_id} not found"
        }

    # Verify all related tasks exist
    valid_related = []
    invalid_related = []
    for related_id in related_task_ids:
        related_dir = find_task_dir(related_id)
        if related_dir:
            valid_related.append(related_dir.name)
        else:
            invalid_related.append(related_id)

    if not valid_related:
        return {
            "success": False,
            "error": f"No valid related tasks found. Invalid: {invalid_related}"
        }

    # Load current state
    state = _load_state(task_dir)

    # Initialize links structure if needed
    if "linked_tasks" not in state:
        state["linked_tasks"] = {}

    if relationship not in state["linked_tasks"]:
        state["linked_tasks"][relationship] = []

    # Add new links (avoid duplicates)
    existing = set(state["linked_tasks"][relationship])
    new_links = [t for t in valid_related if t not in existing]
    state["linked_tasks"][relationship].extend(new_links)

    _save_state(task_dir, state)

    # Create reverse links for bidirectional relationships
    reverse_relationship = {
        "related": "related",
        "builds_on": "built_upon_by",
        "supersedes": "superseded_by",
        "blocked_by": "blocks"
    }.get(relationship, "related")

    for related_id in new_links:
        related_dir = find_task_dir(related_id)
        if related_dir:
            related_state = _load_state(related_dir)
            if "linked_tasks" not in related_state:
                related_state["linked_tasks"] = {}
            if reverse_relationship not in related_state["linked_tasks"]:
                related_state["linked_tasks"][reverse_relationship] = []
            if task_dir.name not in related_state["linked_tasks"][reverse_relationship]:
                related_state["linked_tasks"][reverse_relationship].append(task_dir.name)
            _save_state(related_dir, related_state)

    return {
        "success": True,
        "task_id": task_dir.name,
        "linked_tasks": state["linked_tasks"],
        "new_links": new_links,
        "invalid_tasks": invalid_related if invalid_related else None
    }


def workflow_get_linked_tasks(
    task_id: Optional[str] = None,
    include_memories: bool = False
) -> dict[str, Any]:
    """Get all tasks linked to the specified task.

    Args:
        task_id: Task identifier. If not provided, uses active task.
        include_memories: If True, include recent discoveries from linked tasks

    Returns:
        Linked tasks and optionally their recent discoveries
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    linked_tasks = state.get("linked_tasks", {})

    result = {
        "task_id": task_dir.name,
        "linked_tasks": linked_tasks
    }

    if include_memories and linked_tasks:
        # Collect all linked task IDs
        all_linked = set()
        for relationship, task_list in linked_tasks.items():
            all_linked.update(task_list)

        # Get recent discoveries from linked tasks
        linked_memories = {}
        for linked_id in all_linked:
            linked_dir = find_task_dir(linked_id)
            if linked_dir:
                discoveries_file = linked_dir / "memory" / "discoveries.jsonl"
                if discoveries_file.exists():
                    discoveries = []
                    with open(discoveries_file, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    discoveries.append(json.loads(line))
                                except json.JSONDecodeError:
                                    continue
                    # Keep only last 10 discoveries per task
                    linked_memories[linked_id] = discoveries[-10:]

        result["linked_memories"] = linked_memories

    return result


# Default resilience configuration
DEFAULT_RESILIENCE_CONFIG = {
    "retry": {
        "max_attempts": 3,
        "backoff_seconds": [60, 300, 1500]  # 1m, 5m, 25m
    },
    "fallback_chain": [
        {"model": "claude-opus-4-6", "timeout": 120},
        {"model": "claude-opus-4", "timeout": 120},
        {"model": "claude-sonnet-4", "timeout": 60},
        {"model": "gemini", "timeout": 60}
    ],
    "cooldown": {
        "rate_limit_seconds": 60,
        "error_seconds": 300,
        "billing_seconds": 18000,  # 5 hours
        "max_cooldown_seconds": 3600  # 1 hour cap for regular errors
    }
}

# Error types that trigger different cooldown behaviors
ERROR_TYPES = [
    "rate_limit",      # 429 - too many requests
    "overloaded",      # 529 - API overloaded
    "timeout",         # Request timeout
    "server_error",    # 5xx errors
    "billing",         # Payment/quota issues
    "auth",            # Authentication failures
    "unknown"          # Other errors
]


def _get_resilience_state_file() -> Path:
    """Get the path to the global resilience state file."""
    tasks_dir = get_tasks_dir()
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return tasks_dir / ".resilience_state.json"


def _load_resilience_state() -> dict:
    """Load the global resilience state."""
    state_file = _get_resilience_state_file()
    if state_file.exists():
        with open(state_file, "r") as f:
            return json.load(f)
    return {
        "models": {},
        "updated_at": datetime.now().isoformat()
    }


def _save_resilience_state(state: dict) -> None:
    """Save the global resilience state."""
    state["updated_at"] = datetime.now().isoformat()
    state_file = _get_resilience_state_file()
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def workflow_record_model_error(
    model: str,
    error_type: str,
    error_message: str = "",
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Record a model error for cooldown tracking.

    Tracks errors per model to enable intelligent failover and backoff.
    Errors trigger cooldowns that prevent using a model until it recovers.

    Args:
        model: Model identifier (e.g., 'claude-opus-4', 'claude-sonnet-4')
        error_type: Type of error (rate_limit, overloaded, timeout, server_error, billing, auth, unknown)
        error_message: Optional error message for debugging
        task_id: Optional task context

    Returns:
        Updated model state including cooldown information
    """
    if error_type not in ERROR_TYPES:
        return {
            "success": False,
            "error": f"Invalid error_type '{error_type}'. Must be one of: {', '.join(ERROR_TYPES)}"
        }

    state = _load_resilience_state()
    now = datetime.now()

    # Initialize model state if needed
    if model not in state["models"]:
        state["models"][model] = {
            "error_count": 0,
            "consecutive_errors": 0,
            "last_error": None,
            "last_error_type": None,
            "cooldown_until": None,
            "errors": []
        }

    model_state = state["models"][model]

    # Update error counts
    model_state["error_count"] += 1
    model_state["consecutive_errors"] += 1
    model_state["last_error"] = now.isoformat()
    model_state["last_error_type"] = error_type

    # Keep last 10 errors for debugging
    model_state["errors"].append({
        "type": error_type,
        "message": error_message[:200] if error_message else "",
        "timestamp": now.isoformat(),
        "task_id": task_id
    })
    model_state["errors"] = model_state["errors"][-10:]

    # Calculate cooldown based on error type and consecutive errors
    config = DEFAULT_RESILIENCE_CONFIG["cooldown"]
    consecutive = model_state["consecutive_errors"]

    if error_type == "rate_limit":
        # Exponential backoff: 1m, 5m, 25m, capped at max
        backoff_idx = min(consecutive - 1, len(DEFAULT_RESILIENCE_CONFIG["retry"]["backoff_seconds"]) - 1)
        cooldown_seconds = DEFAULT_RESILIENCE_CONFIG["retry"]["backoff_seconds"][backoff_idx]
    elif error_type == "billing":
        # Billing errors get longer cooldown
        cooldown_seconds = config["billing_seconds"]
    elif error_type == "overloaded":
        # Overloaded: start at 1m, increase with consecutive errors
        cooldown_seconds = min(60 * consecutive, config["max_cooldown_seconds"])
    elif error_type in ["timeout", "server_error"]:
        # Server issues: moderate backoff
        cooldown_seconds = min(config["error_seconds"] * consecutive, config["max_cooldown_seconds"])
    elif error_type == "auth":
        # Auth errors: don't retry quickly
        cooldown_seconds = config["max_cooldown_seconds"]
    else:
        cooldown_seconds = config["error_seconds"]

    cooldown_until = now.timestamp() + cooldown_seconds
    model_state["cooldown_until"] = datetime.fromtimestamp(cooldown_until).isoformat()

    _save_resilience_state(state)

    return {
        "success": True,
        "model": model,
        "error_type": error_type,
        "consecutive_errors": model_state["consecutive_errors"],
        "cooldown_seconds": cooldown_seconds,
        "cooldown_until": model_state["cooldown_until"],
        "message": f"Model {model} in cooldown for {cooldown_seconds}s due to {error_type}"
    }


def workflow_record_model_success(
    model: str
) -> dict[str, Any]:
    """Record a successful model call, resetting consecutive error count.

    Call this after a successful API response to reset the backoff state.

    Args:
        model: Model identifier

    Returns:
        Updated model state
    """
    state = _load_resilience_state()

    if model not in state["models"]:
        return {
            "success": True,
            "model": model,
            "message": "No error history for this model"
        }

    model_state = state["models"][model]
    model_state["consecutive_errors"] = 0
    model_state["cooldown_until"] = None
    model_state["last_success"] = datetime.now().isoformat()

    _save_resilience_state(state)

    return {
        "success": True,
        "model": model,
        "total_errors": model_state["error_count"],
        "message": f"Reset consecutive errors for {model}"
    }


def workflow_get_available_model(
    preferred_model: Optional[str] = None
) -> dict[str, Any]:
    """Get the next available model considering cooldowns.

    Checks the fallback chain and returns the first model not in cooldown.
    Use this before making API calls to get a working model.

    Args:
        preferred_model: Optional preferred model to try first

    Returns:
        Available model and fallback information
    """
    state = _load_resilience_state()
    now = datetime.now()
    fallback_chain = DEFAULT_RESILIENCE_CONFIG["fallback_chain"]

    # Build ordered list of models to try
    models_to_try = []
    if preferred_model:
        models_to_try.append({"model": preferred_model, "timeout": 120})
    models_to_try.extend(fallback_chain)

    # Remove duplicates while preserving order
    seen = set()
    unique_models = []
    for m in models_to_try:
        if m["model"] not in seen:
            seen.add(m["model"])
            unique_models.append(m)

    available_model = None
    checked_models = []

    for model_config in unique_models:
        model = model_config["model"]
        model_state = state["models"].get(model, {})

        cooldown_until = model_state.get("cooldown_until")
        in_cooldown = False
        remaining_seconds = 0

        if cooldown_until:
            cooldown_time = datetime.fromisoformat(cooldown_until)
            if now < cooldown_time:
                in_cooldown = True
                remaining_seconds = int((cooldown_time - now).total_seconds())

        checked_models.append({
            "model": model,
            "available": not in_cooldown,
            "in_cooldown": in_cooldown,
            "cooldown_remaining_seconds": remaining_seconds if in_cooldown else 0,
            "consecutive_errors": model_state.get("consecutive_errors", 0),
            "last_error_type": model_state.get("last_error_type"),
            "timeout": model_config["timeout"]
        })

        if not in_cooldown and available_model is None:
            available_model = model_config

    if available_model:
        return {
            "available": True,
            "model": available_model["model"],
            "timeout": available_model["timeout"],
            "is_fallback": available_model["model"] != (preferred_model or fallback_chain[0]["model"]),
            "checked_models": checked_models
        }
    else:
        # All models in cooldown - return the one with shortest remaining cooldown
        shortest_cooldown = min(checked_models, key=lambda x: x["cooldown_remaining_seconds"])
        return {
            "available": False,
            "model": None,
            "wait_seconds": shortest_cooldown["cooldown_remaining_seconds"],
            "next_available": shortest_cooldown["model"],
            "message": f"All models in cooldown. {shortest_cooldown['model']} available in {shortest_cooldown['cooldown_remaining_seconds']}s",
            "checked_models": checked_models
        }


def workflow_get_resilience_status() -> dict[str, Any]:
    """Get the current resilience status for all models.

    Returns overview of model health, cooldowns, and error history.
    Useful for debugging and monitoring.

    Returns:
        Complete resilience state
    """
    state = _load_resilience_state()
    now = datetime.now()

    models_status = []
    for model, model_state in state.get("models", {}).items():
        cooldown_until = model_state.get("cooldown_until")
        in_cooldown = False
        remaining_seconds = 0

        if cooldown_until:
            cooldown_time = datetime.fromisoformat(cooldown_until)
            if now < cooldown_time:
                in_cooldown = True
                remaining_seconds = int((cooldown_time - now).total_seconds())

        models_status.append({
            "model": model,
            "total_errors": model_state.get("error_count", 0),
            "consecutive_errors": model_state.get("consecutive_errors", 0),
            "in_cooldown": in_cooldown,
            "cooldown_remaining_seconds": remaining_seconds,
            "last_error_type": model_state.get("last_error_type"),
            "last_error": model_state.get("last_error"),
            "last_success": model_state.get("last_success"),
            "recent_errors": model_state.get("errors", [])[-5:]
        })

    return {
        "models": models_status,
        "fallback_chain": [m["model"] for m in DEFAULT_RESILIENCE_CONFIG["fallback_chain"]],
        "config": DEFAULT_RESILIENCE_CONFIG,
        "updated_at": state.get("updated_at")
    }


def workflow_clear_model_cooldown(
    model: str
) -> dict[str, Any]:
    """Manually clear a model's cooldown state.

    Use when you know a model has recovered or for testing.

    Args:
        model: Model identifier to clear

    Returns:
        Updated model state
    """
    state = _load_resilience_state()

    if model not in state["models"]:
        return {
            "success": True,
            "model": model,
            "message": "No state to clear for this model"
        }

    model_state = state["models"][model]
    model_state["cooldown_until"] = None
    model_state["consecutive_errors"] = 0

    _save_resilience_state(state)

    return {
        "success": True,
        "model": model,
        "message": f"Cleared cooldown for {model}"
    }


# ============================================================================
# Workflow Modes
# ============================================================================

WORKFLOW_MODES = {
    "full": {
        "description": "All 7 agents - complex features, critical changes",
        "phases": ["architect", "developer", "reviewer", "skeptic", "implementer", "feedback", "technical_writer"],
        "estimated_cost": "$0.50+"
    },
    "turbo": {
        "description": "Developer plans comprehensively in one pass - standard features with Opus 4.6",
        "phases": ["developer", "implementer", "technical_writer"],
        "estimated_cost": "$0.15"
    },
    "fast": {
        "description": "Skip Skeptic and Feedback - standard changes",
        "phases": ["architect", "developer", "reviewer", "implementer", "technical_writer"],
        "estimated_cost": "$0.25"
    },
    "minimal": {
        "description": "Developer, Implementer, and Technical Writer - simple fixes, typos",
        "phases": ["developer", "implementer", "technical_writer"],
        "estimated_cost": "$0.10"
    }
}

# Recommended thinking effort levels per mode and agent
EFFORT_LEVELS = {
    "full": {
        "architect": "max",
        "developer": "max",
        "reviewer": "high",
        "skeptic": "max",
        "implementer": "high",
        "feedback": "high",
        "technical_writer": "medium"
    },
    "turbo": {
        "developer": "max",
        "implementer": "high",
        "technical_writer": "medium"
    },
    "fast": {
        "architect": "high",
        "developer": "high",
        "reviewer": "high",
        "implementer": "high",
        "technical_writer": "medium"
    },
    "minimal": {
        "developer": "medium",
        "implementer": "medium",
        "technical_writer": "medium"
    }
}

# Keywords for auto-detection
AUTO_DETECT_RULES = {
    "minimal": {
        "keywords": ["typo", "fix typo", "simple fix", "rename", "update comment", "fix import"],
        "max_files": 1
    },
    "turbo": {
        "keywords": ["add feature", "implement", "update", "refactor", "add", "create", "build", "utility"],
        "exclude_keywords": ["security", "auth", "database", "migration", "api", "breaking",
                           "authentication", "authorization", "password", "token", "critical"]
    },
    "fast": {
        "keywords": ["add feature", "implement", "update", "refactor"],
        "exclude_keywords": ["security", "auth", "database", "migration", "api", "breaking"]
    },
    "full": {
        "keywords": ["security", "authentication", "authorization", "database", "migration",
                    "api", "breaking change", "critical", "auth", "password", "token"]
    }
}


def _resolve_mode(mode_name: str, task_id: Optional[str] = None) -> Optional[dict]:
    """Resolve a workflow mode by name, checking config first then hardcoded defaults.

    This allows projects to define custom modes in their workflow-config.yaml
    under workflow_modes.modes, which take precedence over the hardcoded WORKFLOW_MODES.

    Args:
        mode_name: The mode name to resolve (e.g., "full", "turbo", or a custom name)
        task_id: Optional task ID for config resolution

    Returns:
        Mode config dict with "phases", "description", "estimated_cost", or None if not found
    """
    # Check hardcoded modes first (fast path for standard modes)
    if mode_name in WORKFLOW_MODES:
        return WORKFLOW_MODES[mode_name]

    # Check config for custom modes
    try:
        from .config_tools import config_get_effective
        effective = config_get_effective(task_id=task_id)
        config = effective.get("config", {})
        custom_modes = config.get("workflow_modes", {}).get("modes", {})
        if mode_name in custom_modes:
            return custom_modes[mode_name]
    except Exception:
        pass

    return None


def _get_all_mode_names(task_id: Optional[str] = None) -> list[str]:
    """Get all available mode names (hardcoded + config-defined).

    Args:
        task_id: Optional task ID for config resolution

    Returns:
        List of all known mode names
    """
    modes = list(WORKFLOW_MODES.keys())
    try:
        from .config_tools import config_get_effective
        effective = config_get_effective(task_id=task_id)
        config = effective.get("config", {})
        custom_modes = config.get("workflow_modes", {}).get("modes", {})
        for name in custom_modes:
            if name not in modes:
                modes.append(name)
    except Exception:
        pass
    return modes


def workflow_detect_mode(
    task_description: str,
    files_affected: Optional[list[str]] = None
) -> dict[str, Any]:
    """Auto-detect the appropriate workflow mode based on task description.

    Analyzes the task description and affected files to determine
    whether to use full, fast, or minimal workflow mode.

    Args:
        task_description: Description of the task
        files_affected: Optional list of files that will be affected

    Returns:
        Detected mode with reasoning
    """
    desc_lower = task_description.lower()
    file_count = len(files_affected) if files_affected else 0

    # Check for full mode triggers first (highest priority)
    full_matches = []
    for keyword in AUTO_DETECT_RULES["full"]["keywords"]:
        if keyword in desc_lower:
            full_matches.append(keyword)

    if full_matches:
        return {
            "mode": "full",
            "reason": f"Task mentions critical keywords: {', '.join(full_matches)}",
            "confidence": 0.9,
            "matched_keywords": full_matches
        }

    # Check for minimal mode
    minimal_matches = []
    for keyword in AUTO_DETECT_RULES["minimal"]["keywords"]:
        if keyword in desc_lower:
            minimal_matches.append(keyword)

    if minimal_matches and file_count <= AUTO_DETECT_RULES["minimal"]["max_files"]:
        return {
            "mode": "minimal",
            "reason": f"Simple task ({', '.join(minimal_matches)}) affecting {file_count} files",
            "confidence": 0.8,
            "matched_keywords": minimal_matches
        }

    # Check for turbo mode (Opus 4.6 single-pass planning)
    turbo_excluded = False
    for exclude_keyword in AUTO_DETECT_RULES["turbo"]["exclude_keywords"]:
        if exclude_keyword in desc_lower:
            turbo_excluded = True
            break

    if not turbo_excluded:
        turbo_matches = []
        for keyword in AUTO_DETECT_RULES["turbo"]["keywords"]:
            if keyword in desc_lower:
                turbo_matches.append(keyword)

        if turbo_matches:
            return {
                "mode": "turbo",
                "reason": f"Standard feature task ({', '.join(turbo_matches)}) suitable for single-pass Opus 4.6 planning",
                "confidence": 0.75,
                "matched_keywords": turbo_matches
            }

    # Check for fast mode exclusions
    fast_excluded = False
    for exclude_keyword in AUTO_DETECT_RULES["fast"]["exclude_keywords"]:
        if exclude_keyword in desc_lower:
            fast_excluded = True
            break

    if not fast_excluded:
        # Check for fast mode triggers
        fast_matches = []
        for keyword in AUTO_DETECT_RULES["fast"]["keywords"]:
            if keyword in desc_lower:
                fast_matches.append(keyword)

        if fast_matches:
            return {
                "mode": "fast",
                "reason": f"Standard task ({', '.join(fast_matches)}) without critical patterns",
                "confidence": 0.7,
                "matched_keywords": fast_matches
            }

    # Default to full for safety
    return {
        "mode": "full",
        "reason": "No specific pattern detected, defaulting to full mode for safety",
        "confidence": 0.5,
        "matched_keywords": []
    }


def workflow_set_mode(
    mode: str,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Set the workflow mode for a task.

    Supports both built-in modes (full, turbo, fast, minimal) and custom modes
    defined in workflow-config.yaml under workflow_modes.modes.

    Args:
        mode: Workflow mode name (built-in or custom) or "auto" for auto-detection
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Updated task state with mode configuration
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    resolved_task_id = state.get("task_id")

    if mode == "auto":
        # Auto-detect based on task description
        description = state.get("description", "")
        detection = workflow_detect_mode(description)
        effective_mode = detection["mode"]
        state["workflow_mode"] = {
            "requested": "auto",
            "effective": effective_mode,
            "detection_reason": detection["reason"],
            "confidence": detection["confidence"]
        }
    else:
        # Resolve mode from hardcoded defaults + config custom modes
        resolved = _resolve_mode(mode, task_id=resolved_task_id)
        if resolved is None:
            available = _get_all_mode_names(task_id=resolved_task_id)
            return {
                "success": False,
                "error": f"Invalid mode '{mode}'. Available modes: {', '.join(available + ['auto'])}"
            }
        state["workflow_mode"] = {
            "requested": mode,
            "effective": mode,
            "detection_reason": "Explicitly set by user",
            "confidence": 1.0
        }

    # Update required phases based on mode
    effective_mode = state["workflow_mode"]["effective"]
    mode_config = _resolve_mode(effective_mode, task_id=resolved_task_id)
    if mode_config is None:
        mode_config = WORKFLOW_MODES["full"]
    state["workflow_mode"]["phases"] = mode_config["phases"]
    state["workflow_mode"]["estimated_cost"] = mode_config.get("estimated_cost", "unknown")

    _save_state(task_dir, state)

    return {
        "success": True,
        "task_id": resolved_task_id,
        "workflow_mode": state["workflow_mode"],
        "message": f"Workflow mode set to {effective_mode}"
    }


def workflow_get_mode(
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Get the current workflow mode for a task.

    Args:
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Current mode configuration
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    mode = state.get("workflow_mode", {
        "requested": "full",
        "effective": "full",
        "phases": WORKFLOW_MODES["full"]["phases"],
        "estimated_cost": WORKFLOW_MODES["full"]["estimated_cost"]
    })

    return {
        "task_id": state.get("task_id"),
        "workflow_mode": mode,
        "available_modes": _get_all_mode_names(task_id=state.get("task_id"))
    }


def workflow_is_phase_in_mode(
    phase: str,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Check if a phase is included in the current workflow mode.

    Args:
        phase: Phase name to check
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Whether the phase is included
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "in_mode": True,  # Default to allowing if no task
            "error": "No active task found, assuming full mode"
        }

    state = _load_state(task_dir)
    mode = state.get("workflow_mode", {})
    phases = mode.get("phases", WORKFLOW_MODES["full"]["phases"])

    return {
        "phase": phase,
        "in_mode": phase in phases,
        "effective_mode": mode.get("effective", "full"),
        "task_id": state.get("task_id")
    }


def workflow_get_effort_level(
    agent: str,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Get the recommended thinking effort level for an agent in the current mode.

    Maps workflow modes to per-agent effort levels (low/medium/high/max)
    for use with Claude's extended thinking effort parameter.

    Args:
        agent: Agent name (architect, developer, reviewer, etc.)
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Recommended effort level and mode context
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "effort": "high",
            "mode": "full",
            "reason": "No active task found, using default effort level"
        }

    state = _load_state(task_dir)
    mode = state.get("workflow_mode", {}).get("effective", "full")
    mode_efforts = EFFORT_LEVELS.get(mode, EFFORT_LEVELS["full"])
    effort = mode_efforts.get(agent, "high")

    return {
        "effort": effort,
        "agent": agent,
        "mode": mode,
        "task_id": state.get("task_id")
    }


# ============================================================================
# Agent Teams (experimental)
# ============================================================================

AGENT_TEAM_FEATURES = ["parallel_review", "parallel_implementation"]


def workflow_get_agent_team_config(
    feature: str,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Get agent team configuration for a specific feature.

    Reads agent_teams config via config cascade and returns whether the
    feature is enabled along with its settings.

    Args:
        feature: Feature name (parallel_review, parallel_implementation)
        task_id: Task identifier for config cascade resolution.

    Returns:
        Feature enabled status and settings
    """
    if feature not in AGENT_TEAM_FEATURES:
        return {
            "enabled": False,
            "error": f"Unknown agent team feature '{feature}'. Must be one of: {', '.join(AGENT_TEAM_FEATURES)}"
        }

    from .config_tools import config_get_effective

    effective = config_get_effective(task_id=task_id)
    config = effective.get("config", {})
    agent_teams = config.get("agent_teams", {})

    if not agent_teams.get("enabled", False):
        return {
            "enabled": False,
            "feature": feature,
            "reason": "agent_teams.enabled is false"
        }

    feature_config = agent_teams.get(feature, {})

    return {
        "enabled": feature_config.get("enabled", False),
        "feature": feature,
        "settings": feature_config,
        "task_id": task_id
    }


# ============================================================================
# Cost Tracking
# ============================================================================

# Model costs per million tokens (from config, but defaults here)
MODEL_COSTS = {
    "opus": {"input": 5.00, "output": 25.00},
    "opus_long_context": {"input": 10.00, "output": 37.50},
    "sonnet": {"input": 3.00, "output": 15.00},
    "haiku": {"input": 0.80, "output": 4.00}
}


def workflow_record_cost(
    agent: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_seconds: float = 0,
    compaction_tokens: int = 0,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Record token usage and cost for an agent run.

    Args:
        agent: Agent name (architect, developer, etc.)
        model: Model used (opus, sonnet, haiku)
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        duration_seconds: Time taken for the run
        compaction_tokens: Tokens used by compaction iterations
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Recorded cost entry with calculated cost
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    # Calculate cost (use long-context pricing for opus with >200K input tokens)
    model_lower = model.lower()
    if model_lower == "opus" and input_tokens > 200_000:
        costs = MODEL_COSTS["opus_long_context"]
    else:
        costs = MODEL_COSTS.get(model_lower, MODEL_COSTS["opus"])
    input_cost = (input_tokens / 1_000_000) * costs["input"]
    output_cost = (output_tokens / 1_000_000) * costs["output"]
    total_cost = input_cost + output_cost

    compaction_cost = 0
    if compaction_tokens > 0:
        compaction_cost = (compaction_tokens / 1_000_000) * MODEL_COSTS["haiku"]["output"]
        total_cost += compaction_cost

    # Initialize cost tracking if needed
    if "cost_tracking" not in state:
        state["cost_tracking"] = {
            "entries": [],
            "totals": {
                "input_tokens": 0,
                "output_tokens": 0,
                "compaction_tokens": 0,
                "total_cost": 0,
                "duration_seconds": 0
            },
            "by_agent": {},
            "by_model": {}
        }

    # Create entry
    entry = {
        "agent": agent,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "compaction_tokens": compaction_tokens,
        "input_cost": round(input_cost, 4),
        "output_cost": round(output_cost, 4),
        "compaction_cost": round(compaction_cost, 4),
        "total_cost": round(total_cost, 4),
        "duration_seconds": duration_seconds,
        "timestamp": datetime.now().isoformat()
    }

    # Update state
    state["cost_tracking"]["entries"].append(entry)
    state["cost_tracking"]["totals"]["input_tokens"] += input_tokens
    state["cost_tracking"]["totals"]["output_tokens"] += output_tokens
    state["cost_tracking"]["totals"]["compaction_tokens"] += compaction_tokens
    state["cost_tracking"]["totals"]["total_cost"] += total_cost
    state["cost_tracking"]["totals"]["duration_seconds"] += duration_seconds

    # Update by-agent totals
    if agent not in state["cost_tracking"]["by_agent"]:
        state["cost_tracking"]["by_agent"][agent] = {
            "input_tokens": 0, "output_tokens": 0, "total_cost": 0, "runs": 0
        }
    state["cost_tracking"]["by_agent"][agent]["input_tokens"] += input_tokens
    state["cost_tracking"]["by_agent"][agent]["output_tokens"] += output_tokens
    state["cost_tracking"]["by_agent"][agent]["total_cost"] += total_cost
    state["cost_tracking"]["by_agent"][agent]["runs"] += 1

    # Update by-model totals
    if model not in state["cost_tracking"]["by_model"]:
        state["cost_tracking"]["by_model"][model] = {
            "input_tokens": 0, "output_tokens": 0, "total_cost": 0, "runs": 0
        }
    state["cost_tracking"]["by_model"][model]["input_tokens"] += input_tokens
    state["cost_tracking"]["by_model"][model]["output_tokens"] += output_tokens
    state["cost_tracking"]["by_model"][model]["total_cost"] += total_cost
    state["cost_tracking"]["by_model"][model]["runs"] += 1

    _save_state(task_dir, state)

    return {
        "success": True,
        "entry": entry,
        "running_total": round(state["cost_tracking"]["totals"]["total_cost"], 4),
        "task_id": state.get("task_id")
    }


def workflow_get_cost_summary(
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Get cost summary for a workflow task.

    Args:
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Comprehensive cost summary with breakdowns
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    cost_tracking = state.get("cost_tracking", {
        "entries": [],
        "totals": {"input_tokens": 0, "output_tokens": 0, "total_cost": 0, "duration_seconds": 0},
        "by_agent": {},
        "by_model": {}
    })

    # Calculate mode comparison if we have mode info
    mode = state.get("workflow_mode", {}).get("effective", "full")
    full_mode_estimate = cost_tracking["totals"]["total_cost"]  # Current cost is the baseline

    # Generate formatted summary
    summary_lines = []
    summary_lines.append(f"Cost Summary for {state.get('task_id', 'unknown')}")
    summary_lines.append(f"Mode: {mode}")
    summary_lines.append("")
    summary_lines.append("By Agent:")

    for agent, data in sorted(cost_tracking.get("by_agent", {}).items()):
        tokens = data["input_tokens"] + data["output_tokens"]
        cost = data["total_cost"]
        summary_lines.append(f"  {agent}: {tokens:,} tokens  ${cost:.4f}")

    summary_lines.append("")
    summary_lines.append(f"Total Tokens: {cost_tracking['totals']['input_tokens'] + cost_tracking['totals']['output_tokens']:,}")
    summary_lines.append(f"Total Cost: ${cost_tracking['totals']['total_cost']:.4f}")
    summary_lines.append(f"Duration: {cost_tracking['totals']['duration_seconds']:.1f}s")

    return {
        "task_id": state.get("task_id"),
        "mode": mode,
        "totals": cost_tracking["totals"],
        "by_agent": cost_tracking.get("by_agent", {}),
        "by_model": cost_tracking.get("by_model", {}),
        "entries_count": len(cost_tracking.get("entries", [])),
        "formatted_summary": "\n".join(summary_lines)
    }


# ============================================================================
# Parallelization Support
# ============================================================================

def workflow_start_parallel_phase(
    phases: list[str],
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Start parallel execution of multiple phases.

    Used for running Reviewer and Skeptic in parallel.

    Args:
        phases: List of phase names to run in parallel
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Parallel phase tracking info
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    # Initialize parallel tracking
    state["parallel_execution"] = {
        "active": True,
        "phases": phases,
        "started_at": datetime.now().isoformat(),
        "completed_phases": [],
        "results": {}
    }

    _save_state(task_dir, state)

    return {
        "success": True,
        "task_id": state.get("task_id"),
        "parallel_phases": phases,
        "message": f"Started parallel execution of: {', '.join(phases)}"
    }


def workflow_complete_parallel_phase(
    phase: str,
    result_summary: str = "",
    concerns: Optional[list[dict]] = None,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Mark a parallel phase as complete and store its results.

    Args:
        phase: Phase name that completed
        result_summary: Summary of the phase's output
        concerns: List of concerns raised by this phase
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Updated parallel execution state
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    if "parallel_execution" not in state or not state["parallel_execution"].get("active"):
        return {
            "success": False,
            "error": "No active parallel execution"
        }

    parallel = state["parallel_execution"]

    if phase not in parallel["phases"]:
        return {
            "success": False,
            "error": f"Phase {phase} is not part of current parallel execution"
        }

    # Store results
    parallel["results"][phase] = {
        "completed_at": datetime.now().isoformat(),
        "summary": result_summary,
        "concerns": concerns or []
    }

    if phase not in parallel["completed_phases"]:
        parallel["completed_phases"].append(phase)

    # Check if all parallel phases are complete
    all_complete = all(p in parallel["completed_phases"] for p in parallel["phases"])

    if all_complete:
        parallel["active"] = False
        parallel["completed_at"] = datetime.now().isoformat()

    _save_state(task_dir, state)

    return {
        "success": True,
        "task_id": state.get("task_id"),
        "phase": phase,
        "all_complete": all_complete,
        "remaining": [p for p in parallel["phases"] if p not in parallel["completed_phases"]]
    }


def workflow_merge_parallel_results(
    task_id: Optional[str] = None,
    merge_strategy: str = "deduplicate"
) -> dict[str, Any]:
    """Merge results from parallel phase execution.

    Combines concerns from multiple phases, optionally deduplicating.

    Args:
        task_id: Task identifier. If not provided, uses active task.
        merge_strategy: How to merge (deduplicate, combine, prioritize_first)

    Returns:
        Merged results with deduplicated concerns
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    if "parallel_execution" not in state:
        return {
            "success": False,
            "error": "No parallel execution results to merge"
        }

    parallel = state["parallel_execution"]
    results = parallel.get("results", {})

    # Collect all concerns
    all_concerns = []
    for phase, phase_result in results.items():
        for concern in phase_result.get("concerns", []):
            concern["source_phase"] = phase
            all_concerns.append(concern)

    # Apply merge strategy
    if merge_strategy == "deduplicate":
        # Simple deduplication based on description similarity
        seen_descriptions = set()
        merged_concerns = []
        for concern in all_concerns:
            desc_key = concern.get("description", "").lower()[:100]
            if desc_key not in seen_descriptions:
                seen_descriptions.add(desc_key)
                merged_concerns.append(concern)
    elif merge_strategy == "combine":
        merged_concerns = all_concerns
    else:
        merged_concerns = all_concerns

    # Store merged results
    state["parallel_execution"]["merged_concerns"] = merged_concerns
    state["parallel_execution"]["merge_strategy"] = merge_strategy
    state["parallel_execution"]["merged_at"] = datetime.now().isoformat()

    _save_state(task_dir, state)

    return {
        "success": True,
        "task_id": state.get("task_id"),
        "original_count": len(all_concerns),
        "merged_count": len(merged_concerns),
        "merge_strategy": merge_strategy,
        "merged_concerns": merged_concerns
    }


# ============================================================================
# Structured Assertions
# ============================================================================

ASSERTION_TYPES = [
    "file_exists",
    "test_passes",
    "no_pattern",
    "contains_pattern",
    "type_check_passes",
    "lint_passes"
]


def workflow_add_assertion(
    assertion_type: str,
    definition: dict[str, Any],
    step_id: Optional[str] = None,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Add an assertion to the workflow for verification.

    Args:
        assertion_type: Type of assertion (file_exists, test_passes, etc.)
        definition: Assertion definition (varies by type)
        step_id: Optional step this assertion is tied to
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Created assertion with ID
    """
    if assertion_type not in ASSERTION_TYPES:
        return {
            "success": False,
            "error": f"Invalid assertion type '{assertion_type}'. Must be one of: {', '.join(ASSERTION_TYPES)}"
        }

    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    if "assertions" not in state:
        state["assertions"] = []

    # Generate assertion ID
    assertion_id = f"A{len(state['assertions']) + 1:03d}"

    assertion = {
        "id": assertion_id,
        "type": assertion_type,
        "definition": definition,
        "step_id": step_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "verified_at": None,
        "result": None
    }

    state["assertions"].append(assertion)
    _save_state(task_dir, state)

    return {
        "success": True,
        "assertion": assertion,
        "task_id": state.get("task_id")
    }


def workflow_verify_assertion(
    assertion_id: str,
    result: bool,
    message: str = "",
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Record the verification result of an assertion.

    Args:
        assertion_id: ID of the assertion to verify
        result: Whether the assertion passed
        message: Optional message about the result
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Updated assertion
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    if "assertions" not in state:
        return {
            "success": False,
            "error": "No assertions found"
        }

    for assertion in state["assertions"]:
        if assertion["id"] == assertion_id:
            assertion["status"] = "passed" if result else "failed"
            assertion["verified_at"] = datetime.now().isoformat()
            assertion["result"] = {
                "passed": result,
                "message": message
            }
            _save_state(task_dir, state)
            return {
                "success": True,
                "assertion": assertion,
                "task_id": state.get("task_id")
            }

    return {
        "success": False,
        "error": f"Assertion {assertion_id} not found"
    }


def workflow_get_assertions(
    step_id: Optional[str] = None,
    status: Optional[str] = None,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Get assertions, optionally filtered by step or status.

    Args:
        step_id: Filter by step ID
        status: Filter by status (pending, passed, failed)
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        List of matching assertions
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    assertions = state.get("assertions", [])

    # Filter
    if step_id:
        assertions = [a for a in assertions if a.get("step_id") == step_id]
    if status:
        assertions = [a for a in assertions if a.get("status") == status]

    # Summary counts
    total = len(state.get("assertions", []))
    pending = len([a for a in state.get("assertions", []) if a.get("status") == "pending"])
    passed = len([a for a in state.get("assertions", []) if a.get("status") == "passed"])
    failed = len([a for a in state.get("assertions", []) if a.get("status") == "failed"])

    return {
        "assertions": assertions,
        "count": len(assertions),
        "summary": {
            "total": total,
            "pending": pending,
            "passed": passed,
            "failed": failed
        },
        "task_id": state.get("task_id")
    }


# ============================================================================
# Error Pattern Learning
# ============================================================================

def _get_error_patterns_file() -> Path:
    """Get the path to the error patterns file."""
    tasks_dir = get_tasks_dir()
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return tasks_dir / ".error_patterns.jsonl"


def workflow_record_error_pattern(
    error_signature: str,
    error_type: str,
    solution: str,
    tags: Optional[list[str]] = None,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Record an error pattern and its solution for future matching.

    Args:
        error_signature: Unique identifying part of the error
        error_type: Type of error (compile, runtime, test, etc.)
        solution: Description of how to fix this error
        tags: Optional tags for categorization
        task_id: Optional task where this was discovered

    Returns:
        Recorded pattern
    """
    patterns_file = _get_error_patterns_file()

    pattern = {
        "signature": error_signature,
        "type": error_type,
        "solution": solution,
        "tags": tags or [],
        "times_seen": 1,
        "last_task": task_id,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    # Check if pattern already exists
    existing_patterns = []
    if patterns_file.exists():
        with open(patterns_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing_patterns.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    # Check for existing similar pattern
    for existing in existing_patterns:
        if existing.get("signature") == error_signature:
            existing["times_seen"] = existing.get("times_seen", 1) + 1
            existing["last_task"] = task_id
            existing["updated_at"] = datetime.now().isoformat()
            # Merge tags
            existing_tags = set(existing.get("tags", []))
            existing_tags.update(tags or [])
            existing["tags"] = list(existing_tags)

            # Rewrite file
            with open(patterns_file, "w") as f:
                for p in existing_patterns:
                    f.write(json.dumps(p) + "\n")

            return {
                "success": True,
                "pattern": existing,
                "action": "updated",
                "message": f"Updated existing pattern (seen {existing['times_seen']} times)"
            }

    # Add new pattern
    with open(patterns_file, "a") as f:
        f.write(json.dumps(pattern) + "\n")

    return {
        "success": True,
        "pattern": pattern,
        "action": "created",
        "message": "Recorded new error pattern"
    }


def workflow_match_error(
    error_output: str,
    min_confidence: float = 0.5
) -> dict[str, Any]:
    """Match an error output against known patterns.

    Args:
        error_output: The error output to match
        min_confidence: Minimum confidence threshold (0-1)

    Returns:
        Matching patterns with solutions, sorted by relevance
    """
    patterns_file = _get_error_patterns_file()

    if not patterns_file.exists():
        return {
            "matches": [],
            "count": 0,
            "message": "No error patterns recorded yet"
        }

    patterns = []
    with open(patterns_file, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    patterns.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    error_lower = error_output.lower()
    matches = []

    for pattern in patterns:
        signature = pattern.get("signature", "").lower()
        if not signature:
            continue

        # Simple substring matching with confidence based on match quality
        if signature in error_lower:
            # Higher confidence for longer, more specific matches
            confidence = min(1.0, len(signature) / 50 + 0.5)
            # Boost for frequently seen patterns
            times_seen = pattern.get("times_seen", 1)
            if times_seen > 3:
                confidence = min(1.0, confidence + 0.1)

            if confidence >= min_confidence:
                matches.append({
                    "pattern": pattern,
                    "confidence": round(confidence, 2),
                    "solution": pattern.get("solution"),
                    "times_seen": times_seen
                })

    # Sort by confidence
    matches.sort(key=lambda x: (-x["confidence"], -x["times_seen"]))

    return {
        "matches": matches[:5],  # Top 5 matches
        "count": len(matches),
        "total_patterns": len(patterns)
    }


# ============================================================================
# Agent Performance Tracking
# ============================================================================

def workflow_record_concern_outcome(
    concern_id: str,
    outcome: str,
    notes: str = "",
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Record the outcome of a concern (was it valid or false positive).

    Args:
        concern_id: ID of the concern
        outcome: Outcome (valid, false_positive, partially_valid)
        notes: Optional notes about the outcome
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Updated concern with outcome
    """
    valid_outcomes = ["valid", "false_positive", "partially_valid"]
    if outcome not in valid_outcomes:
        return {
            "success": False,
            "error": f"Invalid outcome '{outcome}'. Must be one of: {', '.join(valid_outcomes)}"
        }

    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    if "concerns" not in state:
        return {
            "success": False,
            "error": "No concerns found"
        }

    for concern in state["concerns"]:
        if concern["id"] == concern_id:
            concern["outcome"] = {
                "status": outcome,
                "notes": notes,
                "recorded_at": datetime.now().isoformat()
            }
            _save_state(task_dir, state)

            # Also record to global performance tracking
            _record_agent_performance(
                agent=concern.get("source", "unknown"),
                concern_type=concern.get("severity", "unknown"),
                outcome=outcome
            )

            return {
                "success": True,
                "concern": concern,
                "task_id": state.get("task_id")
            }

    return {
        "success": False,
        "error": f"Concern {concern_id} not found"
    }


def _get_performance_file() -> Path:
    """Get the path to the agent performance file."""
    tasks_dir = get_tasks_dir()
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return tasks_dir / ".agent_performance.jsonl"


def _record_agent_performance(agent: str, concern_type: str, outcome: str) -> None:
    """Record a performance data point for an agent."""
    performance_file = _get_performance_file()

    entry = {
        "agent": agent,
        "concern_type": concern_type,
        "outcome": outcome,
        "timestamp": datetime.now().isoformat()
    }

    with open(performance_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def workflow_get_agent_performance(
    agent: Optional[str] = None,
    time_range_days: int = 30
) -> dict[str, Any]:
    """Get performance statistics for agents.

    Args:
        agent: Optional specific agent to get stats for
        time_range_days: Number of days to look back

    Returns:
        Performance statistics with precision metrics
    """
    performance_file = _get_performance_file()

    if not performance_file.exists():
        return {
            "agents": {},
            "total_concerns": 0,
            "message": "No performance data recorded yet"
        }

    # Load and filter by time range
    cutoff = datetime.now().timestamp() - (time_range_days * 24 * 60 * 60)
    entries = []

    with open(performance_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry_time = datetime.fromisoformat(entry.get("timestamp", "")).timestamp()
                if entry_time >= cutoff:
                    if agent is None or entry.get("agent") == agent:
                        entries.append(entry)
            except (json.JSONDecodeError, ValueError):
                continue

    # Calculate statistics by agent
    agent_stats = {}
    for entry in entries:
        agent_name = entry.get("agent", "unknown")
        if agent_name not in agent_stats:
            agent_stats[agent_name] = {
                "total": 0,
                "valid": 0,
                "false_positive": 0,
                "partially_valid": 0,
                "by_type": {}
            }

        stats = agent_stats[agent_name]
        stats["total"] += 1

        outcome = entry.get("outcome", "unknown")
        if outcome == "valid":
            stats["valid"] += 1
        elif outcome == "false_positive":
            stats["false_positive"] += 1
        elif outcome == "partially_valid":
            stats["partially_valid"] += 1

        # Track by concern type
        concern_type = entry.get("concern_type", "unknown")
        if concern_type not in stats["by_type"]:
            stats["by_type"][concern_type] = {"total": 0, "valid": 0}
        stats["by_type"][concern_type]["total"] += 1
        if outcome in ["valid", "partially_valid"]:
            stats["by_type"][concern_type]["valid"] += 1

    # Calculate precision for each agent
    for agent_name, stats in agent_stats.items():
        if stats["total"] > 0:
            stats["precision"] = round(
                (stats["valid"] + stats["partially_valid"] * 0.5) / stats["total"],
                2
            )
        else:
            stats["precision"] = 0

    return {
        "agents": agent_stats,
        "total_concerns": len(entries),
        "time_range_days": time_range_days,
        "message": f"Performance data for last {time_range_days} days"
    }


# ============================================================================
# Optional Phase Management
# ============================================================================

def workflow_enable_optional_phase(
    phase: str,
    reason: str = "",
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Enable an optional phase for the current workflow.

    Used to dynamically add specialized agents like security_auditor.

    Args:
        phase: Phase to enable
        reason: Why this phase is being enabled
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Updated workflow mode
    """
    optional_phases = ["security_auditor", "performance_analyst", "api_guardian", "accessibility_reviewer"]

    if phase not in optional_phases:
        return {
            "success": False,
            "error": f"Unknown optional phase '{phase}'. Available: {', '.join(optional_phases)}"
        }

    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    # Initialize optional phases if needed
    if "optional_phases" not in state:
        state["optional_phases"] = []

    if phase not in state["optional_phases"]:
        state["optional_phases"].append(phase)

    # Track why it was enabled
    if "optional_phase_reasons" not in state:
        state["optional_phase_reasons"] = {}
    state["optional_phase_reasons"][phase] = {
        "reason": reason,
        "enabled_at": datetime.now().isoformat()
    }

    _save_state(task_dir, state)

    return {
        "success": True,
        "task_id": state.get("task_id"),
        "optional_phases": state["optional_phases"],
        "message": f"Enabled optional phase: {phase}"
    }


def workflow_get_optional_phases(
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Get enabled optional phases for a workflow.

    Args:
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        List of enabled optional phases with reasons
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    return {
        "task_id": state.get("task_id"),
        "optional_phases": state.get("optional_phases", []),
        "reasons": state.get("optional_phase_reasons", {})
    }


# ============================================================================
# Git Worktree Support
# ============================================================================

def _is_wsl() -> bool:
    """Detect if running inside WSL."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except (FileNotFoundError, PermissionError):
        return False


def _slugify(text: str) -> str:
    """Convert text to git-branch-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s_-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def _find_recyclable_worktree() -> Optional[tuple[Path, dict]]:
    """Scan tasks for a worktree with status 'recyclable' whose directory still exists.

    Returns:
        Tuple of (task_dir, state) for the recyclable donor, or None if not found.
    """
    tasks_dir = get_tasks_dir()
    if not tasks_dir.exists():
        return None

    for task_dir in sorted(tasks_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        state_file = task_dir / "state.json"
        if not state_file.exists():
            continue
        state = _load_state(task_dir)
        worktree = state.get("worktree")
        if not worktree or worktree.get("status") != "recyclable":
            continue
        # Check that the directory still exists on disk
        wt_path = worktree.get("path")
        if not wt_path:
            continue
        # Resolve relative to main repo
        abs_path = os.path.normpath(os.path.join(str(Path.cwd()), wt_path))
        if os.path.isdir(abs_path):
            return (task_dir, state)

    return None


def _generate_branch_name(task_id: str, state: dict) -> str:
    """Generate unique branch name from beads/jira ticket or task description."""
    # Priority 1: linked issue
    linked = state.get("linked_issue") or state.get("beads_issue")
    if linked:
        return f"crew/{_slugify(linked)}"
    # Priority 2: description
    desc = state.get("description", "")
    if desc:
        slug = _slugify(desc)[:50].rstrip("-")
        if slug:
            return f"crew/{slug}"
    # Fallback
    return f"crew/{task_id.lower().replace('_', '-')}"


def workflow_create_worktree(
    task_id: Optional[str] = None,
    base_path: Optional[str] = None,
    base_branch: str = "main",
    ai_host: str = "claude",
    branch_name: Optional[str] = None,
    recycle: bool = False
) -> dict[str, Any]:
    """Record worktree metadata in state and return git commands for the orchestrator.

    The MCP server does NOT execute git commands — it records metadata and returns
    the commands for the orchestrator to run.

    Args:
        task_id: Task identifier. If not provided, uses active task.
        base_path: Directory for worktrees. Defaults to ../REPO-worktrees/.
        base_branch: Branch to base the worktree on.
        ai_host: AI host CLI (determines which settings to copy). Default: claude.
        branch_name: Explicit branch name. If not provided, derives from
            linked issue, task description, or task ID.
        recycle: If True, attempt to reuse a recyclable worktree directory
            instead of creating a fresh one. Falls back to normal creation
            if no recyclable worktree is available.

    Returns:
        Worktree metadata, git commands, and setup commands to execute.
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    resolved_task_id = state.get("task_id", task_dir.name)

    if state.get("worktree") and state["worktree"].get("status") == "active":
        return {
            "success": False,
            "error": f"Worktree already exists for {resolved_task_id}",
            "worktree": state["worktree"]
        }

    # Determine repo name from cwd
    repo_name = Path.cwd().name

    # WSL + /mnt/ detection for performance warnings and native commands
    wsl = _is_wsl()
    warnings: list[str] = []
    wsl_use_native_commands = False

    if wsl and not base_path:
        # Check for wsl_native_path config override
        from agentic_workflow_server.config_tools import config_get_effective
        effective = config_get_effective(task_id=resolved_task_id)
        wsl_native_path = effective["config"].get("worktree", {}).get("wsl_native_path", "")
        if wsl_native_path:
            # Substitute placeholders
            wsl_native_path = wsl_native_path.replace("{user}", os.getenv("USER", ""))
            wsl_native_path = wsl_native_path.replace("{repo_name}", repo_name)
            base_path = wsl_native_path

    if not base_path:
        base_path = f"../{repo_name}-worktrees"

    if not branch_name:
        branch_name = _generate_branch_name(resolved_task_id, state)
    worktree_path = f"{base_path}/{resolved_task_id}"

    # Resolve absolute path to check if it's on /mnt/ (NTFS via 9P)
    resolved_abs = os.path.normpath(os.path.join(str(Path.cwd().resolve()), worktree_path))
    if wsl and resolved_abs.startswith("/mnt/"):
        wsl_use_native_commands = True
        warnings.append(
            "WSL performance warning: Worktree is on /mnt/ (NTFS via 9P bridge). "
            "Git and dependency commands will run via PowerShell (native Windows) to bypass 9P. "
            "To avoid this, set worktree.wsl_native_path to a /home/ path "
            "(e.g., '/home/{user}/{repo_name}-worktrees')."
        )

    # Assign a color scheme based on the numeric portion of the task ID
    task_num_match = re.search(r'\d+', resolved_task_id)
    task_num = int(task_num_match.group()) if task_num_match else 0
    color_scheme_index = task_num % len(CREW_COLOR_SCHEMES)

    # Try recycling an existing worktree
    donor = None
    if recycle:
        donor = _find_recyclable_worktree()

    if donor:
        donor_dir, donor_state = donor
        donor_worktree = donor_state["worktree"]
        donor_path = donor_worktree["path"]
        donor_branch = donor_worktree["branch"]
        donor_task_id = donor_state.get("task_id", donor_dir.name)

        worktree_metadata = {
            "status": "active",
            "path": worktree_path,
            "branch": branch_name,
            "base_branch": base_branch,
            "color_scheme_index": color_scheme_index,
            "created_at": datetime.now().isoformat(),
            "recycled_from": donor_task_id,
        }

        state["worktree"] = worktree_metadata
        _save_state(task_dir, state)

        # Mark donor as recycled
        donor_state["worktree"]["status"] = "recycled"
        donor_state["worktree"]["recycled_to"] = resolved_task_id
        donor_state["worktree"]["recycled_at"] = datetime.now().isoformat()
        _save_state(donor_dir, donor_state)

        # Git commands: move worktree dir, switch to base branch, create new branch, delete old
        git_commands = [
            f"git worktree move {donor_path} {worktree_path}",
            f"git -C {worktree_path} checkout {base_branch}",
            f"git -C {worktree_path} checkout -b {branch_name}",
            f"git branch -d {donor_branch}",
        ]

        # Build setup commands (symlink .tasks/ + copy host settings)
        main_repo_abs = str(Path.cwd().resolve())
        worktree_abs = os.path.normpath(os.path.join(main_repo_abs, worktree_path))

        setup_commands = [
            f"ln -sfn {shlex.quote(os.path.join(main_repo_abs, '.tasks'))} {shlex.quote(os.path.join(worktree_abs, '.tasks'))}"
        ]

        main_tasks_abs = os.path.join(main_repo_abs, ".tasks")

        # Locate permissions template
        perms_tpl = ""
        for candidate in [
            os.path.join(main_repo_abs, "config", "worktree-permissions.json"),
            os.path.expanduser("~/.claude/config/worktree-permissions.json"),
        ]:
            if os.path.isfile(candidate):
                perms_tpl = candidate
                break

        for settings_file in _HOST_SETTINGS.get(ai_host, []):
            if settings_file == "gemini_trust":
                setup_commands.append(
                    f"python3 -c {shlex.quote(_GEMINI_TRUST_SCRIPT)} "
                    f"{shlex.quote(worktree_abs)}"
                )
                continue
            src = os.path.join(main_repo_abs, settings_file)
            dest = os.path.join(worktree_abs, settings_file)
            cmd = (
                f"python3 -c {shlex.quote(_SETTINGS_PATCH_SCRIPT)} "
                f"{shlex.quote(src)} {shlex.quote(dest)} {shlex.quote(main_tasks_abs)}"
            )
            if perms_tpl:
                cmd += f" {shlex.quote(perms_tpl)}"
            setup_commands.append(cmd)

        return {
            "success": True,
            "task_id": resolved_task_id,
            "worktree": worktree_metadata,
            "recycled_from": donor_task_id,
            "git_commands": git_commands,
            "setup_commands": setup_commands,
            "fix_paths_commands": [],  # Recycled worktrees already have relative paths
            "warnings": warnings,
            "wsl_use_native_commands": wsl_use_native_commands,
            "message": f"Recycled worktree from {donor_task_id}. Run git commands, then setup commands, then work in {worktree_path}"
        }

    # Fresh worktree creation (no recycling or no candidate found)
    worktree_metadata = {
        "status": "active",
        "path": worktree_path,
        "branch": branch_name,
        "base_branch": base_branch,
        "color_scheme_index": color_scheme_index,
        "created_at": datetime.now().isoformat()
    }

    state["worktree"] = worktree_metadata
    _save_state(task_dir, state)

    # Build setup commands (symlink .tasks/ + copy host settings)
    main_repo_abs = str(Path.cwd().resolve())
    worktree_abs = os.path.normpath(os.path.join(main_repo_abs, worktree_path))

    setup_commands = [
        f"ln -sfn {shlex.quote(os.path.join(main_repo_abs, '.tasks'))} {shlex.quote(os.path.join(worktree_abs, '.tasks'))}"
    ]

    main_tasks_abs = os.path.join(main_repo_abs, ".tasks")

    # Locate permissions template
    perms_tpl = ""
    for candidate in [
        os.path.join(main_repo_abs, "config", "worktree-permissions.json"),
        os.path.expanduser("~/.claude/config/worktree-permissions.json"),
    ]:
        if os.path.isfile(candidate):
            perms_tpl = candidate
            break

    for settings_file in _HOST_SETTINGS.get(ai_host, []):
        if settings_file == "gemini_trust":
            setup_commands.append(
                f"python3 -c {shlex.quote(_GEMINI_TRUST_SCRIPT)} "
                f"{shlex.quote(worktree_abs)}"
            )
            continue
        src = os.path.join(main_repo_abs, settings_file)
        dest = os.path.join(worktree_abs, settings_file)
        # Copy settings, inject additionalDirectories + baseline permissions
        # so the AI host can access .tasks/ and use workflow tools without prompts.
        cmd = (
            f"python3 -c {shlex.quote(_SETTINGS_PATCH_SCRIPT)} "
            f"{shlex.quote(src)} {shlex.quote(dest)} {shlex.quote(main_tasks_abs)}"
        )
        if perms_tpl:
            cmd += f" {shlex.quote(perms_tpl)}"
        setup_commands.append(cmd)

    # Build fix_paths_commands for WSL/Windows compatibility.
    # After `git worktree add`, the .git file and .git/worktrees/TASK/gitdir
    # contain absolute WSL paths that Windows tools can't read.  The
    # fix-worktree-paths.py script converts both to relative paths with
    # correct LF line endings.
    fix_paths_commands: list[str] = []
    if wsl and resolved_abs.startswith("/mnt/"):
        fix_paths_commands = [
            f"python3 {_FIX_WORKTREE_PATHS_SCRIPT} {resolved_task_id}"
        ]

    return {
        "success": True,
        "task_id": resolved_task_id,
        "worktree": worktree_metadata,
        "git_commands": [
            f"git worktree add -b {branch_name} {worktree_path} {base_branch}"
        ],
        "setup_commands": setup_commands,
        "fix_paths_commands": fix_paths_commands,
        "warnings": warnings,
        "wsl_use_native_commands": wsl_use_native_commands,
        "message": f"Run the git commands above, then the setup commands, then fix_paths_commands (if any), then work in {worktree_path}"
    }


def workflow_get_worktree_info(
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Get worktree metadata for a task.

    Args:
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        Worktree metadata or indication that no worktree exists.
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)

    return {
        "task_id": state.get("task_id"),
        "worktree": state.get("worktree"),
        "has_worktree": state.get("worktree") is not None and state["worktree"].get("status") == "active"
    }


def workflow_cleanup_worktree(
    task_id: Optional[str] = None,
    remove_branch: bool = True,
    keep_on_disk: bool = False
) -> dict[str, Any]:
    """Validate worktree state and return a cleanup script command.

    This function does NOT modify state — the cleanup script handles both
    git operations and state updates atomically (state only updates if git
    commands succeed).

    Args:
        task_id: Task identifier. If not provided, uses active task.
        remove_branch: Whether to include branch deletion.
        keep_on_disk: If True, mark worktree as 'recyclable' instead of
            'cleaned' and skip git worktree remove.

    Returns:
        Script command to execute for cleanup.
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    resolved_task_id = state.get("task_id", task_dir.name)

    worktree = state.get("worktree")
    if not worktree:
        return {
            "success": False,
            "error": f"No worktree configured for {resolved_task_id}"
        }

    if worktree.get("status") in ("cleaned", "recyclable"):
        return {
            "success": False,
            "error": f"Worktree already cleaned for {resolved_task_id}"
        }

    # Build the script command
    script_args = [resolved_task_id]
    if keep_on_disk:
        script_args.append("--keep-on-disk")
    if remove_branch:
        script_args.append("--remove-branch")

    script_command = f"python3 {_REPO_ROOT / 'scripts' / 'cleanup-worktree.py'} {' '.join(script_args)}"

    return {
        "success": True,
        "task_id": resolved_task_id,
        "worktree": worktree,
        "cleanup_command": script_command,
        "message": f"Run the cleanup command above from the main repo to remove the worktree."
    }


# Map ai_host to CLI command
_AI_HOST_CLI = {
    "claude": "claude",
    "gemini": "gemini",
    "copilot": "copilot",
    "opencode": "opencode",
}

# Host-specific settings files to copy into worktrees
_HOST_SETTINGS = {
    "claude": [".claude/settings.local.json"],
    "gemini": ["gemini_trust"],
    "copilot": [],
    "opencode": [],
}

# Python script to add worktree to Gemini trustedFolders.json
# Args: worktree_abs_path
_GEMINI_TRUST_SCRIPT = """
import json, os, sys
worktree_abs = sys.argv[1]
trust_file = os.path.expanduser("~/.gemini/trustedFolders.json")
os.makedirs(os.path.dirname(trust_file), exist_ok=True)
d = {}
if os.path.isfile(trust_file):
    with open(trust_file) as f:
        d = json.load(f)
if worktree_abs not in d:
    d[worktree_abs] = "TRUST_FOLDER"
    with open(trust_file, "w") as f:
        json.dump(d, f, indent=2)
        f.write("\\n")
"""

# Python script to copy settings and add additionalDirectories for parent .tasks/ access.
# Args: src_settings_path dest_settings_path parent_tasks_dir
_SETTINGS_PATCH_SCRIPT = """
import json, os, sys
src, dst, tasks_dir = sys.argv[1], sys.argv[2], sys.argv[3]
perms_tpl = sys.argv[4] if len(sys.argv) > 4 else None
os.makedirs(os.path.dirname(dst), exist_ok=True)
d = {}
if os.path.isfile(src):
    with open(src) as f:
        d = json.load(f)
dirs = d.setdefault("additionalDirectories", [])
if tasks_dir not in dirs:
    dirs.append(tasks_dir)
if perms_tpl and os.path.isfile(perms_tpl):
    with open(perms_tpl) as f:
        tpl = json.load(f)
    perms = d.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])
    for entry in tpl.get("permissions", {}).get("allow", []):
        if entry not in allow:
            allow.append(entry)
with open(dst, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\\n")
"""


def _build_resume_prompt(task_id: str, main_tasks_path: str, ai_host: str = "claude") -> str:
    """Build the resume prompt string for a worktree session."""
    if ai_host in ("gemini", "copilot"):
        resume_cmd = f"@crew-resume {task_id}"
    elif ai_host == "opencode":
        resume_cmd = f"/crew-resume {task_id}"
    else:
        resume_cmd = f"/crew resume {task_id}"
    return (
        f"Resume crew workflow {task_id}. "
        f"This is a git worktree — DO NOT create a new .tasks/ directory here. "
        f"The task state lives in the main repo at: {main_tasks_path} "
        f"Read and write all task state using that absolute path. "
        f"A .tasks/ symlink exists in this worktree for convenience, but always "
        f"prefer the absolute path above for reliability. "
        f"{resume_cmd}"
    )


def workflow_get_launch_command(
    task_id: Optional[str] = None,
    terminal_env: str = "unknown",
    ai_host: str = "claude",
    main_repo_path: Optional[str] = None,
    launch_mode: str = "auto",
) -> dict[str, Any]:
    """Generate platform-specific commands to launch a terminal in the worktree.

    Args:
        task_id: Task identifier. If not provided, uses active task.
        terminal_env: Terminal environment (tmux, windows_terminal, macos, linux_generic).
        ai_host: AI host to use (claude, gemini, copilot, opencode).
        main_repo_path: Absolute path to the main repository. Used to resolve
            the worktree absolute path.
        launch_mode: Terminal launch mode (auto, window, tab). "auto" uses
            platform defaults: tmux→window, windows_terminal→tab, macOS→window.

    Returns:
        Launch commands, resume prompt, and metadata.
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    resolved_task_id = state.get("task_id", task_dir.name)

    worktree = state.get("worktree")
    if not worktree:
        return {
            "success": False,
            "error": f"No worktree configured for {resolved_task_id}"
        }

    if worktree.get("status") != "active":
        return {
            "success": False,
            "error": f"Worktree is not active for {resolved_task_id} (status: {worktree.get('status')})"
        }

    # Resolve worktree absolute path
    worktree_rel_path = worktree["path"]
    if main_repo_path and not os.path.isabs(worktree_rel_path):
        worktree_abs_path = os.path.normpath(
            os.path.join(main_repo_path, worktree_rel_path)
        )
    else:
        worktree_abs_path = worktree_rel_path

    # Build resume prompt
    main_tasks_path = os.path.join(
        main_repo_path or ".", ".tasks", resolved_task_id
    )
    resume_prompt = _build_resume_prompt(resolved_task_id, main_tasks_path, ai_host)

    # Resolve CLI command
    cli = _AI_HOST_CLI.get(ai_host, "claude")

    warnings = []
    launch_commands = []

    safe_path = shlex.quote(worktree_abs_path)
    safe_prompt = shlex.quote(resume_prompt)
    safe_task_id = shlex.quote(resolved_task_id)

    # Build the CLI invocation per host
    if ai_host in ("copilot", "opencode"):
        # These hosts don't accept prompt args.
        # The .crew-resume file in the worktree provides context instead.
        cli_with_prompt = cli
    elif ai_host == "gemini":
        # gemini -i "prompt" executes prompt then stays interactive
        cli_with_prompt = f"{cli} -i {safe_prompt}"
    else:
        # claude "prompt" starts interactive with the prompt as the first message
        cli_with_prompt = f"{cli} {safe_prompt}"

    # Resolve color scheme for this worktree
    color_idx = worktree.get("color_scheme_index", 0)
    scheme = CREW_COLOR_SCHEMES[color_idx % len(CREW_COLOR_SCHEMES)]

    # Resolve launch mode: "auto" maps to platform defaults
    if launch_mode not in ("auto", "window", "tab"):
        launch_mode = "auto"
    if launch_mode == "auto":
        _auto_defaults = {
            "tmux": "window",
            "windows_terminal": "tab",
            "macos": "window",
        }
        launch_mode = _auto_defaults.get(terminal_env, "window")

    if terminal_env == "tmux":
        # tmux: open new window, cd to worktree, run CLI with prompt
        tmux_cmd = (
            f"tmux new-window -n {safe_task_id} -c {safe_path} "
            f"{shlex.quote(cli_with_prompt)}"
        )
        launch_commands.append(tmux_cmd)
        # Apply per-window background color so each task is visually distinct
        tmux_style_cmd = (
            f"tmux set-option -t {safe_task_id} -w window-style "
            f"'bg={scheme['bg']},fg={scheme['fg']}'"
        )
        launch_commands.append(tmux_style_cmd)

    elif terminal_env == "windows_terminal":
        # Windows Terminal from WSL: run wsl.exe as the tab/window process so WT
        # opens a WSL session. Use --cd for the working directory.
        # bash -lic: -l (login, sources .profile) + -i (interactive, sources
        # .bashrc where nvm/fnm/volta add CLI tools to PATH) + -c (command).
        # --tabColor and --colorScheme give each task a distinct visual identity.
        if launch_mode == "window":
            wt_cmd = (
                f"wt.exe new-window "
                f"--title {safe_task_id} "
                f"--colorScheme \"{scheme['name']}\" "
                f"wsl.exe --cd {safe_path} "
                f"-- bash -lic {shlex.quote(cli_with_prompt)}"
            )
        else:
            wt_cmd = (
                f"wt.exe new-tab "
                f"--title {safe_task_id} "
                f"--tabColor \"{scheme['tab']}\" "
                f"--colorScheme \"{scheme['name']}\" "
                f"wsl.exe --cd {safe_path} "
                f"-- bash -lic {shlex.quote(cli_with_prompt)}"
            )
        launch_commands.append(wt_cmd)

    elif terminal_env == "macos":
        # macOS Terminal: use osascript to open new Terminal window
        inner_script = f"cd {safe_path} && {cli_with_prompt}"
        osa_cmd = (
            f'osascript -e \'tell app "Terminal" to do script {shlex.quote(inner_script)}\''
        )
        launch_commands.append(osa_cmd)

    else:
        # linux_generic or unknown: cannot reliably open a new terminal
        warnings.append(
            "Cannot reliably open a new terminal on this platform. "
            "Please open a terminal manually, navigate to the worktree, and run the resume prompt."
        )

    # Record launch metadata in state
    state["worktree"]["launch"] = {
        "terminal_env": terminal_env,
        "ai_host": ai_host,
        "launch_mode": launch_mode,
        "launched_at": datetime.now().isoformat(),
        "worktree_abs_path": worktree_abs_path,
        "color_scheme": scheme["name"],
    }
    _save_state(task_dir, state)

    return {
        "success": True,
        "task_id": resolved_task_id,
        "launch_commands": launch_commands,
        "resume_prompt": resume_prompt,
        "worktree_path": worktree_abs_path,
        "color_scheme": scheme["name"],
        "warnings": warnings,
    }


# ── Interaction Logging ──────────────────────────────────────────────


def workflow_log_interaction(
    role: str,
    content: str,
    interaction_type: str = "message",
    agent: str = "",
    phase: str = "",
    task_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Append an interaction entry to .tasks/TASK_XXX/interactions.jsonl.

    Captures human-AI conversation throughout the crew workflow for
    documentation and context recovery.
    """
    if role not in INTERACTION_ROLES:
        return {
            "success": False,
            "error": f"Invalid role '{role}'. Must be one of: {', '.join(INTERACTION_ROLES)}"
        }

    if interaction_type not in INTERACTION_TYPES:
        return {
            "success": False,
            "error": f"Invalid interaction_type '{interaction_type}'. Must be one of: {', '.join(INTERACTION_TYPES)}"
        }

    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "success": False,
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    entry = {
        "timestamp": datetime.now().isoformat(),
        "role": role,
        "content": content,
        "type": interaction_type,
        "agent": agent,
        "phase": phase,
    }
    if metadata:
        entry["metadata"] = metadata

    interactions_file = task_dir / "interactions.jsonl"
    lock_file = task_dir / "interactions.jsonl.lock"
    lock = FileLock(str(lock_file), timeout=5)

    with lock:
        with open(interactions_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    return {
        "success": True,
        "entry": entry,
        "task_id": task_dir.name,
    }
