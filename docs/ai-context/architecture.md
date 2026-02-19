# Architecture & Patterns

Detailed architecture reference for AI agents working on the agentic-workflow codebase.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  AI Host CLI (Claude Code / Copilot / Gemini)               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  /crew command (commands/crew.md)                     │  │
│  │  Orchestrates the agent loop, spawns subagents        │  │
│  └───────────────┬───────────────────────────────────────┘  │
│                  │ MCP tool calls                            │
│  ┌───────────────▼───────────────────────────────────────┐  │
│  │  MCP Server (agentic-workflow-server)                  │  │
│  │  ┌─────────────┐ ┌──────────────┐ ┌────────────────┐ │  │
│  │  │ state_tools  │ │ config_tools │ │ orchestration  │ │  │
│  │  │             │ │              │ │ _tools         │ │  │
│  │  └──────┬──────┘ └──────┬───────┘ └───────┬────────┘ │  │
│  │         │               │                  │          │  │
│  │         ▼               ▼                  ▼          │  │
│  │    .tasks/TASK_XXX/   config cascade    crew_* helpers│  │
│  │    state.json         (4 levels)        (arg parsing, │  │
│  │    *.md outputs                          phase loop)  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## MCP Server Internals

### state_tools.py — The Core (~3800 lines)

This is the largest and most important module. It manages all persistent workflow state.

**Key functions and their groupings:**

#### Task Lifecycle
- `workflow_initialize(task_id, description)` — Creates `.tasks/TASK_XXX/state.json`
- `workflow_transition(to_phase)` — Validates and records phase transitions
- `workflow_get_state(task_id)` — Returns current state
- `workflow_complete_phase()` — Marks current phase done, advances to next
- `workflow_is_complete()` — Checks if all phases are done

#### Implementation Progress
- `workflow_set_implementation_progress(total_steps, current_step)` — Track build progress
- `workflow_complete_step(step_id)` — Mark a plan step as done

#### Worktree Management
- `workflow_create_worktree(task_id, base_branch, ai_host)` — Records worktree metadata, returns git commands
- `workflow_get_launch_command(task_id, terminal_env, ai_host, main_repo_path, launch_mode)` — Generates platform-specific terminal launch commands
- `workflow_get_worktree_info(task_id)` — Check worktree status
- `workflow_cleanup_worktree(task_id)` — Mark cleaned, return cleanup commands

#### Discovery & Memory
- `workflow_save_discovery(category, content)` — Persist a learning to JSONL
- `workflow_get_discoveries(category?)` — Retrieve learnings
- `workflow_flush_context()` — Get all learnings grouped by category
- `workflow_search_memories(query, category?, max_results?)` — Cross-task search

#### Concerns & Review
- `workflow_add_concern(agent, severity, description)` — Record a concern
- `workflow_address_concern(concern_id, resolution)` — Mark concern addressed
- `workflow_add_review_issue(agent, severity, description)` — Add blocking issue

#### Human Decisions
- `workflow_add_human_decision(decision, context)` — Record checkpoint outcome

#### Parallel Execution
- `workflow_start_parallel_phase(phase_name)` — Begin parallel agent execution
- `workflow_complete_parallel_phase(phase_name, output)` — Record parallel output
- `workflow_merge_parallel_results(phase_names)` — Deduplicate and merge

#### Quality & Error Patterns
- `workflow_add_assertion(name, check)` / `workflow_verify_assertion(name)` — Quality gates
- `workflow_record_error_pattern(error, solution)` / `workflow_match_error(error)` — Error learning

#### Cost Tracking
- `workflow_record_cost(agent, model, input_tokens, output_tokens)` — Per-agent cost
- `workflow_get_cost_summary()` — Breakdown by agent and model

#### Mode & Effort
- `workflow_detect_mode(description)` — Auto-detect workflow mode from task text
- `workflow_set_mode(mode)` / `workflow_get_mode()` — Manual mode control
- `workflow_get_effort_level(agent)` — Recommended thinking depth per mode

**Internal helpers (prefixed with `_`):**
- `_load_state(task_dir)` / `_save_state(task_dir, state)` — JSON I/O with file locking
- `_build_resume_prompt(task_id, path, ai_host)` — Platform-specific resume prompt
- `find_task_dir(task_id)` — Locate `.tasks/TASK_XXX/` directory

### config_tools.py — Configuration (~900 lines)

**`DEFAULT_CONFIG` dict** (line ~24) — All settings with defaults. This is the source of truth for what settings exist.

