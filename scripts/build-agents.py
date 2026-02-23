#!/usr/bin/env python3
"""
Multi-platform agent builder for agentic-workflow.

Reads shared agent sources from agents/*.md and produces platform-specific
output for Claude Code, GitHub Copilot, or Gemini CLI.

Usage:
    python3 scripts/build-agents.py copilot                        # Build .github/agents/
    python3 scripts/build-agents.py copilot --output /path/to/repo # Build in another repo
    python3 scripts/build-agents.py claude                         # Build to ~/.claude/agents/
    python3 scripts/build-agents.py claude --output /tmp/test      # Build to custom dir
    python3 scripts/build-agents.py --list-platforms               # Show available platforms
"""

import argparse
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
AGENTS_DIR = REPO_ROOT / "agents"
PREAMBLES_DIR = REPO_ROOT / "config" / "platform-preambles"
ORCHESTRATORS_DIR = REPO_ROOT / "config" / "platform-orchestrators"

# Agent name → short description for frontmatter
AGENT_DESCRIPTIONS = {
    "architect": "Senior Software Architect — analyzes system-wide implications",
    "developer": "Senior Developer — creates detailed implementation plans",
    "reviewer": "Plan Reviewer — validates completeness and correctness",
    "skeptic": "Devil's Advocate — stress-tests plans for failure modes",
    "implementer": "Implementer — executes plans step-by-step",
    "feedback": "Feedback Analyst — compares implementation vs plan",
    "technical-writer": "Technical Writer — maintains AI-context documentation",
    "security-auditor": "Security Auditor — finds vulnerabilities (OWASP Top 10)",
    "performance-analyst": "Performance Analyst — identifies bottlenecks and scalability issues",
    "api-guardian": "API Guardian — protects API contracts and backward compatibility",
    "accessibility-reviewer": "Accessibility Reviewer — ensures WCAG compliance",
    "orchestrator": "Workflow Orchestrator — coordinates the multi-agent workflow",
    "crew-worktree": "Worktree Creator — creates isolated git worktrees for parallel crew workflows",
    "crew-status": "Workflow Status — read-only overview of all tasks, worktrees, and model health",
}

# Agents that are invoked as commands rather than sub-agents.
# For Claude: generates commands/{name}.md with $ARGS substitution
# For Copilot/Gemini: generates as regular agents with full tool access
COMMAND_AGENTS = {
    "crew-worktree",
    "crew-status",
}

# Gemini sub-agent tool restrictions per agent role
GEMINI_AGENT_TOOLS = {
    "architect":             ["read_file", "search_file_content", "list_directory"],
    "developer":             ["read_file", "search_file_content", "list_directory"],
    "reviewer":              ["read_file", "search_file_content", "list_directory"],
    "skeptic":               ["read_file", "search_file_content", "list_directory"],
    "implementer":           ["read_file", "write_file", "search_file_content", "list_directory", "run_shell_command"],
    "feedback":              ["read_file", "search_file_content", "list_directory", "run_shell_command"],
    "technical-writer":      ["read_file", "write_file", "search_file_content", "list_directory"],
    "security-auditor":      ["read_file", "search_file_content", "list_directory"],
    "performance-analyst":   ["read_file", "search_file_content", "list_directory", "run_shell_command"],
    "api-guardian":          ["read_file", "search_file_content", "list_directory"],
    "accessibility-reviewer": ["read_file", "search_file_content", "list_directory"],
    "crew-worktree":          ["read_file", "write_file", "list_directory", "run_shell_command"],
    "crew-status":            ["read_file", "list_directory", "run_shell_command"],
}

# OpenCode sub-agent tool restrictions per agent role
# OpenCode uses boolean tool maps: {tool_name: false} to disable
OPENCODE_AGENT_TOOLS = {
    "architect":             {"write": False, "edit": False, "patch": False},
    "developer":             {"write": False, "edit": False, "patch": False},
    "reviewer":              {"write": False, "edit": False, "patch": False},
    "skeptic":               {"write": False, "edit": False, "patch": False},
    "implementer":           {},  # All tools enabled
    "feedback":              {"write": False, "edit": False, "patch": False},
    "technical-writer":      {"patch": False},
    "security-auditor":      {"write": False, "edit": False, "patch": False},
    "performance-analyst":   {"write": False, "edit": False, "patch": False},
    "api-guardian":          {"write": False, "edit": False, "patch": False},
    "accessibility-reviewer": {"write": False, "edit": False, "patch": False},
    "crew-worktree":          {"patch": False},
    "crew-status":            {"write": False, "edit": False, "patch": False},
}

