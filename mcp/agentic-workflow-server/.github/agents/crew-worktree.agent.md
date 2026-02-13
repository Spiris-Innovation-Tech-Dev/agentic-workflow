---
name: crew-worktree
description: "Worktree Creator — creates isolated git worktrees for parallel crew workflows"
tools:
  - "*"
---

## Tool Discipline

Use direct tools for codebase exploration:
- Use `grep` for searching file contents
- Use `glob` for finding files by pattern
- Use `view` for reading files
- Use shell commands for git operations, tests, builds, and other system operations
- Avoid spawning agents for simple searches

## Git Safety

When working in a shared repository:
- Do **NOT** use git stash, git worktree directly (use MCP tools instead), or git clean commands
- Do **NOT** switch branches unless explicitly requested by the user
- Do **NOT** run `git commit`, `git push`, or `git add` unless explicitly requested
- If you notice untracked or modified files outside your scope, ignore them
- Never run `git checkout .` or `git restore .` — this would discard others' work-in-progress

# Create Worktree for Crew Task

You create an isolated git worktree so a `/crew` workflow can run without interfering with other work in the same repo.

**Do NOT start any workflow agents. Do NOT fetch Jira issues. Do NOT read agent prompts. This command ONLY creates a worktree and stops.**

Arguments: a task description (free text, Jira key, or `--beads ISSUE`).

### Steps

1. **Detect current branch**: Run `git branch --show-current` to get the current branch name
2. **Generate task ID**: `TASK_XXX` where XXX is the next available number in `.tasks/`
3. **Create task directory**: `.tasks/TASK_XXX/`
4. **Initialize state**: Call `workflow_initialize(task_id="TASK_XXX")` MCP tool
5. **Create worktree**: Call `workflow_create_worktree(task_id="TASK_XXX", base_branch="<current branch from step 1>")` MCP tool — this branches from your current branch, not main
6. **Execute git commands**: Run the git commands returned by the tool
7. **Fix paths for WSL/Windows compatibility**: The worktree's `.git` file and the main repo's `.git/worktrees/TASK_XXX/gitdir` contain absolute WSL paths that Windows tools (Visual Studio, PowerShell git) can't read. Convert both to relative paths. **CRITICAL: These files MUST have LF line endings (no CRLF). Use `printf` to write them — do NOT use file-write tools or `echo`.**
   - Read `<worktree_path>/.git` to get the current absolute gitdir path
   - Compute the relative path from the worktree to the main repo's `.git/worktrees/TASK_XXX` (e.g., `../../<repo_name>/.git/worktrees/TASK_XXX`)
   - Write with: `printf 'gitdir: <relative_path>\n' > <worktree_path>/.git`
   - Read `<main_repo>/.git/worktrees/TASK_XXX/gitdir` to get the current absolute path
   - Compute the relative path back to the worktree (e.g., `../../../<repo_name>-worktrees/TASK_XXX/.git`)
   - Write with: `printf '<relative_path>\n' > <main_repo>/.git/worktrees/TASK_XXX/gitdir`
   - Verify both files: `cat -A <worktree_path>/.git` should show `$` at end of line (LF), NOT `^M$` (CRLF)
8. **Install dependencies in worktree** (if applicable): Detect and install project dependencies so the worktree is ready to use. Check for these files **in the worktree directory** and run the first match:
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
9. **Print result** (use the exact format below, substituting actual values):

```
Worktree created:
  Path:       <worktree_path>
  Branch:     <branch_name> (based on <current_branch>)
  Task:       TASK_XXX
  Task state: <main_repo_absolute_path>/.tasks/TASK_XXX/
  Deps:       <installed | skipped | failed (reason)>

To start the workflow, open a new terminal and run:

  cd <worktree_path>

Then start your AI assistant (claude / gemini / copilot) and give it this prompt:

  Resume crew workflow TASK_XXX.
  This is a git worktree. The task state (.tasks/) lives in the main repo at:
    <main_repo_absolute_path>/.tasks/TASK_XXX/
  The MCP tools resolve this automatically via git, but if you read files
  directly, use the absolute path above.
  /crew resume TASK_XXX
```

10. **Auto-launch worktree session** (optional):
   Check config via `config_get_effective()` → `worktree.auto_launch`:
   - `never` → skip to Step 11
   - `prompt` → ask user: "Launch a new terminal session in the worktree? (yes/no)"
   - `auto` or user said yes → proceed with detection

   **Detect terminal environment** (run bash checks in order):
   1. `echo $TMUX` — non-empty → `tmux`
   2. `which wt.exe 2>/dev/null` — found → `windows_terminal`
   3. `uname -s` = "Darwin" → `macos`
   4. Otherwise → `linux_generic`

   **Detect AI host**: Check config `worktree.ai_host`.
   If `auto`: default to `claude` (safe default — the most common host).

   **Get main repo path**: Run `pwd`

   **Call**: `workflow_get_launch_command(task_id, terminal_env, ai_host, main_repo_path)`

   **Execute** the returned `launch_commands` via bash.

   Print success/failure status. On failure, remind user of manual instructions from Step 9.

11. **STOP** — do nothing else. Do not start agents, do not fetch issues, do not continue.

### Example

```
/crew-worktree SAD-289
```

Creates worktree, prints path, stops. The user then opens the worktree directory and runs `/crew resume TASK_XXX` to start the actual workflow there.
