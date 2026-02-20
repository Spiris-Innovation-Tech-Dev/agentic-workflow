# AI Context: Agentic Development Workflow

This directory helps AI agents understand and work with this codebase. Read this file first, then consult specific docs as needed.

## Available Documentation

| File | Purpose |
|------|---------|
| [README.md](./README.md) | Project overview, structure, and getting started (this file) |
| [architecture.md](./architecture.md) | Detailed architecture, patterns, and conventions |
| [cross-platform.md](./cross-platform.md) | Cross-platform patterns: 4 AI hosts, Windows/WSL/macOS, fallbacks |
| [memory-preservation.md](./memory-preservation.md) | How to save/retrieve discoveries across context compaction |

---

## What This Project Is

The **Agentic Development Workflow** is a multi-agent orchestration system for software development. It coordinates specialized AI agents — architect, developer, reviewer, skeptic, implementer, feedback, and technical-writer — through a structured pipeline that plans, reviews, builds, verifies, and documents code changes.

It runs on **four platforms**: Claude Code (Anthropic), GitHub Copilot CLI, Gemini CLI, and OpenCode — using the same agent definitions and workflow configuration across all of them.

The core infrastructure is an **MCP server** (Model Context Protocol) written in Python that manages workflow state, configuration, and orchestration logic.

## Repository Structure

```
agentic-workflow/
├── agents/                     # Agent prompt definitions (markdown)
│   ├── architect.md            # System design & risk analysis
│   ├── developer.md            # Implementation planning
│   ├── reviewer.md             # Code review & gap detection
│   ├── skeptic.md              # Failure mode analysis
│   ├── implementer.md          # Code execution (the only code-writing agent)
│   ├── feedback.md             # Plan-vs-reality comparison
│   ├── technical-writer.md     # Documentation updates
│   ├── crew-worktree.md        # Worktree creation flow
│   ├── crew-status.md          # Workflow status display
│   ├── security-auditor.md     # Optional: security review
│   ├── performance-analyst.md  # Optional: performance review
│   ├── api-guardian.md         # Optional: API contract protection
│   └── accessibility-reviewer.md # Optional: a11y review
├── commands/                   # Slash-command definitions
│   ├── crew.md                 # Main /crew command (orchestrator)
│   ├── crew-config.md          # /crew-config command
│   ├── crew-resume.md          # /crew-resume command
│   ├── crew-checkpoint.md      # /crew-checkpoint command (save workflow checkpoint)
│   └── crew-cost-report.md     # /crew-cost-report command (cost breakdown)
├── crew-board/                 # Norton Commander-style TUI dashboard (Rust)
│   ├── Cargo.toml              # Rust project manifest (ratatui + crossterm)
│   ├── CLAUDE.md               # Agent instructions for this sub-project
│   ├── README.md               # User docs (install, usage, keybindings)
│   └── src/                    # TUI source: app, data layer, UI views, launcher
├── config/
│   ├── workflow-config.yaml    # Reference configuration with all settings
│   ├── terminal-colorschemes.json  # Color schemes for worktree tabs
│   ├── hooks-settings.json     # Claude Code lifecycle hooks (PreToolUse + Stop)
│   ├── platform-orchestrators/ # Platform-specific orchestrator prompts
│   │   ├── copilot.md
│   │   ├── gemini.md
│   │   └── opencode.md
│   └── platform-preambles/     # Platform-specific agent preambles
│       ├── claude.md
│       ├── copilot.md
│       ├── gemini.md
│       └── opencode.md
├── mcp/agentic-workflow-server/  # MCP server (Python)
│   ├── agentic_workflow_server/
│   │   ├── server.py           # MCP tool registration & dispatch
│   │   ├── state_tools.py      # Workflow state management (~3800 lines)
│   │   ├── config_tools.py     # Configuration cascade & defaults
│   │   ├── orchestration_tools.py  # High-level crew orchestration helpers
│   │   └── resources.py        # MCP resource providers
│   ├── tests/                  # pytest test suite (432+ tests)
│   └── pyproject.toml          # Package metadata (v0.4.0)
├── scripts/                    # Helper scripts
│   ├── build-agents.py         # Builds platform-specific agent files
│   ├── setup-worktree.py       # Worktree creation (standalone, no MCP imports)
│   ├── cleanup-worktree.py     # Worktree cleanup helper
│   ├── crew_orchestrator.py    # CLI orchestrator (batches MCP calls)
│   ├── fix-worktree-paths.py   # WSL path compatibility fix
│   ├── shared_utils.py         # Shared utilities (is_wsl, find_repo_root)
│   ├── gemini-trust.py         # Standalone Gemini trustedFolders helper
│   ├── install-wt-colorschemes.py  # Windows Terminal color scheme installer
│   ├── context_preparation.py  # Gemini research prep
│   ├── validate-transition.py  # Workflow transition validator
│   ├── check-workflow-complete.py  # Completion checker
│   └── workflow_state.py       # State utilities
├── docs/
│   ├── overview.md             # Non-technical overview (for managers)
│   └── ai-context/             # AI-agent-facing documentation (this dir)
├── .beads/                     # Issue tracker data (beads/bd)
├── .tasks/                     # Per-task workflow state (symlink in worktrees)
├── install.sh                  # Claude installer (primary)
├── install-copilot.sh          # Copilot installer
├── install-gemini.sh           # Gemini installer
├── install-opencode.sh         # OpenCode installer
├── uninstall.sh                # Claude uninstaller
├── uninstall-copilot.sh        # Copilot uninstaller
├── uninstall-gemini.sh         # Gemini uninstaller
├── uninstall-opencode.sh       # OpenCode uninstaller
├── plugin.json                 # Plugin manifest
├── AGENTS.md                   # Agent instructions for working in this repo
├── CLAUDE.md                   # Points to AGENTS.md
└── VERSION                     # Current version
```