# OpenCode granular bash permissions per agent role.
# Uses glob patterns: {"pattern": "allow"|"ask"|"deny"}.
# Last matching rule wins, so put general patterns first, specific ones last.
# None = no permission block (inherit tool-level bool).
_READ_ONLY_BASH = {
    "*": "deny",
    "git status*": "allow",
    "git log*": "allow",
    "git diff*": "allow",
    "git show*": "allow",
    "git branch*": "allow",
    "grep *": "allow",
    "find *": "allow",
    "ls *": "allow",
    "cat *": "allow",
    "head *": "allow",
    "tail *": "allow",
    "wc *": "allow",
    "tree *": "allow",
}

_FEEDBACK_BASH = {
    **_READ_ONLY_BASH,
    "python3 -m pytest*": "allow",
    "npm test*": "allow",
    "make test*": "allow",
}

_IMPLEMENTER_BASH = {
    "*": "ask",
    "git status*": "allow",
    "git diff*": "allow",
    "git log*": "allow",
    "git add *": "allow",
    "python3 -m pytest*": "allow",
    "npm test*": "allow",
    "npm run*": "allow",
    "make *": "allow",
    "git commit*": "ask",
    "git push*": "deny",
    "git reset --hard*": "deny",
    "git clean*": "deny",
    "rm -rf*": "deny",
}

OPENCODE_AGENT_PERMISSIONS: dict[str, dict | None] = {
    "architect":             {"edit": "deny", "bash": _READ_ONLY_BASH, "webfetch": "deny"},
    "developer":             {"edit": "deny", "bash": _READ_ONLY_BASH, "webfetch": "deny"},
    "reviewer":              {"edit": "deny", "bash": _READ_ONLY_BASH, "webfetch": "deny"},
    "skeptic":               {"edit": "deny", "bash": _READ_ONLY_BASH, "webfetch": "deny"},
    "implementer":           {"bash": _IMPLEMENTER_BASH},
    "feedback":              {"edit": "deny", "bash": _FEEDBACK_BASH, "webfetch": "deny"},
    "technical-writer":      None,  # uses tool-level restrictions only
    "security-auditor":      {"edit": "deny", "bash": _READ_ONLY_BASH, "webfetch": "deny"},
    "performance-analyst":   {"edit": "deny", "bash": _FEEDBACK_BASH, "webfetch": "deny"},
    "api-guardian":          {"edit": "deny", "bash": _READ_ONLY_BASH, "webfetch": "deny"},
    "accessibility-reviewer": {"edit": "deny", "bash": _READ_ONLY_BASH, "webfetch": "deny"},
    "crew-worktree":          None,
    "crew-status":            {"edit": "deny", "bash": _READ_ONLY_BASH},
}


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


PLATFORM_DIRS = {
    "claude": ".claude",
    "copilot": ".copilot",
    "gemini": ".gemini",
    "opencode": ".opencode",  # project-level; global uses .config/opencode/
}

SCRIPTS_DIRS = {
    "claude": "~/.claude/scripts",
    "copilot": str(REPO_ROOT / "scripts"),
    "gemini": str(REPO_ROOT / "scripts"),
    "opencode": str(REPO_ROOT / "scripts"),
}


def _substitute_platform(content: str, platform: str) -> str:
    """Replace {__platform__}, {__platform_dir__}, and {__scripts_dir__} placeholders."""
    content = content.replace("{__platform__}", platform)
    content = content.replace("{__platform_dir__}", PLATFORM_DIRS.get(platform, f".{platform}"))
    content = content.replace("{__scripts_dir__}", SCRIPTS_DIRS.get(platform, "scripts"))
    return content


