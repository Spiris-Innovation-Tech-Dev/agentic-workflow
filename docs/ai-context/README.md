# AI Context Documentation

This directory contains documentation specifically written for AI agents working with the agentic-workflow codebase. Unlike user-facing docs, these focus on implementation details, patterns, and gotchas that help AI agents make good decisions.

## Available Documentation

| File | Purpose |
|------|---------|
| [memory-preservation.md](./memory-preservation.md) | How to save/retrieve discoveries across context compaction |

## When to Read These Docs

- **Starting a new task** - Check for relevant patterns before planning
- **After context compaction** - Reload discoveries, review patterns
- **Implementing features** - Understand conventions and constraints
- **Debugging issues** - Check for known gotchas

## For Technical Writers

When documenting new features or patterns, consider:

1. **Is this AI-specific?** - Does it help AI agents but not necessarily human developers?
2. **Is it non-obvious?** - Would an AI without this context make mistakes?
3. **Is it a pattern?** - Is it something that should be consistent across the codebase?

If yes to any, add it to this directory.

### Document Structure

Each document should include:
- **What problem it solves** - Why does this exist?
- **How to use it** - Concrete examples with tool calls
- **When to use it** - Decision criteria
- **Common mistakes** - What to avoid

## MCP Tools Reference

The agentic-workflow MCP server provides tools for AI agents. Key tool groups:

### Memory & Context
- `workflow_save_discovery` - Save learnings
- `workflow_get_discoveries` - Retrieve learnings
- `workflow_flush_context` - Get all learnings for reload (superseded by compaction when enabled)
- `workflow_search_memories` - Search across tasks
- `workflow_get_context_usage` - Check context pressure
- `workflow_prune_old_outputs` - Clean up old files

### Workflow State
- `workflow_initialize` - Start a new workflow
- `workflow_transition` - Move between phases
- `workflow_get_state` - Get current state
- `workflow_complete_phase` - Mark phase done

### Workflow Modes & Effort
- `workflow_detect_mode` - Auto-detect mode from task description
- `workflow_set_mode` / `workflow_get_mode` - Set/get workflow mode (full/turbo/fast/minimal)
- `workflow_is_phase_in_mode` - Check if a phase runs in current mode
- `workflow_get_effort_level` - Get recommended thinking depth for an agent

### Cost Tracking
- `workflow_record_cost` - Record token usage (input, output, compaction tokens)
- `workflow_get_cost_summary` - Get cost breakdown by agent and model

### Agent Teams (Experimental)
- `workflow_get_agent_team_config` - Check if agent teams are enabled for a feature (`parallel_review`, `parallel_implementation`)

### Parallelization
- `workflow_start_parallel_phase` - Start parallel agent execution
- `workflow_complete_parallel_phase` - Mark a parallel phase done
- `workflow_merge_parallel_results` - Merge and deduplicate parallel results

### Task Linking
- `workflow_link_tasks` - Connect related tasks
- `workflow_get_linked_tasks` - Find related tasks

### Error Recovery
- `workflow_record_model_error` - Track model failures
- `workflow_get_available_model` - Get fallback model
- `workflow_get_resilience_status` - Check model health

### Quality & Assertions
- `workflow_add_assertion` / `workflow_verify_assertion` - Define and verify quality assertions
- `workflow_record_error_pattern` / `workflow_match_error` - Learn from and match error patterns
- `workflow_record_concern_outcome` / `workflow_get_agent_performance` - Track agent precision

### Git Worktree Support

Worktrees enable parallel `/crew` workflows in isolated directories. Available on all platforms:
- **Claude Code**: `/crew-worktree "task"` (slash command)
- **Copilot CLI**: `@crew-worktree "task"` (agent)
- **Gemini CLI**: `@crew-worktree "task"` (agent)

MCP tools (record metadata, return git commands — do not execute git directly):
- `workflow_create_worktree` - Record worktree metadata and get git commands to execute
- `workflow_get_worktree_info` - Check if a task has an active worktree
- `workflow_cleanup_worktree` - Mark worktree as cleaned and get cleanup git commands

The worktree branches from the current branch and `.tasks/` resolves back to the main repo via `git rev-parse --git-common-dir`.

**Important behaviors:**
- **LF enforcement**: The `.git` pointer file and `gitdir` file are written with `printf` to guarantee LF line endings (CRLF breaks git on Windows/WSL).
- **Dependency installation**: After creating the worktree, the agent auto-detects lock files (`package-lock.json`, `yarn.lock`, `requirements.txt`, etc.) and installs dependencies so the worktree is ready to use.
- **Task state path**: The final output includes the absolute path to `.tasks/TASK_XXX/` in the main repo and a prompt template that tells the new AI session where state lives. MCP tools resolve this automatically, but direct file reads should use the absolute path.

See the MCP server source at `mcp/agentic-workflow-server/` for full API documentation.
