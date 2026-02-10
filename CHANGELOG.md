# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-02-10

### Added
- **Git worktree support** — `/crew-worktree` creates isolated worktrees per task, enabling parallel workflows on the same repo without file conflicts
- `/crew-worktree` available on all 3 platforms: Claude Code (slash command), Copilot CLI (`@crew-worktree`), Gemini CLI (`@crew-worktree`)
- Single source `agents/crew-worktree.md` → build script generates platform-specific output
- `COMMAND_AGENTS` concept in `build-agents.py` — command-type agents generate slash commands for Claude and full-access agents for Copilot/Gemini
- 3 new MCP tools: `workflow_create_worktree`, `workflow_get_worktree_info`, `workflow_cleanup_worktree` (record metadata and return git commands; do not execute git directly)
- Worktree-aware `get_tasks_dir()` — resolves `.tasks/` back to the main repo via `git rev-parse --git-common-dir` when running in a worktree
- Worktree config section in `workflow-config.yaml` (`base_path`, `branch_prefix`, `cleanup_on_complete`)
- WSL/Windows compatibility: worktree `.git` paths automatically converted to relative paths
- Worktree cleanup in crew.md Step 9 (Completion)
- 12 new tests in `TestWorktreeSupport`

### Changed
- Platform preambles updated: "Do NOT use git worktree" changed to "Do NOT use git worktree directly (use MCP tools instead)"
- Build script now generates `commands/` (Claude) in addition to `agents/` for command-type agents
- MCP tool count: 52 → 55

## [0.3.0] - 2026-02-09

### Added
- **Multi-platform build system** — `scripts/build-agents.py` transforms shared agent sources into Claude Code, Copilot CLI, and Gemini CLI formats
- **Gemini CLI support** — sub-agent `.md` files with YAML frontmatter (name, description, kind, tools, max_turns), per-agent tool restrictions, `install-gemini.sh` / `uninstall-gemini.sh`
- **Platform orchestrators** — `config/platform-orchestrators/copilot.md` (runSubagent chaining) and `config/platform-orchestrators/gemini.md` (autonomous description-based routing)
- **Gemini platform preamble** — `config/platform-preambles/gemini.md` with Gemini-native tool names (read_file, grep_search, etc.)
- **`.gemini` config path** — added to `PLATFORM_DIRS` so config cascade checks `~/.gemini/workflow-config.yaml`
- 5 new tests for `.gemini` config path detection and precedence

### Changed
- **Technical Writer always runs** — included in all workflow modes (full, turbo, fast, minimal) to keep documentation in sync
- All agents (Developer, Reviewer, Skeptic, Implementer, Feedback) now flag documentation gaps via `workflow_mark_docs_needed`
- Platform orchestrators fixed: "quick" mode renamed to correct "fast"/"minimal" names, added missing mode definitions
- `install.sh` now uses `scripts/build-agents.py claude` instead of inline shell loop
- `install-copilot.ps1` now uses `scripts/build-agents.py copilot` instead of inline PowerShell loop
- `install-copilot.ps1` cleans up old-format `crew-*.md` files (without `.agent.md` extension) on install
- Copilot orchestrator (`crew.agent.md`) gets `tools: ["*"]` in frontmatter
- Generated `.github/agents/` files are now gitignored (rebuilt on install)
- README rewritten with three-platform feature comparison table, install instructions for all platforms, updated config/contributing/uninstall sections
- `copilot-instructions.md` config section updated to mention `.gemini/` fallback

## [0.2.1] - 2026-02-06

### Fixed
- `/crew-config` command was reading `crew-config.yaml` instead of `workflow-config.yaml`
- `/crew-config` displayed hardcoded defaults instead of actual config values

## [0.2.0] - 2026-02-06

### Added
- **Workflow modes** — full, turbo, fast, minimal modes with auto-detection (`--mode`)
- **Effort levels** — per-agent thinking depth (low/medium/high/max) mapped to Anthropic API parameters (`thinking: {"type": "adaptive"}`, `output_config: {"effort": "<level>"}`)
- **Server-side compaction** — config for Anthropic API `compact-2026-01-12` model with custom preservation instructions
- **Compaction cost tracking** — `compaction_tokens` parameter on `workflow_record_cost` for tracking compaction iteration costs
- **Agent teams (experimental)** — `workflow_get_agent_team_config` MCP tool and config section for parallel review and parallel implementation via Claude Code agent teams
- **Subagent limits** — `max_turns` caps on all Task calls (30 planning, 50 implementation, 20 docs, 15 consultation) and `agent_timeout` config
- **Tool Discipline** — all 11 agent prompts now include guidance to use Grep/Glob/Read directly instead of spawning Task subagents for discovery
- **Specialist agents** — security auditor, performance analyst, API guardian, accessibility reviewer (auto-triggered)
- **Quality assertions** — `workflow_add_assertion`, `workflow_verify_assertion` for defining and checking quality gates
- **Error pattern learning** — `workflow_record_error_pattern`, `workflow_match_error` for matching errors to known solutions
- **Agent performance tracking** — `workflow_record_concern_outcome`, `workflow_get_agent_performance` for precision metrics
- **Optional phases** — `workflow_enable_optional_phase`, `workflow_get_optional_phases` for specialist agent activation
- **Parallelization** — `workflow_start_parallel_phase`, `workflow_complete_parallel_phase`, `workflow_merge_parallel_results` for running Reviewer+Skeptic concurrently
- **Cost tracking** — `workflow_record_cost`, `workflow_get_cost_summary` with per-agent/model breakdowns and long-context pricing
- **Opus 4.6 support** — updated model names, pricing ($5/$25 standard, $10/$37.50 long-context), turbo mode for single-pass planning
- **Native context preference** — skip Gemini if repomix output fits in Opus 4.6's context (`native_context_threshold_kb: 800`)
- CHANGELOG.md, VERSION file, release process documentation

### Changed
- Model fallback chain updated: claude-opus-4-6 > claude-opus-4 > claude-sonnet-4 > gemini
- Effort level comments in config now document Anthropic API parameter mapping
- All Task spawning examples in crew.md include `max_turns`
- Parallel review section in crew.md checks `workflow_get_agent_team_config` before choosing approach

## [0.1.0] - 2026-01-22

### Added
- Initial release
- 7 specialized agents: Architect, Developer, Reviewer, Skeptic, Implementer, Feedback, Technical Writer
- `/crew` command with task lifecycle (planning > implementation > documentation)
- `/crew ask` for single-agent consultation
- `/crew-status`, `/crew-resume`, `/crew-config` commands
- Configuration cascade: global > project > task > CLI overrides
- Human checkpoints at configurable points
- Loop mode for autonomous iteration until tests/build pass
- Gemini + Repomix integration for large-context codebase analysis
- MCP server with state management tools
- Memory preservation (`workflow_save_discovery`, `workflow_get_discoveries`, `workflow_flush_context`)
- Cross-task memory search (`workflow_search_memories`, `workflow_link_tasks`)
- Model resilience with exponential backoff and fallback chain
- Context management (`workflow_get_context_usage`, `workflow_prune_old_outputs`)
- Beads issue tracking integration (auto-detect)
- Enforcement hooks (PreToolUse for transitions, Stop for Technical Writer)
- 29 tests