def _assert_no_raw_placeholders(output_dir: Path, platform: str, written_files: list[Path] | None = None) -> None:
    """Scan built output for raw placeholders that should have been substituted.

    Args:
        output_dir: Root output directory (only used if written_files is None).
        platform: Platform name for error messages.
        written_files: Specific files to check. If None, falls back to scanning
            agents/ and commands/ subdirectories (NOT the entire output_dir tree).
    """
    raw_patterns = ["{__platform__}", "{__platform_dir__}", "{__scripts_dir__}"]
    violations = []

    if written_files:
        files_to_check = written_files
    else:
        # Fallback: scan only the directories we write to, not entire output tree
        files_to_check = []
        for subdir in ("agents", "commands"):
            d = output_dir / f".{platform}" / subdir if platform != "claude" else output_dir / ".claude" / subdir
            if d.exists():
                files_to_check.extend(d.glob("*.md"))

    for md_file in files_to_check:
        content = md_file.read_text(encoding="utf-8")
        for pat in raw_patterns:
            if pat in content:
                violations.append(f"  {md_file}: contains raw {pat}")
    if violations:
        print(f"\nERROR: Raw placeholders found in {platform} build output:", file=sys.stderr)
        for v in violations:
            print(v, file=sys.stderr)
        raise SystemExit(1)


def _write_manifest(output_dir: Path, platform: str, files: list[str]):
    """Write a manifest of files created by the build."""
    from datetime import datetime as _dt
    manifest_path = output_dir / f".agentic-workflow-{platform}.manifest.json"
    manifest = {
        "platform": platform,
        "created_at": _dt.now().isoformat(),
        "files": sorted(files),
    }
    import json as _json
    manifest_path.write_text(_json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"  + manifest: {manifest_path.name}")


def list_agents() -> list[Path]:
    """Return all agent .md files sorted by name."""
    return sorted(AGENTS_DIR.glob("*.md"))


# ---------------------------------------------------------------------------
# Claude adapter
# ---------------------------------------------------------------------------

# Claude command wrappers: appended to command agent content for $ARGS substitution
COMMAND_SUFFIXES = {
    "crew-worktree": "\nNow, process the arguments and create the worktree:\n\nArguments: $ARGS\n",
    "crew-status": "\nNow, scan `.tasks/` directory and **display** (read-only) the status of all workflows with worktree state, context, and model health. Do NOT transition, complete, or advance any workflow. ONLY read and print.\n",
}


def _claude_command_wrap(name: str, body: str) -> str:
    """Wrap agent content as a Claude Code slash command with $ARGS substitution."""
    suffix = COMMAND_SUFFIXES.get(name, "\n\nArguments: $ARGS\n")
    return body.rstrip() + "\n" + suffix


def build_claude(output_dir: Path):
    """Build agents in Claude Code format: plain markdown in {output}/agents/ and commands/."""
    agents_out = output_dir / "agents"
    agents_out.mkdir(parents=True, exist_ok=True)
    commands_out = output_dir / "commands"

    preamble_path = PREAMBLES_DIR / "claude.md"
    preamble = read_file(preamble_path) if preamble_path.exists() else ""

    agent_count = 0
    cmd_count = 0
    command_agent_names: set[str] = set()  # track filenames written as command-agents
    for agent_path in list_agents():
        name = agent_path.stem  # e.g. "architect"
        body = read_file(agent_path)

        if name in COMMAND_AGENTS:
            commands_out.mkdir(parents=True, exist_ok=True)
            content = _substitute_platform(_claude_command_wrap(name, body), "claude")
            dest = commands_out / agent_path.name
            dest.write_text(content, encoding="utf-8")
            command_agent_names.add(agent_path.name)
            print(f"  + commands/{agent_path.name}")
            cmd_count += 1
        else:
            if name == "orchestrator":
                content = body
            else:
                content = preamble + "\n" + body
            content = _substitute_platform(content, "claude")

            dest = agents_out / agent_path.name
            dest.write_text(content, encoding="utf-8")
            print(f"  + agents/{agent_path.name}")
            agent_count += 1

    # Copy main commands from commands/ directory (crew.md, crew-config.md, crew-resume.md)
    # These are the slash commands that drive the workflow, separate from command-agents.
    commands_src = REPO_ROOT / "commands"
    if commands_src.exists():
        commands_out.mkdir(parents=True, exist_ok=True)
        for cmd_path in sorted(commands_src.glob("*.md")):
            # Skip files that were already written as command-agents above
            if cmd_path.name in command_agent_names:
                continue
            content = _substitute_platform(read_file(cmd_path), "claude")
            dest = commands_out / cmd_path.name
            dest.write_text(content, encoding="utf-8")
            print(f"  + commands/{cmd_path.name}")
            cmd_count += 1

    _assert_no_raw_placeholders(output_dir, "claude")
    print(f"\n  {agent_count} agents + {cmd_count} commands written to {output_dir}")