## Key Concepts

### Workflow Phases

Every task flows through phases in order:

1. **Architect** — Analyzes system impact, risks, constraints (read-only)
2. **Developer** — Creates step-by-step implementation plan (read-only)
3. **Reviewer** — Checks plan for gaps and correctness (read-only)
4. **Skeptic** — Stress-tests for failure modes (read-only)
5. **Implementer** — Executes the plan, writes code (read-write)
6. **Feedback** — Compares built code vs approved plan (read-only)
7. **Technical Writer** — Updates documentation (docs-only write)

Human checkpoints occur between phases (configurable).

### Workflow Modes

Not all tasks need all agents:

| Mode | Agents | Use For |
|------|--------|---------|
| **full** | All 7 + optional specialists | Security, DB migrations, critical systems |
| **fast** | Architect → Developer → Reviewer → Implementer → Writer | Multi-module changes |
| **turbo** | Developer → Implementer → Writer | Standard features |
| **minimal** | Developer → Implementer → Writer (fewer checkpoints) | Typo fixes, renames |

Mode is auto-detected from the task description or set explicitly.

### Task State

Each task gets a directory under `.tasks/TASK_XXX/` containing:

- `state.json` — Current phase, progress, decisions, worktree info
- `task.md` — Task description
- `architect.md`, `developer.md`, etc. — Agent outputs
- `plan.md` — Final implementation plan
- `config.yaml` — Task-specific config overrides
- `memory/discoveries.jsonl` — Persistent learnings

### Configuration Cascade

Settings flow through four levels (later overrides earlier):

1. **Defaults** — Hardcoded in `config_tools.py:DEFAULT_CONFIG`
2. **Global** — `~/<platform_dir>/workflow-config.yaml` (searched in order: `.claude`, `.copilot`, `.gemini`, `.config/opencode`, `.opencode`)
3. **Project** — `<repo>/<platform_dir>/workflow-config.yaml` (same search order)
4. **Task** — `.tasks/TASK_XXX/config.yaml`

