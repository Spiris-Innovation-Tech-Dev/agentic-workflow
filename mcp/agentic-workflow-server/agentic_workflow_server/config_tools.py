"""
Configuration Tools for Agentic Workflow MCP Server

Handles YAML configuration cascade merge:
  1. Global defaults:  ~/.claude/workflow-config.yaml
  2. Project config:   <repo>/.claude/workflow-config.yaml
  3. Task config:      <repo>/.tasks/TASK_XXX/config.yaml

Each level overrides the previous.
"""

import os
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None


DEFAULT_CONFIG = {
    "checkpoints": {
        "planning": {
            "after_architect": True,
            "after_developer": False,
            "after_reviewer": True,
            "after_skeptic": True
        },
        "implementation": {
            "at_25_percent": False,
            "at_50_percent": True,
            "at_75_percent": False,
            "before_commit": True
        },
        "documentation": {
            "after_technical_writer": True
        },
        "feedback": {
            "on_deviation": True,
            "on_test_failure": True,
            "on_major_change": True
        }
    },
    "knowledge_base": "docs/ai-context/",
    "task_directory": ".tasks/",
    "max_iterations": {
        "planning": 3,
        "implementation": 5,
        "feedback": 2
    },
    "models": {
        "orchestrator": "opus",
        "architect": "opus",
        "developer": "opus",
        "reviewer": "opus",
        "skeptic": "opus",
        "implementer": "opus",
        "feedback": "opus",
        "technical-writer": "opus"
    },
    "auto_actions": {
        "run_tests": True,
        "create_files": True,
        "modify_files": True,
        "run_build": True,
        "git_add": False,
        "git_commit": False
    },
    "loop_mode": {
        "enabled": False,
        "phases": {
            "planning": False,
            "implementation": True,
            "documentation": False
        },
        "completion_promise": "COMPLETE",
        "blocked_promise": "BLOCKED",
        "max_iterations": {
            "per_step": 10,
            "per_phase": 30,
            "before_escalate": 5
        },
        "verification": {
            "method": "tests",
            "custom_command": "",
            "require_all_pass": True
        }
    }
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> Optional[dict]:
    if not path.exists():
        return None

    if yaml is None:
        with open(path) as f:
            content = f.read()
            import re
            config = {}
            for line in content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    match = re.match(r'^(\w+):\s*(.+)$', line)
                    if match:
                        key, value = match.groups()
                        if value.lower() == 'true':
                            config[key] = True
                        elif value.lower() == 'false':
                            config[key] = False
                        elif value.isdigit():
                            config[key] = int(value)
                        else:
                            config[key] = value
            return config if config else None

    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _get_global_config_path() -> Path:
    return Path.home() / ".claude" / "workflow-config.yaml"


def _get_project_config_path(project_dir: Optional[str] = None) -> Path:
    if project_dir:
        return Path(project_dir) / ".claude" / "workflow-config.yaml"
    return Path.cwd() / ".claude" / "workflow-config.yaml"


def _get_task_config_path(task_id: str, project_dir: Optional[str] = None) -> Path:
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ".tasks" / task_id / "config.yaml"


def config_get_effective(
    task_id: Optional[str] = None,
    project_dir: Optional[str] = None
) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()

    global_path = _get_global_config_path()
    global_config = _load_yaml(global_path)
    if global_config:
        config = _deep_merge(config, global_config)

    project_path = _get_project_config_path(project_dir)
    project_config = _load_yaml(project_path)
    if project_config:
        config = _deep_merge(config, project_config)

    if task_id:
        task_path = _get_task_config_path(task_id, project_dir)
        task_config = _load_yaml(task_path)
        if task_config:
            config = _deep_merge(config, task_config)

    sources = []
    if global_config:
        sources.append(str(global_path))
    if project_config:
        sources.append(str(project_path))
    if task_id:
        task_path = _get_task_config_path(task_id, project_dir)
        if task_path.exists():
            sources.append(str(task_path))

    return {
        "config": config,
        "sources": sources,
        "has_global": global_config is not None,
        "has_project": project_config is not None,
        "has_task": task_id is not None and _get_task_config_path(task_id, project_dir).exists()
    }


def config_get_checkpoint(
    checkpoint: str,
    category: str,
    task_id: Optional[str] = None,
    project_dir: Optional[str] = None
) -> dict[str, Any]:
    effective = config_get_effective(task_id, project_dir)
    config = effective["config"]

    checkpoints = config.get("checkpoints", {})
    category_checkpoints = checkpoints.get(category, {})

    if checkpoint not in category_checkpoints:
        available = list(category_checkpoints.keys())
        return {
            "error": f"Unknown checkpoint '{checkpoint}' in category '{category}'",
            "available_checkpoints": available,
            "category": category
        }

    enabled = category_checkpoints[checkpoint]

    return {
        "checkpoint": checkpoint,
        "category": category,
        "enabled": enabled,
        "sources": effective["sources"]
    }


def config_get_model(
    agent: str,
    task_id: Optional[str] = None,
    project_dir: Optional[str] = None
) -> dict[str, Any]:
    effective = config_get_effective(task_id, project_dir)
    config = effective["config"]

    models = config.get("models", {})

    if agent not in models:
        return {
            "error": f"Unknown agent '{agent}'",
            "available_agents": list(models.keys())
        }

    return {
        "agent": agent,
        "model": models[agent],
        "sources": effective["sources"]
    }


def config_get_auto_action(
    action: str,
    task_id: Optional[str] = None,
    project_dir: Optional[str] = None
) -> dict[str, Any]:
    effective = config_get_effective(task_id, project_dir)
    config = effective["config"]

    auto_actions = config.get("auto_actions", {})

    if action not in auto_actions:
        return {
            "error": f"Unknown auto action '{action}'",
            "available_actions": list(auto_actions.keys())
        }

    return {
        "action": action,
        "allowed": auto_actions[action],
        "sources": effective["sources"]
    }


def config_get_loop_mode(
    task_id: Optional[str] = None,
    project_dir: Optional[str] = None
) -> dict[str, Any]:
    effective = config_get_effective(task_id, project_dir)
    config = effective["config"]

    loop_mode = config.get("loop_mode", {})

    return {
        "enabled": loop_mode.get("enabled", False),
        "phases": loop_mode.get("phases", {}),
        "max_iterations": loop_mode.get("max_iterations", {}),
        "verification": loop_mode.get("verification", {}),
        "sources": effective["sources"]
    }