# ---------------------------------------------------------------------------
# Copilot adapter
# ---------------------------------------------------------------------------

def _agent_output_name(name: str) -> str:
    """Return platform output name: add crew- prefix unless name already has it."""
    return name if name.startswith("crew-") else f"crew-{name}"


def _copilot_frontmatter(name: str, description: str, *, is_orchestrator: bool = False) -> str:
    """Generate YAML frontmatter for a .agent.md file."""
    out_name = _agent_output_name(name)
    lines = [
        "---",
        f"name: {out_name}",
        f'description: "{description}"',
    ]
    if is_orchestrator:
        lines.append("tools:")
        lines.append('  - "*"')
    lines.append("---")
    return "\n".join(lines) + "\n"


def _copilot_agents_dir(output_dir: Path) -> Path:
    """Return the Copilot agents directory.

    Copilot stores user-level agents under ~/.copilot/agents/ but project-level
    agents under .github/agents/.  When output_dir is the user's home directory
    (global install), return output_dir / .copilot / agents.  Otherwise
    (project-level install), return output_dir / .github / agents.
    """
    if output_dir == Path.home():
        return output_dir / ".copilot" / "agents"
    return output_dir / ".github" / "agents"


def build_copilot(output_dir: Path):
    """Build agents in Copilot format: .agent.md files with YAML frontmatter.

    Project-level: .github/agents/crew-*.agent.md
    User-level (output==$HOME): ~/.copilot/agents/crew-*.agent.md
    """
    agents_out = _copilot_agents_dir(output_dir)
    agents_out.mkdir(parents=True, exist_ok=True)

    preamble_path = PREAMBLES_DIR / "copilot.md"
    preamble = read_file(preamble_path) if preamble_path.exists() else ""

    written_files: list[Path] = []

    # Build orchestrator from platform-specific template
    orchestrator_path = ORCHESTRATORS_DIR / "copilot.md"
    if orchestrator_path.exists():
        orch_body = read_file(orchestrator_path)
        desc = AGENT_DESCRIPTIONS.get("orchestrator", "Workflow Orchestrator")
        orch_content = _copilot_frontmatter("orchestrator", desc, is_orchestrator=True) + "\n" + orch_body
        dest = agents_out / "crew.agent.md"
        dest.write_text(orch_content, encoding="utf-8")
        written_files.append(dest)
        print(f"  + crew.agent.md (orchestrator)")
    else:
        print(f"  ! No orchestrator template at {orchestrator_path}")

    count = 0
    for agent_path in list_agents():
        name = agent_path.stem
        body = read_file(agent_path)

        if name == "orchestrator":
            # Already handled above from platform-specific template
            continue

        desc = AGENT_DESCRIPTIONS.get(name, f"Crew agent: {name}")
        is_command = name in COMMAND_AGENTS
        frontmatter = _copilot_frontmatter(name, desc, is_orchestrator=is_command)

        out_name = _agent_output_name(name)
        content = _substitute_platform(frontmatter + "\n" + preamble + "\n" + body, "copilot")
        dest = agents_out / f"{out_name}.agent.md"
        dest.write_text(content, encoding="utf-8")
        written_files.append(dest)
        print(f"  + {out_name}.agent.md")
        count += 1

    _assert_no_raw_placeholders(agents_out, "copilot", written_files=written_files)
    print(f"\n  {count} agents + orchestrator written to {agents_out}")


# ---------------------------------------------------------------------------
# Gemini adapter
# ---------------------------------------------------------------------------

# Gemini sub-agent max_turns defaults, matching subagent_limits.max_turns config.
# TODO: Read these from workflow-config.yaml subagent_limits.max_turns section
# instead of hardcoding. For now, these are reasonable defaults that match
# the intended config values.
GEMINI_MAX_TURNS = {
    "architect": 30,
    "developer": 30,
    "reviewer": 30,
    "skeptic": 30,
    "implementer": 50,
    "feedback": 30,
    "technical-writer": 20,
    "security-auditor": 30,
    "performance-analyst": 30,
    "api-guardian": 30,
    "accessibility-reviewer": 30,
    "crew-worktree": 15,
    "crew-status": 10,
}