Key config sections:
- `checkpoints` — Which human approval points are active per phase
- `knowledge_base` — Path to AI context docs (default: `docs/ai-context/`)
- `models` — Which AI model each agent uses
- `worktree` — Worktree settings (base_path, auto_launch, terminal_launch_mode, ai_host, jira, etc.)
- `auto_actions` — What agents can do without asking (run_tests, git_add, etc.)
- `loop_mode` — Autonomous execution settings
- `max_iterations` — Retry limits per phase type

**`config_get_effective(task_id?)`** — Returns merged config from all 4 cascade levels.

**Multi-platform config paths** — The server searches for config files in Claude, Copilot, and Gemini config directories (in that preference order).

### orchestration_tools.py — Crew Helpers (~1400 lines)

High-level functions called by the `/crew` command and `scripts/crew_orchestrator.py`:

- `crew_parse_args(raw_args)` — Parse command arguments (action, task description, options)
- `crew_init_task(description, options)` — Full task initialization (config, state, mode, KB inventory)
- `crew_get_next_phase(task_id)` — Returns next action: spawn_agent, checkpoint, complete
- `crew_parse_agent_output(agent, output_text)` — Extract issues and recommendations
- `crew_get_implementation_action(task_id, verification_passed?, error_output?)` — Implementation loop logic
- `crew_format_completion(task_id, files_changed)` — Final summary, commit message, cleanup
- `crew_jira_transition(task_id, hook_name, issue_key)` — Resolve Jira lifecycle transition (skip/prompt/execute)
- `crew_get_resume_state(task_id)` — Load resume context for a paused task

### scripts/crew_orchestrator.py — CLI Routing (~280 lines)

CLI script that batches multiple MCP tool calls into single instant JSON decisions, replacing LLM interpretation of procedural routing logic. Subcommands:

- `init --args "..."` — Parse args → init task → get first phase (replaces 3 LLM turns)
- `next --task-id X` — Get next phase/action
- `agent-done --task-id X --agent A` — Parse output → complete phase → record cost → get next (replaces 4 LLM turns)
- `checkpoint-done --task-id X --decision D` — Record decision → get next
- `impl-action --task-id X` — Implementation loop step
- `complete --task-id X` — Format completion + resolve Jira transitions
- `resume --task-id X` — Load resume context + get next phase

### server.py — MCP Registration (~1500 lines)

Registers all tools with the MCP protocol. Each tool has:
- A `Tool()` object with name, description, and JSON Schema for parameters
- A dispatch entry mapping tool name to function

**Pattern for adding new tools:**
1. Import the function from state_tools/config_tools
2. Add a `Tool()` entry in the tools list (~line 200+) with the input schema
3. Add dispatch entry in the `_TOOL_DISPATCH` dict (~line 1500+)

### resources.py — MCP Resources (~200 lines)

Exposes project files as MCP resources that agents can read:
- Agent prompt files from `agents/`
- Configuration files from `config/`
- Documentation from `docs/ai-context/`

## State Management Pattern

### state.json Structure

```json
{
  "task_id": "TASK_002",
  "phase": "implementer",
  "phases_completed": ["architect", "developer", "reviewer", "skeptic"],
  "review_issues": [],
  "iteration": 1,
  "docs_needed": [],
  "implementation_progress": {
    "total_steps": 20,
    "current_step": 13,
    "steps_completed": ["1.1", "1.2", "2.1"]
  },
  "human_decisions": [],
  "concerns": [],
  "worktree": {
    "status": "active",
    "path": "../repo-worktrees/TASK_002",
    "branch": "crew/feature-name",
    "base_branch": "main",
    "color_scheme_index": 2,
    "launch": {
      "terminal_env": "windows_terminal",
      "ai_host": "claude",
      "launch_mode": "tab",
      "launched_at": "2026-02-18T07:20:10",
      "worktree_abs_path": "/path/to/worktree",
      "color_scheme": "Crew Sunset"
    }
  },
  "description": "task description text",
  "created_at": "...",
  "updated_at": "..."
}
```

**File locking**: `_save_state()` uses `filelock` to prevent concurrent writes. Lock files are `state.json.lock`.

### Agent Output Files

Each agent writes its output to `.tasks/TASK_XXX/<agent>.md`. These accumulate and are passed as context to subsequent agents.

## Configuration Pattern

### Adding a New Setting

Follow this checklist:

