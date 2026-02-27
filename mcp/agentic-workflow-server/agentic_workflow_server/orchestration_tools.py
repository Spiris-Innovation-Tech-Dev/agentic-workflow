"""
Orchestration Tools for Agentic Workflow MCP Server

Higher-level tools that compose state_tools and config_tools into
single-call operations for the /crew command. These extract deterministic
logic (arg parsing, config merging, phase sequencing) from crew.md,
reducing its size and improving testability.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from .state_tools import (
    find_task_dir,
    workflow_initialize,
    workflow_detect_mode,
    workflow_set_mode,
    workflow_set_kb_inventory,
    workflow_enable_optional_phase,
    workflow_get_state,
    workflow_is_phase_in_mode,
    workflow_get_effort_level,
    workflow_get_cost_summary,
    workflow_get_worktree_info,
    workflow_mark_docs_needed,
    workflow_add_review_issue,
    workflow_add_concern,
    workflow_log_interaction,
    _load_state,
    _save_state,
    _REPO_ROOT,
    WORKFLOW_MODES,
    PHASE_ORDER,
)
from .config_tools import (
    config_get_effective,
    config_get_beads,
    _deep_merge,
    DEFAULT_CONFIG,
)

# ============================================================================
# Helpers
# ============================================================================

def _slugify(text: str) -> str:
    """Convert text to git-branch-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s_-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


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


# ============================================================================
# Optional agent detection patterns
# ============================================================================

OPTIONAL_AGENT_TRIGGERS = {
    "security_auditor": {
        "keywords": [
            "auth", "password", "token", "secret", "sql", "encryption",
            "security", "csrf", "xss", "injection", "oauth", "jwt",
            "credential", "permission", "rbac", "acl"
        ],
        "file_patterns": ["**/auth/**", "**/security/**", "**/.env*"]
    },
    "performance_analyst": {
        "keywords": [
            "performance", "cache", "optimize", "slow", "scale",
            "latency", "throughput", "benchmark", "profil", "memory leak",
            "n+1", "database index", "query optimization"
        ],
        "file_patterns": ["**/database/**", "**/cache/**"]
    },
    "api_guardian": {
        "keywords": [
            "api", "endpoint", "breaking", "deprecat", "schema",
            "rest", "graphql", "grpc", "openapi", "swagger",
            "backward compat", "versioning"
        ],
        "file_patterns": ["**/api/**", "**/routes/**", "**/openapi*"]
    },
    "accessibility_reviewer": {
        "keywords": [
            "ui", "component", "form", "a11y", "wcag", "aria",
            "screen reader", "keyboard nav", "accessibility",
            "contrast", "focus"
        ],
        "file_patterns": ["**/*.tsx", "**/*.jsx", "**/*.vue"]
    }
}


# ============================================================================
# Tool 1: crew_parse_args
# ============================================================================

def crew_parse_args(raw_args: str) -> dict[str, Any]:
    """Parse /crew command arguments into structured format.

    Args:
        raw_args: Raw argument string from /crew command

    Returns:
        Parsed action, task_description, options dict, and any errors
    """
    errors = []
    options: dict[str, Any] = {}
    remaining_parts: list[str] = []

    if not raw_args or not raw_args.strip():
        return {
            "action": "start",
            "task_description": "",
            "options": options,
            "errors": ["No arguments provided. Usage: /crew <task description> [options]"]
        }

    text = raw_args.strip()

    # Detect action from first word
    action = "start"
    first_word = text.split()[0].lower() if text.split() else ""

    if first_word in ("resume", "status", "proceed", "config"):
        action = first_word
        text = text[len(first_word):].strip()
    elif first_word == "ask":
        action = "ask"
        text = text[len("ask"):].strip()
    elif first_word == "start":
        action = "start"
        text = text[len("start"):].strip()

    # For non-start actions, handle simply
    if action == "resume":
        return {
            "action": "resume",
            "task_description": "",
            "task_id": text.strip() if text.strip() else None,
            "options": options,
            "errors": errors
        }
    if action == "status":
        return {
            "action": "status",
            "task_description": "",
            "options": options,
            "errors": errors
        }
    if action == "proceed":
        return {
            "action": "proceed",
            "task_description": "",
            "options": options,
            "errors": errors
        }
    if action == "config":
        return {
            "action": "config",
            "task_description": "",
            "options": options,
            "errors": errors
        }
    if action == "ask":
        return _parse_ask_args(text, errors)

    # Parse options and task description for start action
    # Tokenize respecting quotes
    tokens = _tokenize(text)
    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token == "--mode" and i + 1 < len(tokens):
            mode_val = tokens[i + 1]
            if mode_val in ("full", "turbo", "fast", "minimal", "auto"):
                options["mode"] = mode_val
            else:
                errors.append(f"Invalid mode '{mode_val}'. Must be: full, turbo, fast, minimal, auto")
            i += 2
        elif token == "--loop-mode":
            options["loop_mode"] = True
            i += 1
        elif token == "--no-loop":
            options["loop_mode"] = False
            i += 1
        elif token == "--max-iterations" and i + 1 < len(tokens):
            try:
                options["max_iterations"] = int(tokens[i + 1])
            except ValueError:
                errors.append(f"Invalid --max-iterations value: '{tokens[i + 1]}'")
            i += 2
        elif token == "--verify" and i + 1 < len(tokens):
            method = tokens[i + 1]
            if method in ("tests", "build", "lint", "all"):
                options["verify"] = method
            else:
                errors.append(f"Invalid --verify method '{method}'. Must be: tests, build, lint, all")
            i += 2
        elif token == "--no-checkpoints":
            options["no_checkpoints"] = True
            i += 1
        elif token == "--parallel":
            options["parallel"] = True
            i += 1
        elif token == "--beads" and i + 1 < len(tokens):
            options["beads"] = tokens[i + 1]
            i += 2
        elif token == "--config" and i + 1 < len(tokens):
            options["config_file"] = tokens[i + 1]
            i += 2
        elif token == "--task" and i + 1 < len(tokens):
            options["task_file"] = tokens[i + 1]
            i += 2
        elif token.startswith("--"):
            errors.append(f"Unknown option: {token}")
            i += 1
        else:
            remaining_parts.append(token)
            i += 1

    task_description = " ".join(remaining_parts).strip()
    # Strip wrapping quotes from task description
    if len(task_description) >= 2:
        if (task_description[0] == '"' and task_description[-1] == '"') or \
           (task_description[0] == "'" and task_description[-1] == "'"):
            task_description = task_description[1:-1]

    return {
        "action": action,
        "task_description": task_description,
        "options": options,
        "errors": errors
    }