# Gemini per-agent model selection.
# Pro for complex reasoning agents, Flash for utility/simple agents.
GEMINI_AGENT_MODELS = {
    "architect":              "gemini-2.5-pro",
    "developer":              "gemini-2.5-pro",
    "reviewer":               "gemini-2.5-pro",
    "skeptic":                "gemini-2.5-pro",
    "implementer":            "gemini-2.5-pro",
    "feedback":               "gemini-2.5-pro",
    "technical-writer":       "gemini-2.0-flash",
    "security-auditor":       "gemini-2.5-pro",
    "performance-analyst":    "gemini-2.5-pro",
    "api-guardian":           "gemini-2.5-pro",
    "accessibility-reviewer": "gemini-2.0-flash",
    "orchestrator":           "gemini-2.5-pro",
    "crew-worktree":          "gemini-2.0-flash",
    "crew-status":            "gemini-2.0-flash",
}


def _gemini_frontmatter(name: str, description: str, tools: list[str]) -> str:
    """Generate YAML frontmatter for a Gemini sub-agent .md file."""
    out_name = _agent_output_name(name)
    max_turns = GEMINI_MAX_TURNS.get(name, 30)
    model = GEMINI_AGENT_MODELS.get(name)
    lines = [
        "---",
        f"name: {out_name}",
        f'description: "{description}"',
        "kind: local",
    ]
    if model:
        lines.append(f"model: {model}")
    if tools:
        lines.append("tools:")
        for tool in tools:
            lines.append(f"  - {tool}")
    lines.append(f"max_turns: {max_turns}")
    lines.append("timeout_mins: 10")
    lines.append("---")
    return "\n".join(lines) + "\n"


def build_gemini(output_dir: Path):
    """Build agents in Gemini CLI format: .gemini/agents/*.md with YAML frontmatter."""
    agents_out = output_dir / ".gemini" / "agents"
    agents_out.mkdir(parents=True, exist_ok=True)

    preamble_path = PREAMBLES_DIR / "gemini.md"
    preamble = read_file(preamble_path) if preamble_path.exists() else ""

    # Build orchestrator from platform-specific template
    orchestrator_path = ORCHESTRATORS_DIR / "gemini.md"
    if orchestrator_path.exists():
        orch_body = read_file(orchestrator_path)
        desc = AGENT_DESCRIPTIONS.get("orchestrator", "Workflow Orchestrator")
        orch_fm = _gemini_frontmatter(
            "orchestrator", desc,
            tools=["read_file", "write_file", "search_file_content", "list_directory", "run_shell_command"],
        )
        dest = agents_out / "crew-orchestrator.md"
        dest.write_text(orch_fm + "\n" + orch_body, encoding="utf-8")
        print(f"  + crew-orchestrator.md (orchestrator)")
    else:
        print(f"  ! No orchestrator template at {orchestrator_path}")

    count = 0
    for agent_path in list_agents():
        name = agent_path.stem
        body = read_file(agent_path)

        if name == "orchestrator":
            continue

        desc = AGENT_DESCRIPTIONS.get(name, f"Crew agent: {name}")
        tools = GEMINI_AGENT_TOOLS.get(name, ["read_file", "grep_search", "list_directory"])
        frontmatter = _gemini_frontmatter(name, desc, tools)

        out_name = _agent_output_name(name)
        content = _substitute_platform(frontmatter + "\n" + preamble + "\n" + body, "gemini")
        dest = agents_out / f"{out_name}.md"
        dest.write_text(content, encoding="utf-8")
        print(f"  + {out_name}.md")
        count += 1

    # Generate settings.json with experimental agents enabled
    settings_dir = output_dir / ".gemini"
    settings_path = settings_dir / "settings.json"
    if not settings_path.exists():
        import json
        settings = {
            "experimental": {
                "enableAgents": True
            }
        }
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        print(f"  + settings.json (enableAgents: true)")

    _assert_no_raw_placeholders(output_dir, "gemini")
    print(f"\n  {count} agents + orchestrator written to {agents_out}")


# ---------------------------------------------------------------------------
# OpenCode adapter
# ---------------------------------------------------------------------------

# OpenCode agent profile per command type
OPENCODE_COMMAND_AGENTS = {
    "crew-worktree": "build",    # worktree creation needs write access
    "crew-status": "read",       # status is read-only
}

