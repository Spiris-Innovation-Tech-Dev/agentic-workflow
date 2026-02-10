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
7. **Fix paths for WSL/Windows compatibility**: The worktree's `.git` file and the main repo's `.git/worktrees/TASK_XXX/gitdir` contain absolute WSL paths that Windows tools (Visual Studio, PowerShell git) can't read. Convert both to relative paths:
   - Read `<worktree_path>/.git` — replace the absolute path with a relative path from the worktree to the main repo's `.git/worktrees/TASK_XXX` (e.g., `gitdir: ../../<repo_name>/.git/worktrees/TASK_XXX`)
   - Read `<main_repo>/.git/worktrees/TASK_XXX/gitdir` — replace with a relative path back to the worktree's `.git` (e.g., `../../../<repo_name>-worktrees/TASK_XXX/.git`)
8. **Print result** (use the exact format below, substituting actual values):

```
Worktree created:
  Path:     <worktree_path>
  Branch:   <branch_name> (based on <current_branch>)
  Task:     TASK_XXX

To start the workflow, exit this session and run:

  cd <worktree_path>
  claude
  /crew resume TASK_XXX
```

9. **STOP** — do nothing else. Do not start agents, do not fetch issues, do not continue.

### Example

```
/crew-worktree SAD-289
```

Creates worktree, prints path, stops. The user then opens the worktree directory and runs `/crew resume TASK_XXX` to start the actual workflow there.