def _parse_ask_args(text: str, errors: list) -> dict[str, Any]:
    """Parse /crew ask subcommand arguments."""
    tokens = _tokenize(text)
    options: dict[str, Any] = {}

    if not tokens:
        errors.append("Usage: /crew ask <agent> <question> [options]")
        return {
            "action": "ask",
            "agent": None,
            "task_description": "",
            "options": options,
            "errors": errors
        }

    agent = tokens[0].lower()
    valid_agents = [
        "architect", "developer", "reviewer", "skeptic", "feedback",
        "implementer", "technical-writer", "security-auditor",
        "api-guardian", "accessibility-reviewer", "performance-analyst",
    ]
    if agent not in valid_agents:
        errors.append(f"Unknown agent '{agent}'. Available: {', '.join(valid_agents)}")

    remaining_parts = []
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token == "--context" and i + 1 < len(tokens):
            options["context"] = tokens[i + 1]
            i += 2
        elif token == "--file" and i + 1 < len(tokens):
            options["file"] = tokens[i + 1]
            i += 2
        elif token == "--plan" and i + 1 < len(tokens):
            options["plan"] = tokens[i + 1]
            i += 2
        elif token == "--diff":
            options["diff"] = True
            i += 1
        elif token == "--model" and i + 1 < len(tokens):
            options["model"] = tokens[i + 1]
            i += 2
        elif token.startswith("--"):
            errors.append(f"Unknown option for ask: {token}")
            i += 1
        else:
            remaining_parts.append(token)
            i += 1

    question = " ".join(remaining_parts).strip()

    return {
        "action": "ask",
        "agent": agent,
        "task_description": question,
        "options": options,
        "errors": errors
    }


def _tokenize(text: str) -> list[str]:
    """Tokenize respecting quoted strings."""
    tokens = []
    current = []
    in_quote = None

    for char in text:
        if in_quote:
            if char == in_quote:
                in_quote = None
            else:
                current.append(char)
        elif char in ('"', "'"):
            in_quote = char
        elif char in (' ', '\t') and not in_quote:
            if current:
                tokens.append(''.join(current))
                current = []
        else:
            current.append(char)

    if current:
        tokens.append(''.join(current))

    return tokens


# ============================================================================
# Tool 2: crew_init_task
# ============================================================================

def crew_init_task(
    task_description: str,
    options: Optional[dict] = None,
    project_dir: Optional[str] = None
) -> dict[str, Any]:
    """Full task initialization in one call.

    Composes: config_get_effective, crew_apply_config_overrides,
    workflow_initialize, workflow_detect_mode, workflow_set_mode,
    workflow_set_kb_inventory, crew_detect_optional_agents.

    Args:
        task_description: Description of the task
        options: Parsed options dict from crew_parse_args
        project_dir: Optional project directory

    Returns:
        task_id, task_dir, mode, optional_agents, kb_inventory, config
    """
    options = options or {}

    # Step 1: Get effective config
    effective = config_get_effective(project_dir=project_dir)
    config = effective["config"]

    # Step 2: Apply CLI overrides
    override_result = crew_apply_config_overrides(options)
    if override_result.get("overrides"):
        config = _deep_merge(config, override_result["overrides"])

    # Step 3: Initialize workflow
    init_result = workflow_initialize(description=task_description)
    if not init_result.get("success"):
        return init_result

    task_id = init_result["task_id"]
    task_dir_str = init_result["task_dir"]

    # Step 3.5: Store linked_issue if beads option provided
    if options.get("beads"):
        task_dir = find_task_dir(task_id)
        if task_dir:
            state = _load_state(task_dir)
            state["linked_issue"] = options["beads"]
            _save_state(task_dir, state)

    # Step 4: Determine and set mode
    mode_to_set = options.get("mode", "auto")
    mode_result = workflow_set_mode(mode=mode_to_set, task_id=task_id)
    effective_mode = "full"
    if mode_result.get("success"):
        effective_mode = mode_result["workflow_mode"]["effective"]

    # Step 5: Inventory knowledge base
    kb_path = config.get("knowledge_base", "docs/ai-context/")
    kb_files = []
    kb_full_path = Path(project_dir) / kb_path if project_dir else Path.cwd() / kb_path
    if kb_full_path.exists() and kb_full_path.is_dir():
        kb_files = [str(f.relative_to(kb_full_path)) for f in kb_full_path.rglob("*") if f.is_file()]
    workflow_set_kb_inventory(path=str(kb_path), files=kb_files, task_id=task_id)

    # Step 6: Detect optional agents
    optional_result = crew_detect_optional_agents(
        task_description=task_description,
        task_id=task_id
    )

    # Step 7: Save effective config to task dir
    task_dir = find_task_dir(task_id)
    if task_dir:
        try:
            import yaml
            with open(task_dir / "config.yaml", "w") as f:
                yaml.dump(config, f, default_flow_style=False)
        except ImportError:
            with open(task_dir / "config.yaml", "w") as f:
                json.dump(config, f, indent=2)

        # Save task description
        with open(task_dir / "task.md", "w") as f:
            f.write(f"# Task\n\n{task_description}\n")

    # Log initial user input so every platform gets it automatically
    ai_host = options.get("ai_host", config.get("ai_host", "unknown"))
    workflow_log_interaction(
        role="human",
        content=task_description,
        interaction_type="message",
        agent="",
        phase="init",
        task_id=task_id,
        metadata={"ai_host": ai_host},
    )

    # Store ai_host in state.json for crew-board display
    if task_dir:
        state = _load_state(task_dir)
        state["ai_host"] = ai_host
        _save_state(task_dir, state)

    return {
        "success": True,
        "task_id": task_id,
        "task_dir": task_dir_str,
        "mode": effective_mode,
        "config": config,
        "optional_agents": optional_result.get("enabled", []),
        "kb_inventory": {
            "path": str(kb_path),
            "files": kb_files
        },
        "beads_issue": options.get("beads")
    }