# OpenCode per-agent model selection (optional).
# Format: "provider/model-id" — depends on user's configured provider.
# Empty string = inherit from opencode.json default model.
# Users can override per-agent in their agent .md files.
OPENCODE_AGENT_MODELS: dict[str, str] = {
    # Reasoning-heavy agents — use the best available model
    "architect":              "",
    "developer":              "",
    "reviewer":               "",
    "skeptic":                "",
    "implementer":            "",
    "feedback":               "",
    "technical-writer":       "",
    "security-auditor":       "",
    "performance-analyst":    "",
    "api-guardian":           "",
    "accessibility-reviewer": "",
    "orchestrator":           "",
    # Utility agents — could use a cheaper/faster model
    "crew-worktree":          "",
    "crew-status":            "",
}


def _opencode_frontmatter(name: str, description: str, tools: dict[str, bool],
                           model: str = "",
                           permission: dict | None = None) -> str:
    """Generate YAML frontmatter for an OpenCode agent .md file.

    Args:
        permission: Granular permission map. Values are either a string
            ("allow"/"ask"/"deny") for simple tool permissions, or a dict
            of glob→action for bash commands.
    """
    lines = [
        "---",
        f'description: "{description}"',
        "mode: subagent",
    ]
    if model:
        lines.append(f"model: {model}")
    if tools:
        lines.append("tools:")
        for tool_name, enabled in tools.items():
            lines.append(f"  {tool_name}: {str(enabled).lower()}")
    if permission:
        lines.append("permission:")
        for tool_name, rule in permission.items():
            if isinstance(rule, str):
                lines.append(f"  {tool_name}: {rule}")
            elif isinstance(rule, dict):
                lines.append(f"  {tool_name}:")
                for pattern, action in rule.items():
                    lines.append(f'    "{pattern}": {action}')
    lines.append("---")
    return "\n".join(lines) + "\n"


def _opencode_base(output_dir: Path) -> Path:
    """Return the OpenCode config base directory.

    OpenCode stores global config under ~/.config/opencode/ but project-level
    config under .opencode/.  When output_dir is the user's home directory
    (global install), return output_dir / .config / opencode.  Otherwise
    (project-level install), return output_dir / .opencode.
    """
    if output_dir == Path.home():
        return output_dir / ".config" / "opencode"
    return output_dir / ".opencode"


