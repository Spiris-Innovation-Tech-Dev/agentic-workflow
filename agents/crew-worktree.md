# Create Worktree for Crew Task

You create an isolated git worktree so a `/crew` workflow can run without interfering with other work in the same repo.

**Do NOT start any workflow agents. Do NOT fetch Jira issues. Do NOT read agent prompts. This command ONLY creates a worktree and stops.**

Arguments: a task description (free text, Jira key, or `--beads ISSUE`).

### Steps

1. **Detect current branch**: Run `git branch --show-current` to get the current branch name
2. **Check base branch freshness**: Check `config_get_effective()` → `worktree.sync_before_create`.
   - `never` → skip this step
   - `auto` or `prompt` → run `git fetch origin`, then `git rev-list --count <branch>..origin/<branch>`
     - If the remote tracking branch doesn't exist (e.g., `origin/<branch>` unknown), skip with a warning
     - If `git fetch` fails (offline), warn and continue
     - If count = 0: "Base branch is up to date"
     - If count > 0: warn "Local `<branch>` is N commits behind `origin/<branch>`"
       - `prompt`: ask user "Pull latest changes? (yes/no)" → if yes, run `git pull origin <branch>`
       - `auto`: just print warning, continue without pulling
3. **Generate task ID**: `TASK_XXX` where XXX is the next available number in `.tasks/`
4. **Create task directory**: `.tasks/TASK_XXX/`
5. **Initialize state**: Call `workflow_initialize(task_id="TASK_XXX")` MCP tool
6. **Resolve AI host**: Check config via `config_get_effective()` → `worktree.ai_host`.
   If `auto`: default to `claude` (safe default — the most common host).
   Store as `<ai_host>` for later steps.
7. **Resolve recycle setting**: Check `config_get_effective()` → `worktree.recycle`.
   - `never` → `<recycle>` = false
   - `auto` → `<recycle>` = true
   - `prompt` → ask user: "Reuse an existing finished worktree directory? (yes/no)" → set `<recycle>` accordingly
8. **Create worktree**: Call `workflow_create_worktree(task_id="TASK_XXX", base_branch="<current branch from step 1>", ai_host="<ai_host>", recycle=<recycle>)` MCP tool — this branches from your current branch, not main.
   If the response contains `recycled_from`, this is a recycled worktree — the git commands will use `git worktree move` + `git checkout` instead of `git worktree add`.
   If `warnings` is non-empty, print each warning. If a warning mentions WSL performance, ask user: "Continue anyway? (yes/no)". If no, abort.
