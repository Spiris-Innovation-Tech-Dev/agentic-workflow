"""
Configuration Tools for Agentic Workflow MCP Server

Handles YAML configuration cascade merge:
  1. Global defaults:  ~/.claude/ or ~/.copilot/ or ~/.gemini/workflow-config.yaml
  2. Project config:   <repo>/.claude/ or .copilot/ or .gemini/workflow-config.yaml
  3. Task config:      <repo>/.tasks/TASK_XXX/config.yaml

Each level overrides the previous. Platform directories are checked
in order (.claude first, then .copilot, then .gemini), using whichever exists.
"""

import os
import shutil
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
    "worktree": {
        "base_path": "../{repo_name}-worktrees",
        "branch_prefix": "crew/",
        "cleanup_on_complete": "prompt",
        "auto_launch": "prompt",
        "terminal_launch_mode": "auto",
        "ai_host": "auto",
        "copy_settings": True,
        "recycle": "prompt",
        "sync_before_create": "prompt",
        "wsl_native_path": "",
        "install_deps": "auto",
        "jira": {
            "auto_assign": "never",
            "transitions": {
                "on_create": {
                    "to": "",
                    "mode": "auto",
                    "only_from": [],
                },
                "on_complete": {
                    "to": "",
                    "mode": "auto",
                    "only_from": [],
                },
                "on_cleanup": {
                    "to": "",
                    "mode": "prompt",
                    "only_from": [],
                },
            },
        },
        "post_setup_commands": [],
    },
    "auto_actions": {
        "run_tests": True,
        "create_files": True,
        "modify_files": True,
        "run_build": True,
        "git_add": False,
        "git_commit": False,
        "git_push": False
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


def _get_valid_keys(defaults: dict, prefix: str = "") -> set[str]:
    """Recursively collect all valid keys from defaults."""
    keys = set()
    for key, value in defaults.items():
        full_key = f"{prefix}.{key}" if prefix else key
        keys.add(full_key)
        if isinstance(value, dict):
            keys.update(_get_valid_keys(value, full_key))
    return keys


def _validate_config(config: dict, defaults: dict, prefix: str = "") -> list[str]:
    """Validate config against defaults, returning warnings for unknown keys."""
    warnings = []
    for key, value in config.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if key not in defaults:
            warnings.append(f"Unknown config key: '{full_key}'")
        elif isinstance(value, dict) and isinstance(defaults.get(key), dict):
            warnings.extend(_validate_config(value, defaults[key], full_key))
        elif value is not None:
            expected_type = type(defaults.get(key))
            if expected_type is not type(None) and not isinstance(value, expected_type):
                if not (expected_type == int and isinstance(value, bool)):
                    warnings.append(
                        f"Invalid type for '{full_key}': expected {expected_type.__name__}, got {type(value).__name__}"
                    )
    return warnings


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


PLATFORM_DIRS = [".claude", ".copilot", ".gemini"]


def _get_global_config_path() -> Path:
    """Return global config path, checking multiple platform directories."""
    for platform_dir in PLATFORM_DIRS:
        path = Path.home() / platform_dir / "workflow-config.yaml"
        if path.exists():
            return path
    return Path.home() / ".claude" / "workflow-config.yaml"


def _get_project_config_path(project_dir: Optional[str] = None) -> Path:
    """Return project config path, checking multiple platform directories."""
    base = Path(project_dir) if project_dir else Path.cwd()
    for platform_dir in PLATFORM_DIRS:
        path = base / platform_dir / "workflow-config.yaml"
        if path.exists():
            return path
    return base / ".claude" / "workflow-config.yaml"


def _get_task_config_path(task_id: str, project_dir: Optional[str] = None) -> Path:
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ".tasks" / task_id / "config.yaml"


def config_get_effective(
    task_id: Optional[str] = None,
    project_dir: Optional[str] = None
) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    warnings = []

    global_path = _get_global_config_path()
    global_config = _load_yaml(global_path)
    if global_config:
        warnings.extend(_validate_config(global_config, DEFAULT_CONFIG))
        config = _deep_merge(config, global_config)

    project_path = _get_project_config_path(project_dir)
    project_config = _load_yaml(project_path)
    if project_config:
        warnings.extend(_validate_config(project_config, DEFAULT_CONFIG))
        config = _deep_merge(config, project_config)

    if task_id:
        task_path = _get_task_config_path(task_id, project_dir)
        task_config = _load_yaml(task_path)
        if task_config:
            warnings.extend(_validate_config(task_config, DEFAULT_CONFIG))
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
        "warnings": warnings,
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


def _is_beads_installed() -> bool:
    """Check if beads is installed and available."""
    # Check for beads CLI
    if shutil.which("beads") or shutil.which("bd"):
        return True

    # Check for beads-mcp in PATH
    if shutil.which("beads-mcp"):
        return True

    # Check for .beads directory in current project (beads is initialized)
    if (Path.cwd() / ".beads").exists():
        return True

    return False


def _is_beads_initialized() -> bool:
    """Check if beads is initialized in the current project."""
    return (Path.cwd() / ".beads").exists()


def config_get_beads(
    task_id: Optional[str] = None,
    project_dir: Optional[str] = None
) -> dict[str, Any]:
    """Get beads configuration with auto-detection support.

    If beads.enabled is set to "auto", will check if beads is installed
    and initialized in the current project.

    Returns:
        Beads configuration with resolved enabled status
    """
    effective = config_get_effective(task_id, project_dir)
    config = effective["config"]

    beads_config = config.get("beads", {})
    enabled_setting = beads_config.get("enabled", False)

    # Handle auto-detection
    if enabled_setting == "auto":
        beads_installed = _is_beads_installed()
        beads_initialized = _is_beads_initialized()
        enabled = beads_installed and beads_initialized
        detection_info = {
            "mode": "auto",
            "beads_installed": beads_installed,
            "beads_initialized": beads_initialized,
            "resolved_to": enabled
        }
    else:
        enabled = bool(enabled_setting)
        detection_info = {
            "mode": "manual",
            "configured_value": enabled_setting
        }

    return {
        "enabled": enabled,
        "auto_create_issue": beads_config.get("auto_create_issue", False),
        "auto_link": beads_config.get("auto_link", True),
        "sync_status": beads_config.get("sync_status", True),
        "add_comments": beads_config.get("add_comments", True),
        "detection": detection_info,
        "sources": effective["sources"]
    }