1. **Default**: Add to `DEFAULT_CONFIG` in `config_tools.py`
2. **Reference**: Add to `config/workflow-config.yaml` with inline comment
3. **Usage**: Read via `config_get_effective()` in the consuming code
4. **Schema**: If exposed as MCP tool parameter, add to `server.py` Tool schema
5. **Tests**: Add to `tests/test_config_tools.py`
6. **Docs**: Update agent docs if it affects agent behavior

### Config Validation

`config_get_effective()` warns about unknown keys but doesn't reject them. The `_get_valid_keys()` helper recursively collects valid keys from `DEFAULT_CONFIG`.

## Agent System Pattern

### Agent Definition Structure

Each agent is a markdown file in `agents/` with:
- Role description and personality
- Input format (what context they receive)
- Analysis steps / checklist
- Output format (structured markdown)
- Permissions (read-only vs read-write)
- Completion signals (promise tags)

### Platform Mirroring

`scripts/build-agents.py` generates platform-specific copies:
- `mcp/agentic-workflow-server/.github/agents/crew-*.agent.md` — For Copilot
- Gemini equivalents in their config dir

**Do not edit mirror files directly.** Edit `agents/` source and run the build script.

### Agent Preambles

Each platform prepends a preamble (`config/platform-preambles/`) that adapts tool names, permissions syntax, and conventions to the specific platform.

## Worktree Pattern

### Launch Flow

1. Agent detects terminal: tmux → windows_terminal → macos → linux_generic
2. `workflow_create_worktree()` records metadata, returns git commands
3. Agent executes git commands (worktree add, branch create)
4. Agent runs setup (symlink .tasks, copy settings, fix paths, install deps)
5. `workflow_get_launch_command()` generates platform-specific launch command
6. Agent executes the launch command

### Color Schemes

8 schemes cycle by task number (defined in `state_tools.py:CREW_COLOR_SCHEMES`):
- Crew Ocean, Forest, Sunset, Amethyst, Steel, Ember, Frost, Earth
- Applied as tab colors in Windows Terminal, window-style in tmux

### Terminal Launch Modes

`terminal_launch_mode` setting (in `worktree` config):
- `auto` — Platform default (tmux→window, WT→tab, macOS→window)
- `window` — Force `wt.exe new-window` on Windows Terminal
- `tab` — Force `wt.exe new-tab` on Windows Terminal

tmux and macOS always use windows regardless of this setting.

## Testing Patterns

### Test Organization

```
tests/
├── test_state_tools.py          # Core state, worktree, launch, resume tests
├── test_state_tools_extended.py # Additional state tests (assertions, errors, etc.)
├── test_config_tools.py         # Config loading, cascade, platform paths
├── test_config_tools_extended.py # Additional config edge cases
├── test_orchestration_tools.py  # Crew helpers (arg parsing, phase routing, Jira transition)
├── test_crew_orchestrator.py    # CLI orchestrator script (subprocess tests)
├── test_resources.py            # MCP resource tests
└── conftest.py                  # Shared fixtures
```

### Key Fixture

```python
@pytest.fixture
def clean_tasks_dir(tmp_path, monkeypatch):
    """Creates a temp .tasks/ dir and patches find_task_dir to use it."""
```

All tests use this to avoid polluting real state.

### Running Tests

```bash
cd mcp/agentic-workflow-server
python3 -m pytest tests/ -v                    # All (463+ tests)
python3 -m pytest tests/test_state_tools.py -v # One file
python3 -m pytest tests/test_state_tools.py::TestLaunchMode -v  # One class
python3 -m pytest tests/ -k "test_tmux" -v     # By name pattern
```

## Common Gotchas

1. **LF line endings**: The `.git` pointer file in worktrees MUST be LF, not CRLF. Always use `printf` to write it, never echo or file-write tools.

2. **Agent mirror files**: Files in `.github/agents/` are auto-generated by `build-agents.py`. Edit the source in `agents/` instead.

3. **State file locking**: `state.json` uses filelock. If a lock file is stale, delete `state.json.lock`.

4. **Config cascade order**: Claude dirs are searched first, then Copilot, then Gemini. The first found wins at each level.

5. **Worktree .tasks/ symlink**: In worktrees, `.tasks/` is a symlink to the main repo. MCP tools resolve this automatically via `find_task_dir()`, but direct file reads should use the absolute main repo path.

6. **`shlex.quote()`**: All user-provided strings in launch commands are quoted via `shlex.quote()` to prevent injection.