Reference config with all settings and inline docs: `config/workflow-config.yaml`

### Worktree System

Parallel workflows run in isolated git worktrees:

- `/crew-worktree "task description"` creates a worktree, branches from current branch
- Each worktree gets a unique color scheme for visual distinction
- `.tasks/` is symlinked back to the main repo
- Terminal auto-launch supports tmux (new window), Windows Terminal (new tab/window), macOS (new window)
- `terminal_launch_mode` config controls window vs tab behavior

## MCP Server

The MCP server (`mcp/agentic-workflow-server/`) is the backbone. It exposes tools via the Model Context Protocol that AI agents call to manage workflows.

### Key Modules

| Module | Responsibility | Size |
|--------|---------------|------|
| `state_tools.py` | All workflow state: initialize, transition, worktree, launch, discoveries, assertions, costs | ~3800 lines |
| `config_tools.py` | Configuration loading, cascade, defaults, validation | ~900 lines |
| `orchestration_tools.py` | High-level crew helpers: arg parsing, phase routing, implementation actions | ~2600 lines |
| `server.py` | MCP tool registration, schema definitions, dispatch | ~1500 lines |
| `resources.py` | MCP resource providers (agent prompts, config files) | ~200 lines |

### Running Tests

```bash
cd mcp/agentic-workflow-server
python3 -m pytest tests/ -v           # All tests
python3 -m pytest tests/test_state_tools.py::TestAutoLaunch -v  # Specific class
```

Tests use a `clean_tasks_dir` pytest fixture that creates a temp `.tasks/` directory.

## Issue Tracking

This project uses **beads** (`bd` CLI) for issue tracking. Issues live in `.beads/issues.jsonl`.

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync --from-main   # Pull beads updates from main branch
```

## Cross-Platform Support

Agent prompts are platform-agnostic markdown. Platform differences are handled by:

- **Preambles** (`config/platform-preambles/`) — Prepended to agent prompts per platform
- **Orchestrators** (`config/platform-orchestrators/`) — Platform-specific orchestration instructions
- **build-agents.py** — Generates platform-specific agent files with correct frontmatter, tool restrictions, and output paths per platform. Routes global installs to platform-specific directories (`~/.copilot/agents/`, `~/.config/opencode/`, etc.)

Commands differ by platform:
- Claude: `/crew "task"`, `/crew-worktree "task"`
- OpenCode: `/crew "task"`, `/crew-worktree "task"` (uses `$ARGUMENTS` instead of `$ARGS`)
- Copilot: `@crew "task"`, `@crew-worktree "task"`
- Gemini: `@crew-orchestrator "task"`, `@crew-worktree "task"`

See [cross-platform.md](./cross-platform.md) for detailed platform configuration reference (MCP keys, agent frontmatter, directory routing).

## Quick Reference for Making Changes

### Adding a new config setting
1. Add default to `config_tools.py:DEFAULT_CONFIG`
2. Add to `config/workflow-config.yaml` with inline docs
3. Use it in the relevant module (state_tools.py, orchestration_tools.py)
4. Add to MCP tool schema in `server.py` if exposed as a tool parameter
5. Add tests
6. Update agent docs if the setting affects agent behavior

### Adding a new MCP tool
1. Implement the function in the appropriate module (state_tools.py or config_tools.py)
2. Register in `server.py` — add Tool() schema definition and dispatch entry
3. Add tests
4. Update `docs/ai-context/README.md` if user-facing

### Modifying agent behavior
1. Edit the markdown file in `agents/`
2. Run `scripts/build-agents.py <platform>` to regenerate platform-specific copies
3. All output files are auto-generated — don't edit them directly (`.github/agents/`, `~/.copilot/agents/`, `~/.gemini/agents/`, `~/.config/opencode/`, `.opencode/`)

### Adding tests
- Tests go in `mcp/agentic-workflow-server/tests/`
- Use `clean_tasks_dir` fixture for isolated state
- Follow existing patterns in `test_state_tools.py`