# ============================================================================
# Tool 3: crew_apply_config_overrides
# ============================================================================

def crew_apply_config_overrides(
    options: dict,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Merge CLI option flags into effective config.

    Maps command-line options to config structure overrides.

    Args:
        options: Parsed options dict from crew_parse_args
        task_id: Optional task ID for context

    Returns:
        Config overrides dict and applied list
    """
    overrides: dict[str, Any] = {}
    applied = []

    if options.get("loop_mode") is True:
        overrides.setdefault("loop_mode", {})["enabled"] = True
        applied.append("loop_mode.enabled = true")
    elif options.get("loop_mode") is False:
        overrides.setdefault("loop_mode", {})["enabled"] = False
        applied.append("loop_mode.enabled = false")

    if "max_iterations" in options:
        overrides.setdefault("loop_mode", {}).setdefault("max_iterations", {})["per_step"] = options["max_iterations"]
        applied.append(f"loop_mode.max_iterations.per_step = {options['max_iterations']}")

    if "verify" in options:
        overrides.setdefault("loop_mode", {}).setdefault("verification", {})["method"] = options["verify"]
        applied.append(f"loop_mode.verification.method = {options['verify']}")

    if options.get("no_checkpoints"):
        overrides["checkpoints"] = {
            "planning": {
                "after_architect": False,
                "after_developer": False,
                "after_reviewer": False,
                "after_skeptic": False
            },
            "implementation": {
                "at_25_percent": False,
                "at_50_percent": False,
                "at_75_percent": False,
                "before_commit": False
            },
            "documentation": {
                "after_technical_writer": False
            },
            "feedback": {
                "on_deviation": False,
                "on_test_failure": False,
                "on_major_change": False
            }
        }
        applied.append("all checkpoints disabled")

    if options.get("parallel"):
        overrides.setdefault("parallelization", {}).setdefault("reviewer_skeptic", {})["enabled"] = True
        applied.append("parallelization.reviewer_skeptic.enabled = true")

    if options.get("beads"):
        overrides.setdefault("beads", {})["enabled"] = True
        overrides["beads"]["linked_issue"] = options["beads"]
        applied.append(f"beads.enabled = true, beads.linked_issue = {options['beads']}")

    return {
        "overrides": overrides,
        "applied": applied,
        "task_id": task_id
    }


# ============================================================================
# Tool 4: crew_detect_optional_agents
# ============================================================================

def crew_detect_optional_agents(
    task_description: str,
    files_affected: Optional[list[str]] = None,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Keyword/pattern match against specialized agent triggers.

    Auto-calls workflow_enable_optional_phase for each match.

    Args:
        task_description: Description of the task
        files_affected: Optional list of affected file paths
        task_id: Optional task ID

    Returns:
        enabled list, reasons dict, skipped list
    """
    desc_lower = task_description.lower()
    files_affected = files_affected or []
    files_str = " ".join(files_affected).lower()

    enabled = []
    reasons = {}
    skipped = []

    for agent, triggers in OPTIONAL_AGENT_TRIGGERS.items():
        matched_keywords = []
        for kw in triggers["keywords"]:
            if kw in desc_lower:
                matched_keywords.append(kw)

        matched_patterns = []
        if files_affected:
            for pattern in triggers.get("file_patterns", []):
                # Simple glob check: convert ** pattern to substring match
                simplified = pattern.replace("**/", "").replace("/**", "").replace("*", "")
                if simplified in files_str:
                    matched_patterns.append(pattern)

        if matched_keywords or matched_patterns:
            reason_parts = []
            if matched_keywords:
                reason_parts.append(f"keywords: {', '.join(matched_keywords)}")
            if matched_patterns:
                reason_parts.append(f"files: {', '.join(matched_patterns)}")
            reason = "; ".join(reason_parts)

            enabled.append(agent)
            reasons[agent] = reason

            # Auto-enable in workflow state
            if task_id:
                workflow_enable_optional_phase(phase=agent, reason=reason, task_id=task_id)
        else:
            skipped.append(agent)

    return {
        "enabled": enabled,
        "reasons": reasons,
        "skipped": skipped,
        "task_id": task_id
    }


# ============================================================================
# Tool 5: crew_get_next_phase (highest impact)
# ============================================================================

# Agent prompt file mapping
AGENT_PROMPT_FILES = {
    "architect": "architect.md",
    "developer": "developer.md",
    "reviewer": "reviewer.md",
    "skeptic": "skeptic.md",
    "implementer": "implementer.md",
    "feedback": "feedback.md",
    "technical_writer": "technical-writer.md",
    "security_auditor": "security-auditor.md",
    "performance_analyst": "performance-analyst.md",
    "api_guardian": "api-guardian.md",
    "accessibility_reviewer": "accessibility-reviewer.md",
}

# Subagent turn limits by category
SUBAGENT_LIMITS = {
    "planning_agents": 30,
    "implementation_agents": 50,
    "documentation_agents": 20,
    "consultation_agents": 15,
}

# Map agents to their limit category
AGENT_LIMIT_CATEGORY = {
    "architect": "planning_agents",
    "developer": "planning_agents",
    "reviewer": "planning_agents",
    "skeptic": "planning_agents",
    "implementer": "implementation_agents",
    "feedback": "planning_agents",
    "technical_writer": "documentation_agents",
    "security_auditor": "planning_agents",
    "performance_analyst": "planning_agents",
    "api_guardian": "planning_agents",
    "accessibility_reviewer": "planning_agents",
}


def crew_get_next_phase(
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Determine the next workflow action based on current state + mode.

    Returns what the orchestrator should do next: spawn an agent,
    hit a checkpoint, or complete the workflow.

    Args:
        task_id: Task identifier. If not provided, uses active task.

    Returns:
        action, agent, agent_prompt_path, context_files, effort_level,
        max_turns, parallel_with, checkpoint_after, variables
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    current_phase = state.get("phase")
    phases_completed = [p.lower().replace("-", "_") for p in state.get("phases_completed", [])]
    mode_config = state.get("workflow_mode", {})
    effective_mode = mode_config.get("effective", "full")
    mode_phases = mode_config.get("phases", WORKFLOW_MODES.get(effective_mode, WORKFLOW_MODES["full"])["phases"])
    optional_phases = state.get("optional_phases", [])

    # Get effective config for checkpoint/parallel settings
    effective = config_get_effective(task_id=state.get("task_id"))
    config = effective["config"]

    # Determine what phase comes next
    if current_phase is None:
        # Workflow not started - begin with first phase in mode
        next_agent = mode_phases[0] if mode_phases else "architect"
        return _build_phase_action(next_agent, state, config, task_dir)

    # Check if current phase is complete
    if current_phase not in phases_completed:
        # Current phase still running - check for checkpoint
        checkpoint = _get_checkpoint_for_phase(current_phase, config)
        if checkpoint:
            concerns = state.get("concerns", [])
            unaddressed = [c for c in concerns if not c.get("addressed_by")]
            return {
                "action": "checkpoint",
                "phase": current_phase,
                "checkpoint_name": checkpoint,
                "task_id": state.get("task_id"),
                "unaddressed_concerns": unaddressed,
                "concerns_count": len(unaddressed),
            }
        # Phase output not yet processed - orchestrator should process it
        return {
            "action": "process_output",
            "phase": current_phase,
            "task_id": state.get("task_id")
        }

    # Current phase is complete - find next
    # Build the full sequence: mode phases + optional phases (after reviewer)
    full_sequence = list(mode_phases)

    # Insert optional phases after reviewer (or after developer if no reviewer)
    insert_after = "reviewer" if "reviewer" in full_sequence else "developer"
    if insert_after in full_sequence:
        insert_idx = full_sequence.index(insert_after) + 1
        for opt_phase in optional_phases:
            if opt_phase not in full_sequence:
                full_sequence.insert(insert_idx, opt_phase)
                insert_idx += 1

    # Find current position and get next
    try:
        current_idx = full_sequence.index(current_phase)
    except ValueError:
        # Current phase not in sequence - find nearest next
        current_idx = -1
        for i, p in enumerate(full_sequence):
            if p in phases_completed:
                current_idx = i

    next_idx = current_idx + 1
    while next_idx < len(full_sequence):
        candidate = full_sequence[next_idx]
        if candidate not in phases_completed:
            break
        next_idx += 1

    if next_idx >= len(full_sequence):
        # All phases complete
        return {
            "action": "complete",
            "task_id": state.get("task_id"),
            "phases_completed": phases_completed
        }

    next_agent = full_sequence[next_idx]

    # Check for parallel execution (reviewer + skeptic)
    parallel_config = config.get("parallelization", {}).get("reviewer_skeptic", {})
    parallel_enabled = parallel_config.get("enabled", False)
    parallel_with = None

    if parallel_enabled and next_agent == "reviewer" and "skeptic" in full_sequence:
        skeptic_idx = full_sequence.index("skeptic")
        if "skeptic" not in phases_completed and skeptic_idx > next_idx:
            parallel_with = "skeptic"

    return _build_phase_action(next_agent, state, config, task_dir, parallel_with=parallel_with)


def _build_phase_action(
    agent: str,
    state: dict,
    config: dict,
    task_dir: Path,
    parallel_with: Optional[str] = None
) -> dict[str, Any]:
    """Build the action dict for spawning an agent phase."""
    task_id = state.get("task_id", "")

    # Get agent prompt path (supports custom agents via {agent}.md fallback)
    prompt_file = AGENT_PROMPT_FILES.get(agent, f"{agent.replace('_', '-')}.md")
    agents_dir = Path.home() / ".claude" / "agents"
    agent_prompt_path = str(agents_dir / prompt_file)

    # Get effort level (custom agents get "high" default via workflow_get_effort_level)
    effort_result = workflow_get_effort_level(agent=agent, task_id=task_id)
    effort = effort_result.get("effort", "high")

    # Get max turns from config first, then hardcoded defaults
    subagent_limits = config.get("subagent_limits", {}).get("max_turns", {})
    category = AGENT_LIMIT_CATEGORY.get(agent, "planning_agents")
    max_turns = subagent_limits.get(category, SUBAGENT_LIMITS.get(category, 30))

    # Get context files
    context_files = _get_context_files(agent, state, task_dir)

    # Check for checkpoint after this phase
    checkpoint_after = _get_checkpoint_for_phase(agent, config) is not None

    # Variable substitution values
    kb_inv = state.get("knowledge_base_inventory", {})
    variables = {
        "knowledge_base": config.get("knowledge_base", "docs/ai-context/"),
        "task_directory": config.get("task_directory", ".tasks/"),
        "task_id": task_id,
        "task_dir": str(task_dir),
        "kb_path": kb_inv.get("path", "docs/ai-context/"),
        "kb_files": kb_inv.get("files", []),
    }

    # Build beads comment if enabled
    beads_comment = None
    beads_config = config.get("beads", {})
    if beads_config.get("enabled") and beads_config.get("add_comments"):
        beads_comment = f"Phase '{agent}' starting for task {task_id}"

    result: dict[str, Any] = {
        "action": "spawn_agent",
        "agent": agent,
        "agent_prompt_path": agent_prompt_path,
        "context_files": context_files,
        "effort_level": effort,
        "max_turns": max_turns,
        "checkpoint_after": checkpoint_after,
        "variables": variables,
        "task_id": task_id,
    }

    # Provide git diff commands for agents that need code change context
    if agent in ("technical_writer", "feedback"):
        wt = state.get("worktree", {})
        base_branch = wt.get("base_branch", "main")
        result["git_diff_command"] = f"git diff {base_branch}...HEAD"
        result["git_diff_uncommitted_command"] = "git diff"

    if parallel_with:
        result["parallel_with"] = parallel_with
        # Also provide info for the parallel agent
        par_prompt_file = AGENT_PROMPT_FILES.get(parallel_with, f"{parallel_with}.md")
        result["parallel_agent_prompt_path"] = str(agents_dir / par_prompt_file)
        par_category = AGENT_LIMIT_CATEGORY.get(parallel_with, "planning_agents")
        result["parallel_max_turns"] = SUBAGENT_LIMITS.get(par_category, 30)

    if beads_comment:
        result["beads_comment"] = beads_comment

    return result


def _get_context_files(agent: str, state: dict, task_dir: Path) -> list[str]:
    """Determine which context files an agent needs."""
    files = []

    # Always include task description
    task_md = task_dir / "task.md"
    if task_md.exists():
        files.append(str(task_md))

    # Agent-specific context
    if agent in ("developer", "reviewer", "skeptic", "feedback"):
        arch_output = task_dir / "architect.md"
        if arch_output.exists():
            files.append(str(arch_output))

    if agent in ("reviewer", "skeptic", "feedback", "implementer"):
        dev_output = task_dir / "developer.md"
        if dev_output.exists():
            files.append(str(dev_output))

    if agent == "implementer":
        plan = task_dir / "plan.md"
        if plan.exists():
            files.append(str(plan))
        review = task_dir / "reviewer.md"
        if review.exists():
            files.append(str(review))

    if agent == "feedback":
        impl_output = task_dir / "implementer.md"
        if impl_output.exists():
            files.append(str(impl_output))

    if agent == "technical_writer":
        # Technical writer needs all prior agent outputs to capture
        # documentation gaps, patterns, and findings from every phase
        for name in [
            "task.md", "architect.md", "developer.md",
            "reviewer.md", "skeptic.md", "implementer.md", "feedback.md",
        ]:
            f = task_dir / name
            if f.exists():
                files.append(str(f))

    # Gemini analysis if available
    gemini = task_dir / "gemini-analysis.md"
    if gemini.exists():
        files.append(str(gemini))

    return files


def _get_checkpoint_for_phase(phase: str, config: dict) -> Optional[str]:
    """Check if a checkpoint is configured after a given phase."""
    checkpoints = config.get("checkpoints", {})

    planning_checkpoints = checkpoints.get("planning", {})
    checkpoint_key = f"after_{phase}"
    if planning_checkpoints.get(checkpoint_key):
        return checkpoint_key

    # Documentation checkpoint
    if phase == "technical_writer":
        doc_checkpoints = checkpoints.get("documentation", {})
        if doc_checkpoints.get("after_technical_writer"):
            return "after_technical_writer"

    return None


# ============================================================================
# Tool 6: crew_parse_agent_output
# ============================================================================

def crew_parse_agent_output(
    agent: str,
    output_text: str,
    task_id: Optional[str] = None
) -> dict[str, Any]:
    """Extract structured data from agent output and update state.

    Parses <docs_needed>, <review_issues>, <recommendation>, <concerns> tags.
    Auto-calls workflow state tools to persist extracted data.

    Args:
        agent: Agent name that produced the output
        output_text: Raw output text from agent
        task_id: Optional task ID

    Returns:
        Extracted data and has_blocking_issues flag
    """
    extracted: dict[str, Any] = {}
    has_blocking_issues = False

    # Parse <docs_needed> (from architect)
    docs_match = re.search(r'<docs_needed>\s*(\[.*?\])\s*</docs_needed>', output_text, re.DOTALL)
    if docs_match:
        try:
            docs = json.loads(docs_match.group(1))
            extracted["docs_needed"] = docs
            if task_id:
                workflow_mark_docs_needed(docs=docs, task_id=task_id)
        except json.JSONDecodeError:
            extracted["docs_needed_parse_error"] = docs_match.group(1)

    # Parse <review_issues> (from reviewer)
    issues_match = re.search(r'<review_issues>\s*(\[.*?\])\s*</review_issues>', output_text, re.DOTALL)
    if issues_match:
        try:
            issues = json.loads(issues_match.group(1))
            extracted["review_issues"] = issues
            for issue in issues:
                if task_id and isinstance(issue, dict):
                    workflow_add_review_issue(
                        issue_type=issue.get("type", "review"),
                        description=issue.get("description", str(issue)),
                        severity=issue.get("severity", "medium"),
                        task_id=task_id
                    )
                elif task_id and isinstance(issue, str):
                    workflow_add_review_issue(issue_type="review", description=issue, task_id=task_id)
            if issues:
                has_blocking_issues = True
        except json.JSONDecodeError:
            extracted["review_issues_parse_error"] = issues_match.group(1)

    # Parse <recommendation> (from reviewer)
    rec_match = re.search(r'<recommendation>\s*(.*?)\s*</recommendation>', output_text, re.DOTALL)
    if rec_match:
        recommendation = rec_match.group(1).strip().upper()
        extracted["recommendation"] = recommendation
        if recommendation == "REVISE":
            has_blocking_issues = True

    # Parse <concerns> (from skeptic)
    concerns_match = re.search(r'<concerns>\s*(\[.*?\])\s*</concerns>', output_text, re.DOTALL)
    if concerns_match:
        try:
            concerns = json.loads(concerns_match.group(1))
            extracted["concerns"] = concerns
            for concern in concerns:
                if task_id and isinstance(concern, dict):
                    severity = concern.get("severity", "medium").lower()
                    workflow_add_concern(
                        source=agent,
                        severity=severity,
                        description=concern.get("description", str(concern)),
                        task_id=task_id
                    )
                    if severity == "critical":
                        has_blocking_issues = True
                elif task_id and isinstance(concern, str):
                    workflow_add_concern(
                        source=agent,
                        severity="medium",
                        description=concern,
                        task_id=task_id
                    )
        except json.JSONDecodeError:
            extracted["concerns_parse_error"] = concerns_match.group(1)

    # Include unaddressed concerns in the return for display at checkpoints
    unaddressed_concerns = []
    if task_id:
        task_dir = find_task_dir(task_id)
        if task_dir:
            state = _load_state(task_dir)
            all_concerns = state.get("concerns", [])
            unaddressed_concerns = [c for c in all_concerns if not c.get("addressed_by")]

    return {
        "agent": agent,
        "extracted": extracted,
        "has_blocking_issues": has_blocking_issues,
        "unaddressed_concerns": unaddressed_concerns,
        "task_id": task_id
    }


# ============================================================================
# Tool 7: crew_get_implementation_action
# ============================================================================

def crew_get_implementation_action(
    task_id: Optional[str] = None,
    last_verification_passed: Optional[bool] = None,
    last_error_output: Optional[str] = None
) -> dict[str, Any]:
    """Step-level implementation loop decisions.

    Determines what the implementer should do next: implement a step,
    verify, retry, escalate, or move on.

    Args:
        task_id: Task identifier
        last_verification_passed: Result of last verification run
        last_error_output: Error output from last verification

    Returns:
        action, step_id, progress info, iteration details
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    progress = state.get("implementation_progress", {
        "total_steps": 0,
        "current_step": 0,
        "steps_completed": []
    })

    effective = config_get_effective(task_id=state.get("task_id"))
    config = effective["config"]
    loop_config = config.get("loop_mode", {})
    loop_enabled = loop_config.get("enabled", False)
    max_per_step = loop_config.get("max_iterations", {}).get("per_step", 10)
    before_escalate = loop_config.get("max_iterations", {}).get("before_escalate", 5)
    verification_method = loop_config.get("verification", {}).get("method", "tests")

    total_steps = progress.get("total_steps", 0)
    current_step = progress.get("current_step", 0)
    steps_completed = progress.get("steps_completed", [])

    # Track iteration count per step in state
    impl_state = state.get("implementation_loop", {})
    current_step_id = f"step_{current_step + 1}"
    step_iterations = impl_state.get("iterations", {}).get(current_step_id, 0)

    # Calculate progress percentage
    progress_percent = 0
    if total_steps > 0:
        progress_percent = round((len(steps_completed) / total_steps) * 100)

    # Check implementation checkpoints
    checkpoints = config.get("checkpoints", {}).get("implementation", {})
    checkpoint_action = None
    if progress_percent >= 25 and checkpoints.get("at_25_percent") and not impl_state.get("checkpoint_25"):
        checkpoint_action = "checkpoint_25"
    elif progress_percent >= 50 and checkpoints.get("at_50_percent") and not impl_state.get("checkpoint_50"):
        checkpoint_action = "checkpoint_50"
    elif progress_percent >= 75 and checkpoints.get("at_75_percent") and not impl_state.get("checkpoint_75"):
        checkpoint_action = "checkpoint_75"

    if checkpoint_action:
        return {
            "action": "checkpoint",
            "checkpoint": checkpoint_action,
            "progress_percent": progress_percent,
            "steps_completed": len(steps_completed),
            "total_steps": total_steps,
            "task_id": state.get("task_id")
        }

    # All steps done?
    if total_steps > 0 and len(steps_completed) >= total_steps:
        # Check before_commit checkpoint
        if checkpoints.get("before_commit") and not impl_state.get("checkpoint_commit"):
            return {
                "action": "checkpoint",
                "checkpoint": "before_commit",
                "progress_percent": 100,
                "task_id": state.get("task_id")
            }
        return {
            "action": "complete",
            "progress_percent": 100,
            "steps_completed": len(steps_completed),
            "total_steps": total_steps,
            "task_id": state.get("task_id")
        }

    # Handle verification result
    if last_verification_passed is True:
        return {
            "action": "next_step",
            "step_id": current_step_id,
            "progress_percent": progress_percent,
            "iteration": step_iterations,
            "task_id": state.get("task_id")
        }

    if last_verification_passed is False and loop_enabled:
        step_iterations += 1

        # Update iteration tracking
        if "implementation_loop" not in state:
            state["implementation_loop"] = {"iterations": {}}
        state["implementation_loop"].setdefault("iterations", {})[current_step_id] = step_iterations
        _save_state(task_dir, state)

        # Check escalation
        if step_iterations >= max_per_step:
            return {
                "action": "escalate",
                "reason": f"Max iterations ({max_per_step}) reached for {current_step_id}",
                "step_id": current_step_id,
                "iteration": step_iterations,
                "progress_percent": progress_percent,
                "task_id": state.get("task_id")
            }

        if step_iterations >= before_escalate:
            return {
                "action": "escalate",
                "reason": f"Escalation threshold ({before_escalate}) reached for {current_step_id}",
                "step_id": current_step_id,
                "iteration": step_iterations,
                "progress_percent": progress_percent,
                "task_id": state.get("task_id")
            }

        # Check for repeated failures (try different approach after 3)
        should_try_different = step_iterations >= 3

        # Check error patterns for known solutions
        known_solution = None
        if last_error_output:
            from .state_tools import workflow_match_error
            match_result = workflow_match_error(error_text=last_error_output, task_id=task_id)
            if match_result.get("match"):
                known_solution = match_result["match"].get("resolution")

        return {
            "action": "retry",
            "step_id": current_step_id,
            "iteration": step_iterations,
            "verification_command": verification_method,
            "should_try_different_approach": should_try_different,
            "known_solution": known_solution,
            "progress_percent": progress_percent,
            "task_id": state.get("task_id")
        }

    # Default: implement the current step
    return {
        "action": "implement_step",
        "step_id": current_step_id,
        "progress_percent": progress_percent,
        "iteration": step_iterations,
        "verification_command": verification_method if loop_enabled else None,
        "loop_mode": loop_enabled,
        "task_id": state.get("task_id")
    }


# ============================================================================
# Tool 8: crew_format_completion
# ============================================================================

def crew_format_completion(
    task_id: Optional[str] = None,
    files_changed: Optional[list[str]] = None
) -> dict[str, Any]:
    """Generate completion output.

    Returns cost summary, commit message suggestion, worktree action,
    and beads cleanup commands.

    Args:
        task_id: Task identifier
        files_changed: List of files changed during implementation

    Returns:
        cost_summary, commit_message, worktree_action, worktree_commands, beads_commands
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": "No active task found" if not task_id else f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    resolved_task_id = state.get("task_id", task_id or "unknown")
    files_changed = files_changed or []

    # Cost summary
    cost_result = workflow_get_cost_summary(task_id=resolved_task_id)

    # Generate commit message
    description = state.get("description", "workflow task")
    mode = state.get("workflow_mode", {}).get("effective", "full")
    file_summary = f"{len(files_changed)} files changed" if files_changed else "files changed"
    commit_message = f"{description}\n\nCompleted via /crew ({mode} mode), {file_summary}"

    # Worktree info
    worktree_result = workflow_get_worktree_info(task_id=resolved_task_id)
    worktree_action = None
    worktree_commands = []

    effective = config_get_effective(task_id=resolved_task_id)
    config = effective["config"]
    cleanup_policy = config.get("worktree", {}).get("cleanup_on_complete", "prompt")

    if worktree_result.get("has_worktree"):
        wt = worktree_result.get("worktree", {})
        branch = wt.get("branch", "")
        base_branch = wt.get("base_branch", "main")
        worktree_action = cleanup_policy
        worktree_commands = [
            f"git checkout {base_branch}",
            f"git merge {branch}",
            f"python3 {_REPO_ROOT / 'scripts' / 'cleanup-worktree.py'} {resolved_task_id} --remove-branch",
        ]

    # Beads commands
    beads_commands = []
    beads_config = config.get("beads", {})
    linked_issue = state.get("linked_issue")

    if beads_config.get("enabled") and linked_issue:
        beads_commands.append(f"bd close {linked_issue}")
        if beads_config.get("add_comments"):
            beads_commands.append(f"bd comments add {linked_issue} 'Completed via /crew workflow {resolved_task_id}'")
        beads_commands.append("bd sync")

    return {
        "task_id": resolved_task_id,
        "cost_summary": cost_result,
        "commit_message": commit_message,
        "worktree_action": worktree_action,
        "worktree_commands": worktree_commands,
        "beads_commands": beads_commands,
        "files_changed": files_changed,
        "mode": mode
    }


# ============================================================================
# Tool 9: crew_get_resume_state
# ============================================================================

def crew_get_resume_state(
    task_id: str
) -> dict[str, Any]:
    """Load complete resume context for a task.

    Args:
        task_id: Task identifier to resume

    Returns:
        resume_point, current_agent, progress_summary, context_files, display_summary
    """
    task_dir = find_task_dir(task_id)
    if not task_dir:
        return {
            "error": f"Task {task_id} not found"
        }

    state = _load_state(task_dir)
    current_phase = state.get("phase")
    phases_completed = state.get("phases_completed", [])
    mode = state.get("workflow_mode", {}).get("effective", "full")
    progress = state.get("implementation_progress", {})

    # Determine resume point
    if current_phase == "implementer" and progress.get("total_steps", 0) > 0:
        resume_point = f"implementation step {progress.get('current_step', 0) + 1}/{progress.get('total_steps', 0)}"
    elif current_phase:
        resume_point = f"phase: {current_phase}"
    else:
        resume_point = "beginning"

    # Get context files for current phase
    context_files = _get_context_files(current_phase or "architect", state, task_dir)

    # Build display summary
    description = state.get("description", "No description")
    completed_str = ", ".join(phases_completed) if phases_completed else "none"
    display_summary = (
        f"Task: {task_id}\n"
        f"Description: {description}\n"
        f"Mode: {mode}\n"
        f"Current phase: {current_phase or 'not started'}\n"
        f"Phases completed: {completed_str}\n"
    )

    if progress.get("total_steps"):
        display_summary += (
            f"Implementation: step {progress.get('current_step', 0)}/{progress['total_steps']} "
            f"({len(progress.get('steps_completed', []))} completed)\n"
        )

    concerns = state.get("concerns", [])
    unresolved = [c for c in concerns if c.get("status") != "addressed"]
    if unresolved:
        display_summary += f"Unresolved concerns: {len(unresolved)}\n"

    return {
        "task_id": task_id,
        "resume_point": resume_point,
        "current_agent": current_phase,
        "phases_completed": phases_completed,
        "mode": mode,
        "progress_summary": {
            "total_steps": progress.get("total_steps", 0),
            "current_step": progress.get("current_step", 0),
            "steps_completed": progress.get("steps_completed", [])
        },
        "context_files": context_files,
        "display_summary": display_summary,
        "has_worktree": state.get("worktree", {}).get("status") == "active" if state.get("worktree") else False
    }


# ============================================================================
# Tool 10: crew_jira_transition
# ============================================================================

def crew_jira_transition(
    task_id: Optional[str] = None,
    hook_name: str = "on_complete",
    issue_key: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve a Jira transition for a lifecycle hook.

    Encapsulates the 6-step Jira transition procedure from crew.md into a
    single deterministic call. Returns a structured action for the LLM to
    execute (or skip).

    Args:
        task_id: Task identifier for config resolution
        hook_name: Lifecycle hook name (on_create, on_complete, on_cleanup)
        issue_key: Jira issue key (e.g., "PROJ-42")

    Returns:
        action (skip/prompt/execute), reason, and transition details
    """
    if not issue_key:
        return {"action": "skip", "reason": "No Jira issue key provided"}

    # Get effective config
    effective = config_get_effective(task_id=task_id)
    config = effective["config"]

    # Navigate to transition config
    jira_config = config.get("worktree", {}).get("jira", {})
    transitions = jira_config.get("transitions", {})
    hook_config = transitions.get(hook_name, {})

    target_status = hook_config.get("to", "")
    mode = hook_config.get("mode", "never")
    only_from = hook_config.get("only_from", [])

    # Check if transition should be skipped
    if not target_status:
        return {
            "action": "skip",
            "reason": f"No target status configured for hook '{hook_name}'",
            "hook_name": hook_name,
        }

    if mode == "never":
        return {
            "action": "skip",
            "reason": f"Mode is 'never' for hook '{hook_name}'",
            "hook_name": hook_name,
        }

    # Build the transition details
    transition_details = {
        "issue_key": issue_key,
        "target_status": target_status,
        "hook_name": hook_name,
        "only_from": only_from,
    }

    if mode == "prompt":
        return {
            "action": "prompt",
            "question": f"Transition {issue_key} to '{target_status}'?",
            **transition_details,
        }

    # mode == "auto"
    return {
        "action": "execute",
        **transition_details,
    }