def build_opencode(output_dir: Path):
    """Build agents in OpenCode format: .opencode/agents/*.md and .opencode/commands/*.md."""
    oc_base = _opencode_base(output_dir)
    agents_out = oc_base / "agents"
    agents_out.mkdir(parents=True, exist_ok=True)

    preamble_path = PREAMBLES_DIR / "opencode.md"
    preamble = read_file(preamble_path) if preamble_path.exists() else ""

    written_files: list[Path] = []

    # Build orchestrator from platform-specific template
    orchestrator_path = ORCHESTRATORS_DIR / "opencode.md"
    if orchestrator_path.exists():
        orch_body = read_file(orchestrator_path)
        desc = AGENT_DESCRIPTIONS.get("orchestrator", "Workflow Orchestrator")
        # OpenCode orchestrator is a primary agent (not subagent)
        orch_fm = (
            "---\n"
            f'description: "{desc}"\n'
            "mode: primary\n"
            "---\n"
        )
        dest = agents_out / "crew.md"
        dest.write_text(orch_fm + "\n" + orch_body, encoding="utf-8")
        written_files.append(dest)
        print(f"  + crew.md (orchestrator)")
    else:
        print(f"  ! No orchestrator template at {orchestrator_path}")

    # Build command agents as OpenCode commands
    commands_out = oc_base / "commands"

    count = 0
    cmd_count = 0
    for agent_path in list_agents():
        name = agent_path.stem
        body = read_file(agent_path)

        if name == "orchestrator":
            continue

        desc = AGENT_DESCRIPTIONS.get(name, f"Crew agent: {name}")

        if name in COMMAND_AGENTS:
            # Command agents go to commands/ with command frontmatter
            commands_out.mkdir(parents=True, exist_ok=True)
            out_name = _agent_output_name(name)
            agent_profile = OPENCODE_COMMAND_AGENTS.get(name, "build")
            cmd_fm = (
                "---\n"
                f'description: "{desc}"\n'
                f"agent: {agent_profile}\n"
                "subtask: true\n"
                "---\n"
            )
            suffix = COMMAND_SUFFIXES.get(name, "\n\nArguments: $ARGUMENTS\n")
            content = _substitute_platform(
                cmd_fm + "\n" + preamble + "\n" + body.rstrip() + "\n" + suffix.replace("$ARGS", "$ARGUMENTS"),
                "opencode"
            )
            dest = commands_out / f"{out_name}.md"
            dest.write_text(content, encoding="utf-8")
            written_files.append(dest)
            print(f"  + commands/{out_name}.md")
            cmd_count += 1
        else:
            # Regular agents go to agents/
            tools = OPENCODE_AGENT_TOOLS.get(name, {})
            model = OPENCODE_AGENT_MODELS.get(name, "")
            perm = OPENCODE_AGENT_PERMISSIONS.get(name)
            frontmatter = _opencode_frontmatter(name, desc, tools, model=model, permission=perm)

            out_name = _agent_output_name(name)
            content = _substitute_platform(frontmatter + "\n" + preamble + "\n" + body, "opencode")
            dest = agents_out / f"{out_name}.md"
            dest.write_text(content, encoding="utf-8")
            written_files.append(dest)
            print(f"  + {out_name}.md")
            count += 1

    # Copy main commands from commands/ directory (crew.md, crew-config.md, crew-resume.md)
    # These are the slash commands that drive the workflow, separate from command-agents.
    commands_src = REPO_ROOT / "commands"
    if commands_src.exists():
        commands_out.mkdir(parents=True, exist_ok=True)
        for cmd_path in sorted(commands_src.glob("*.md")):
            body = read_file(cmd_path)
            # Substitute $ARGS → $ARGUMENTS for OpenCode's variable syntax
            content = body.replace("$ARGS", "$ARGUMENTS")
            content = _substitute_platform(content, "opencode")
            dest = commands_out / cmd_path.name
            dest.write_text(content, encoding="utf-8")
            written_files.append(dest)
            print(f"  + commands/{cmd_path.name}")
            cmd_count += 1

    _assert_no_raw_placeholders(oc_base, "opencode", written_files=written_files)
    print(f"\n  {count} agents + {cmd_count} commands + orchestrator written to {oc_base}")


# ---------------------------------------------------------------------------
# Platform registry
# ---------------------------------------------------------------------------

PLATFORMS = {
    "claude": {
        "build": build_claude,
        "default_output": lambda: Path.home() / ".claude",
        "description": "Claude Code — plain .md agents in ~/.claude/agents/",
    },
    "copilot": {
        "build": build_copilot,
        "default_output": lambda: Path.cwd(),
        "description": "GitHub Copilot — .agent.md files in .github/agents/",
    },
    "gemini": {
        "build": build_gemini,
        "default_output": lambda: Path.home(),
        "description": "Gemini CLI — sub-agent .md files in ~/.gemini/agents/",
    },
    "opencode": {
        "build": build_opencode,
        "default_output": lambda: Path.home(),
        "description": "OpenCode — agent .md files in ~/.config/opencode/agents/",
    },
}


def main():
    parser = argparse.ArgumentParser(
        description="Build platform-specific agent files from shared sources."
    )
    parser.add_argument(
        "platform",
        nargs="?",
        choices=list(PLATFORMS.keys()),
        help="Target platform to build for",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output directory (default depends on platform)",
    )
    parser.add_argument(
        "--list-platforms",
        action="store_true",
        help="List available platforms and exit",
    )

    args = parser.parse_args()

    if args.list_platforms:
        print("Available platforms:\n")
        for name, info in PLATFORMS.items():
            print(f"  {name:10s}  {info['description']}")
        print()
        return

    if not args.platform:
        parser.print_help()
        sys.exit(1)

    platform = PLATFORMS[args.platform]
    output_dir = args.output or platform["default_output"]()

    if not AGENTS_DIR.exists():
        print(f"Error: agents directory not found: {AGENTS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Building agents for {args.platform}...")
    print(f"  Source:  {AGENTS_DIR}")
    print(f"  Output:  {output_dir}")
    print()

    platform["build"](output_dir)
    print("\nDone.")


if __name__ == "__main__":
    main()
