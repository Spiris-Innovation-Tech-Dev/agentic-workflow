# Create Worktree for Crew Task

You create an isolated git worktree so a `/crew` workflow can run without interfering with other work in the same repo.

**Do NOT start any workflow agents. Do NOT fetch Jira issues. Do NOT read agent prompts. This command ONLY creates a worktree and stops.**

Arguments: a task description (free text, Jira key, or `--beads ISSUE`).

### Steps

1. **Read config + resolve prompts**: Call `config_get_effective()` MCP tool to get the `worktree` section. If MCP tools are unavailable (e.g., OpenCode subtasks), read the config by running:
   ```
   python3 scripts/crew_orchestrator.py config
   ```
   and parse the JSON output for the `worktree` section.
   For each prompt-mode setting (`sync_before_create`, `recycle`, `auto_launch`):
   - If value is `prompt` → ask the user (yes/no) → build the corresponding CLI flag (`--pull`/`--no-pull`, `--recycle`/`--no-recycle`, `--launch`/`--no-launch`)
   - If value is `auto` or `never` → the script handles it, no flag needed

2. **Run the setup script**:
   ```
   python3 scripts/setup-worktree.py "<description>" --ai-host {__platform__} [flags] --json
   ```
   Where `[flags]` are the CLI flags built in step 1 (only for prompt-mode settings where the user was asked).

3. **Handle exit code 2** (pending decisions): If the script exits with code 2, the JSON output contains a `pending_decisions` list. Present each decision to the user, collect answers, and re-run with the appropriate flags.

4. **Handle exit code 1** (error): Print the error and stop.

5. **Jira operations** (optional — only when the JSON result contains a `jira` section with an `issue_key`):
   1. Read `jira.config` from the script output
   2. **Assign** — based on `auto_assign`:
      - `never` → skip assignment
      - `auto` → get current user via `jira_users_current`, assign via `jira_issues_assign`
      - `prompt` → ask user "Assign this Jira issue to you? (yes/no)", if yes → assign
   3. **Transition** — execute the `transitions.on_create` hook using the Jira transition procedure:
      - Read `transitions.on_create` → `{to, mode, only_from}`
      - If `to` is empty or `mode` is `never` → skip
      - If `mode` is `prompt` → ask user "Transition issue to '<to>'? (yes/no)", if no → skip
      - If `only_from` is non-empty: get current issue status via `jira_issues_get`. If current status is NOT in `only_from` → skip with message "Issue is '<current_status>', skipping transition"
      - List available transitions via `jira_transitions_list` MCP tool
      - Find the transition whose name matches `to` (case-insensitive)
      - Execute via `jira_issues_transition` MCP tool
      - If no matching transition found, warn and continue
   4. If both `auto_assign == "never"` and `transitions.on_create.to` is empty → skip this step entirely
   5. If any Jira operation fails (MCP server unavailable, auth error, etc.), print a warning and continue — Jira integration is non-blocking

   **Note:** Jira MCP tools (`jira_users_current`, `jira_issues_assign`, `jira_transitions_list`, `jira_issues_transition`, `jira_issues_get`) require MCP server access. If MCP tools are unavailable (e.g., on OpenCode subtasks), skip Jira operations and print: "Jira integration skipped (MCP tools unavailable). Transition/assign manually if needed."

6. **Print formatted result**: Display the result from the JSON output:

```
Worktree ready:
  Task:       TASK_XXX
  Directory:  <worktree_path>
  Branch:     <branch_name> (based on <base_branch>)
  Recycled:   yes, from <recycled_from>  |  no (fresh)
  Task state: <main_repo_path>/.tasks/TASK_XXX/
  Setup:      <summary.setup>
  Jira:       assigned + transitioned to "In Progress" | skipped | failed (reason)
  Deps:       <summary.deps>
  Post-setup: <summary.post_setup>

To start the workflow, open a new terminal and run:

  cd <worktree_path>

Then start your AI assistant (claude / gemini / copilot) and give it this prompt:

  <resume_prompt>
```

If `launch.launched` is true, skip the manual instructions — the session was already launched.

   **Detect terminal environment** (cross-platform — use Python or `setup-worktree.py --json`):
   - The `setup-worktree.py --json` output includes `launch.terminal_env` — use that value directly.
   - If detecting manually: check `$TMUX` env var → `tmux`; on WSL check for `wt.exe` on PATH → `windows_terminal`; `platform.system() == "Darwin"` → `macos`; `platform.system() == "Windows"` (non-WSL) → `windows_native`; otherwise → `linux_generic`.

   **Use AI host** from step 6 (`<ai_host>`).

   **Resolve launch mode** from config → `worktree.terminal_launch_mode`:
   - `auto` (default) → platform default: tmux uses window, Windows Terminal uses tab, macOS uses window
   - `window` → force new window (Windows Terminal: `wt.exe new-window`)
   - `tab` → force new tab (Windows Terminal: `wt.exe new-tab`; tmux/macOS ignore this)

   **Get main repo path**: Run `pwd`

   **Call**: `workflow_get_launch_command(task_id, terminal_env, ai_host, main_repo_path, launch_mode)` MCP tool. If MCP tools are unavailable, the launch commands are already included in the `setup-worktree.py --json` output under `launch.commands` — use those directly.

   **Execute** the returned `launch_commands` via bash.

   Print success/failure status. If the returned `warnings` mention that the CLI doesn't support auto-prompts (e.g., Copilot), print the resume prompt text so the user can paste it manually. On failure, remind user of manual instructions from Step 15.

17. **STOP** — do nothing else. Do not start agents, do not fetch issues, do not continue.

### Example

```
/crew-worktree SAD-289
```

Creates worktree, prints path, stops. The user then opens the worktree directory and runs `/crew resume TASK_XXX` (Claude) or `@crew-resume TASK_XXX` (Gemini/Copilot) to start the actual workflow there.
