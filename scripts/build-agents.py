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
}


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def list_agents() -> list[Path]:
    """Return all agent .md files sorted by name."""
    return sorted(AGENTS_DIR.glob("*.md"))


# ---------------------------------------------------------------------------
# Claude adapter
# ---------------------------------------------------------------------------

def build_claude(output_dir: Path):
    """Build agents in Claude Code format: plain markdown in {output}/agents/."""
    agents_out = output_dir / "agents"
    agents_out.mkdir(parents=True, exist_ok=True)

    preamble_path = PREAMBLES_DIR / "claude.md"
    preamble = read_file(preamble_path) if preamble_path.exists() else ""

    count = 0
    for agent_path in list_agents():
        name = agent_path.stem  # e.g. "architect"
        body = read_file(agent_path)

        if name == "orchestrator":
            content = body
        else:
            content = preamble + "\n" + body

        dest = agents_out / agent_path.name
        dest.write_text(content, encoding="utf-8")
        print(f"  + {agent_path.name}")
        count += 1

    print(f"\n  {count} agents written to {agents_out}")


# ---------------------------------------------------------------------------
# Copilot adapter
# ---------------------------------------------------------------------------

def _copilot_frontmatter(name: str, description: str, *, is_orchestrator: bool = False) -> str:
    """Generate YAML frontmatter for a .agent.md file."""
    lines = [
        "---",
        f"name: crew-{name}",
        f'description: "{description}"',
    ]
    if is_orchestrator:
        lines.append("tools:")
        lines.append('  - "*"')
    lines.append("---")
    return "\n".join(lines) + "\n"


def build_copilot(output_dir: Path):
    """Build agents in Copilot format: .github/agents/crew-*.agent.md with YAML frontmatter."""
    agents_out = output_dir / ".github" / "agents"
    agents_out.mkdir(parents=True, exist_ok=True)

    preamble_path = PREAMBLES_DIR / "copilot.md"
    preamble = read_file(preamble_path) if preamble_path.exists() else ""

    # Build orchestrator from platform-specific template
    orchestrator_path = ORCHESTRATORS_DIR / "copilot.md"
    if orchestrator_path.exists():
        orch_body = read_file(orchestrator_path)
        desc = AGENT_DESCRIPTIONS.get("orchestrator", "Workflow Orchestrator")
        orch_content = _copilot_frontmatter("orchestrator", desc, is_orchestrator=True) + "\n" + orch_body
        dest = agents_out / "crew.agent.md"
        dest.write_text(orch_content, encoding="utf-8")
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
        frontmatter = _copilot_frontmatter(name, desc)

        content = frontmatter + "\n" + preamble + "\n" + body
        dest = agents_out / f"crew-{name}.agent.md"
        dest.write_text(content, encoding="utf-8")
        print(f"  + crew-{name}.agent.md")
        count += 1

    print(f"\n  {count} agents + orchestrator written to {agents_out}")


# ---------------------------------------------------------------------------
# Gemini adapter
# ---------------------------------------------------------------------------

def _gemini_frontmatter(name: str, description: str, tools: list[str]) -> str:
    """Generate YAML frontmatter for a Gemini sub-agent .md file."""
    lines = [
        "---",
        f"name: crew-{name}",
        f'description: "{description}"',
        "kind: local",
    ]
    if tools:
        lines.append("tools:")
        for tool in tools:
            lines.append(f"  - {tool}")
    lines.append("max_turns: 30")
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

        content = frontmatter + "\n" + preamble + "\n" + body
        dest = agents_out / f"crew-{name}.md"
        dest.write_text(content, encoding="utf-8")
        print(f"  + crew-{name}.md")
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

    print(f"\n  {count} agents + orchestrator written to {agents_out}")


# ---------------------------------------------------------------------------
# Platform registry
# ---------------------------------------------------------------------------

PLATFORMS = {
    "claude": {
        "build": build_claude,
        "default_output": lambda: Path.home(),
        "description": "Claude Code — plain .md agents in ~/agents/",
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
