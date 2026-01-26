"""
MCP Resources for Agentic Workflow Server

Provides URI-based access to workflow state and configuration data.

Resource URIs:
  - workflow://tasks                    - List all tasks
  - workflow://tasks/{id}/state         - State of specific task
  - workflow://active                   - Currently active task
  - config://effective                  - Fully merged effective config
"""

import json
from typing import Any, Optional

from .state_tools import (
    list_tasks,
    get_active_task,
    workflow_get_state,
    get_tasks_dir,
)
from .config_tools import config_get_effective


def get_tasks_list() -> dict[str, Any]:
    tasks = list_tasks()
    return {
        "tasks": tasks,
        "count": len(tasks),
        "active_count": sum(1 for t in tasks if not t.get("is_complete")),
        "completed_count": sum(1 for t in tasks if t.get("is_complete")),
        "tasks_dir": str(get_tasks_dir())
    }


def get_task_state(task_id: str) -> dict[str, Any]:
    return workflow_get_state(task_id=task_id)


def get_active_task_state() -> dict[str, Any]:
    active = get_active_task()
    if not active:
        return {
            "error": "No active task",
            "has_active": False
        }

    state = workflow_get_state(task_id=active)
    state["has_active"] = True
    return state


def get_effective_config() -> dict[str, Any]:
    active = get_active_task()
    return config_get_effective(task_id=active)


def resolve_resource(uri: str) -> str:
    if uri == "workflow://tasks":
        return json.dumps(get_tasks_list(), indent=2)

    if uri == "workflow://active":
        return json.dumps(get_active_task_state(), indent=2)

    if uri == "config://effective":
        return json.dumps(get_effective_config(), indent=2)

    if uri.startswith("workflow://tasks/") and uri.endswith("/state"):
        task_id = uri.replace("workflow://tasks/", "").replace("/state", "")
        return json.dumps(get_task_state(task_id), indent=2)

    return json.dumps({"error": f"Unknown resource URI: {uri}"})


RESOURCE_DESCRIPTIONS = {
    "workflow://tasks": {
        "name": "All workflow tasks",
        "description": "List of all tasks in .tasks/ directory with summary info",
        "mimeType": "application/json"
    },
    "workflow://active": {
        "name": "Active workflow task",
        "description": "Currently active (incomplete) workflow task state",
        "mimeType": "application/json"
    },
    "config://effective": {
        "name": "Effective configuration",
        "description": "Fully merged workflow configuration from all sources",
        "mimeType": "application/json"
    }
}


RESOURCE_TEMPLATES = {
    "workflow://tasks/{task_id}/state": {
        "name": "Task workflow state",
        "description": "Get workflow state for a specific task by ID",
        "mimeType": "application/json"
    }
}
