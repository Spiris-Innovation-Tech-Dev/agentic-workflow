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
9. **Execute git commands**: Run the git commands returned by the tool
10. **Setup worktree environment**: Run the `setup_commands` returned by `workflow_create_worktree` (in order).
   These commands:
   - Symlink `.tasks/` to the main repo (for MCP tools and convenience)
   - Copy host settings (e.g., `.claude/settings.local.json`) with `additionalDirectories` patched in, granting the worktree session read/write access to the parent repo's `.tasks/` directory. This is critical — symlinks alone are not reliable for Claude Code file access.
   If `config_get_effective()` → `worktree.copy_settings` is `false`, skip the settings copy commands (but still run the `.tasks/` symlink command, which is always the first command).
   If any command fails, print a warning but continue.
11. **Fix paths for WSL/Windows compatibility** (skip for recycled worktrees — paths are already relative): The worktree's `.git` file and the main repo's `.git/worktrees/TASK_XXX/gitdir` contain absolute WSL paths that Windows tools (Visual Studio, PowerShell git) can't read. Convert both to relative paths. **CRITICAL: These files MUST have LF line endings (no CRLF). Use `printf` to write them — do NOT use file-write tools or `echo`.**
   - Read `<worktree_path>/.git` to get the current absolute gitdir path
   - Compute the relative path from the worktree to the main repo's `.git/worktrees/TASK_XXX` (e.g., `../../<repo_name>/.git/worktrees/TASK_XXX`)
   - Write with: `printf 'gitdir: <relative_path>\n' > <worktree_path>/.git`
   - Read `<main_repo>/.git/worktrees/TASK_XXX/gitdir` to get the current absolute path
   - Compute the relative path back to the worktree (e.g., `../../../<repo_name>-worktrees/TASK_XXX/.git`)
   - Write with: `printf '<relative_path>\n' > <main_repo>/.git/worktrees/TASK_XXX/gitdir`
   - Verify both files: `cat -A <worktree_path>/.git` should show `$` at end of line (LF), NOT `^M$` (CRLF)
12. **Install dependencies in worktree** (skip for recycled worktrees — dependencies already installed): Detect and install project dependencies so the worktree is ready to use. Check for these files **in the worktree directory** and run the first match:
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
13. **Print result** (use the exact format below, substituting actual values):

```
Worktree ready:
  Task:       TASK_XXX
  Directory:  <worktree_path>
  Branch:     <branch_name> (based on <current_branch>)
  Recycled:   yes, from <donor_task_id>  |  no (fresh)
  Task state: <main_repo_absolute_path>/.tasks/TASK_XXX/
  Setup:      .tasks/ symlinked, settings copied (or "settings copy skipped")
  Deps:       installed | skipped (recycled) | skipped | failed (reason)

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

14. **Auto-launch worktree session** (optional):
   Check config via `config_get_effective()` → `worktree.auto_launch`:
   - `never` → skip to Step 15
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

   Print success/failure status. If the returned `warnings` mention that the CLI doesn't support auto-prompts (e.g., Copilot), print the resume prompt text so the user can paste it manually. On failure, remind user of manual instructions from Step 13.

15. **STOP** — do nothing else. Do not start agents, do not fetch issues, do not continue.

### Example

```
/crew-worktree SAD-289
```

Creates worktree, prints path, stops. The user then opens the worktree directory and runs `/crew resume TASK_XXX` (Claude) or `@crew-resume TASK_XXX` (Gemini/Copilot) to start the actual workflow there.