9. **Execute git commands**: Run the git commands returned by the tool.
   - If `wsl_use_native_commands` is `true` in the MCP response (WSL + `/mnt/` path):
     Run git commands via PowerShell for native NTFS performance. For each git command:
     1. Get the Windows cwd: `wslpath -w "$(pwd)"`
     2. Convert any WSL-relative paths in the command to Windows-relative paths (replace `/` with `\` in path arguments)
     3. Run: `powershell.exe -Command "cd '<win_cwd>'; <git_command_with_win_paths>"`
     Example: `git worktree add -b crew/sad-639 ../repo-worktrees/TASK_014 main`
     becomes: `powershell.exe -Command "cd 'C:\git\repo'; git worktree add -b crew/sad-639 '..\repo-worktrees\TASK_014' main"`
   - Otherwise → run git commands directly in WSL (existing behavior)
10. **Setup worktree environment**: Run the `setup_commands` returned by `workflow_create_worktree` (in order).
   These commands:
   - Symlink `.tasks/` to the main repo (for MCP tools and convenience)
   - Copy host settings (e.g., `.claude/settings.local.json`) with `additionalDirectories` patched in, granting the worktree session read/write access to the parent repo's `.tasks/` directory. This is critical — symlinks alone are not reliable for Claude Code file access.
   If `config_get_effective()` → `worktree.copy_settings` is `false`, skip the settings copy commands (but still run the `.tasks/` symlink command, which is always the first command).
   If any command fails, print a warning but continue.
11. **Fix paths for WSL/Windows compatibility**: Run the `fix_paths_commands` returned by `workflow_create_worktree` (if any). This runs `python3 scripts/fix-worktree-paths.py TASK_XXX` which converts absolute WSL paths in the worktree's `.git` file and the main repo's `.git/worktrees/TASK_XXX/gitdir` to relative paths so Windows tools (Visual Studio, PowerShell git) can read them. The script computes the correct relative paths, writes files with LF line endings, and verifies the results — do NOT compute or fix paths manually.
   - If `fix_paths_commands` is empty (non-WSL or non-`/mnt/` path), skip this step.
12. **Jira operations** (optional — only when args contain a Jira issue key like `SAD-123`):
   1. Read `config_get_effective()` → `worktree.jira`
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
13. **Install dependencies in worktree**: Check `config_get_effective()` → `worktree.install_deps`. If `never`, skip this step entirely. Also skip for recycled worktrees (dependencies already installed).
   Detect and install project dependencies so the worktree is ready to use. Check for these files **in the worktree directory** and run the first match:
   - If `wsl_use_native_commands` is `true` in the MCP response (WSL + `/mnt/` path):
     Convert worktree path to Windows: `wslpath -w <worktree_path>`
     Run via PowerShell for each detected package manager:
       - `package-lock.json` → `powershell.exe -Command "cd '<win_path>'; npm ci"`
       - `yarn.lock` → `powershell.exe -Command "cd '<win_path>'; yarn install --frozen-lockfile"`
       - `pnpm-lock.yaml` → `powershell.exe -Command "cd '<win_path>'; pnpm install --frozen-lockfile"`
       - `requirements.txt` → `powershell.exe -Command "cd '<win_path>'; python -m pip install -r requirements.txt"`
       - `pyproject.toml` → `powershell.exe -Command "cd '<win_path>'; python -m pip install -e ."`
     Note: pip on Windows must use `python -m pip`, not `pip` directly.
   - Otherwise (not WSL, or worktree not on `/mnt/`) → run normally in WSL:
     - `package-lock.json` → `npm ci` (in worktree dir)
     - `yarn.lock` → `yarn install --frozen-lockfile` (in worktree dir)
     - `pnpm-lock.yaml` → `pnpm install --frozen-lockfile` (in worktree dir)
     - `requirements.txt` → `pip install -r requirements.txt` (in worktree dir)
     - `pyproject.toml` → `pip install -e .` (in worktree dir)
     - `Gemfile.lock` → `bundle install` (in worktree dir)
     - `go.sum` → `go mod download` (in worktree dir)
     - `Cargo.lock` → `cargo fetch` (in worktree dir)
   - If none found, skip this step.
   - If the install command fails, print a warning but continue — the user can fix it manually.
14. **Run post-setup commands** (optional):
   1. Read `config_get_effective()` → `worktree.post_setup_commands`
   2. If empty list → skip this step
   3. For each command, substitute placeholders:
      - `{worktree_path}` → absolute path to the worktree directory
      - `{task_id}` → e.g., `TASK_017`
      - `{branch_name}` → e.g., `crew/sad-710-description`
      - `{main_repo_path}` → absolute path to the main repo
      - `{jira_issue}` → e.g., `SAD-123` (empty string if no Jira issue linked)
   4. Run each command in order from the **worktree directory** as CWD
   5. If `wsl_use_native_commands` is `true` → run via PowerShell (convert worktree path to Windows)
   6. If any command fails, print a warning but continue — post-setup commands are non-blocking
15. **Print result** (use the exact format below, substituting actual values):

```
Worktree ready:
  Task:       TASK_XXX
  Directory:  <worktree_path>
  Branch:     <branch_name> (based on <current_branch>)
  Recycled:   yes, from <donor_task_id>  |  no (fresh)
  Task state: <main_repo_absolute_path>/.tasks/TASK_XXX/
  Setup:      .tasks/ symlinked, settings copied (or "settings copy skipped")
  Jira:       assigned + transitioned to "In Progress" | skipped | failed (reason)
  Deps:       installed | skipped (recycled) | skipped (config) | skipped | failed (reason)
  Post-setup: N commands ran | skipped (none configured)

To start the workflow, open a new terminal and run:

  cd <worktree_path>

Then start your AI assistant (claude / gemini / copilot) and give it this prompt:

  Resume crew workflow TASK_XXX.
  This is a git worktree — DO NOT create a new .tasks/ directory here.
  The task state lives in the main repo at:
    <main_repo_absolute_path>/.tasks/TASK_XXX/
  Read and write all task state using that absolute path.
  A .tasks/ symlink exists in this worktree for convenience, but always
  prefer the absolute path above for reliability.
  /crew resume TASK_XXX          ← for Claude
  @crew-resume TASK_XXX          ← for Gemini / Copilot
```

16. **Auto-launch worktree session** (optional):
   Check config via `config_get_effective()` → `worktree.auto_launch`:
   - `never` → skip to Step 17
   - `prompt` → ask user: "Launch a new terminal session in the worktree? (yes/no)"
   - `auto` or user said yes → proceed with detection

   **Detect terminal environment** (run bash checks in order):
   1. `echo $TMUX` — non-empty → `tmux`
   2. `which wt.exe 2>/dev/null` — found → `windows_terminal`
   3. `uname -s` = "Darwin" → `macos`
   4. Otherwise → `linux_generic`

   **Use AI host** from step 6 (`<ai_host>`).

   **Get main repo path**: Run `pwd`

   **Call**: `workflow_get_launch_command(task_id, terminal_env, ai_host, main_repo_path)`

   **Execute** the returned `launch_commands` via bash.

   Print success/failure status. If the returned `warnings` mention that the CLI doesn't support auto-prompts (e.g., Copilot), print the resume prompt text so the user can paste it manually. On failure, remind user of manual instructions from Step 15.

17. **STOP** — do nothing else. Do not start agents, do not fetch issues, do not continue.

### Example

```
/crew-worktree SAD-289
```

Creates worktree, prints path, stops. The user then opens the worktree directory and runs `/crew resume TASK_XXX` (Claude) or `@crew-resume TASK_XXX` (Gemini/Copilot) to start the actual workflow there.
