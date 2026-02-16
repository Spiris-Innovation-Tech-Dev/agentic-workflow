# Workflow Status

**THIS COMMAND IS READ-ONLY. Do NOT modify any state. Do NOT call workflow_transition, workflow_complete_phase, workflow_can_transition, or any MCP tool that writes state. Do NOT evaluate implementations, advance workflows, or continue any task. ONLY read state and display it.**

## Command: /crew-status

List all task directories in `.tasks/` and summarize their state.

### For Each Task

Read `.tasks/TASK_XXX/state.json` and display:

```
+-------------------------------------------------------------+
| TASK_042: auth-jwt                                          |
+-------------------------------------------------------------+
| Phase:    Implementation                                    |
| Progress: ============........ 60% (12/20 steps)            |
| Agent:    Implementer                                       |
| Updated:  2 hours ago                                       |
|                                                             |
| Worktree: ../repo-wt/TASK_042 (crew/task-042)  [active]    |
| Context:  =======............. 35% (~70k tokens)            |
| Memory:   12 discoveries saved                              |
|                                                             |
| Resume: /crew resume TASK_042                               |
+-------------------------------------------------------------+
```

### Summary Table

If multiple tasks:

```
| Task     | Phase          | Progress | Worktree                | Branch                 | WT Status   | Action     | Last Update |
|----------|----------------|----------|-------------------------|------------------------|-------------|------------|-------------|
| TASK_042 | implementer    | 60%      | ../repo-wt/TASK_042     | crew/implement-caching | active      | resume     | 2 hours ago |
| TASK_043 | developer      | -        | ../repo-wt/TASK_043     | crew/fix-login         | active      | resume     | 5 mins ago  |
| TASK_041 | complete       | 100%     | ../repo-wt/TASK_041     | crew/add-feature       | active      | cleanup    | Yesterday   |
| TASK_040 | complete       | 100%     | ../repo-wt/TASK_040     | crew/old-feature       | recyclable  | recyclable | 2 days ago  |
| TASK_038 | complete       | 100%     | ../repo-wt/TASK_038     | crew/auth-jwt          | cleaned     | done       | 3 days ago  |
| TASK_039 | architect      | -        | (none)                  | -                      | -           | resume     | 3 days ago  |
```

**Action column meanings:**
- `resume` — task is in progress, can be resumed in the worktree
- `cleanup` — workflow complete but worktree still active, candidate for `workflow_cleanup_worktree()`
- `recyclable` — worktree kept on disk for reuse by a future task
- `done` — worktree already cleaned up, no action needed

### Worktree Overview

After the summary table, if any tasks have worktrees, display a dedicated worktree section:

```
Worktrees:
  Active:      3  (TASK_042, TASK_043, TASK_041)
  Recyclable:  1  (TASK_040)
  Cleaned:     1  (TASK_038)
  None:        1  (TASK_039)

Cleanup candidates (workflow complete, worktree still active):
  TASK_041  ../repo-wt/TASK_041  crew/add-feature
    -> Run: python3 scripts/cleanup-worktree.py TASK_041 --remove-branch
    -> Or keep for reuse: python3 scripts/cleanup-worktree.py TASK_041 --keep-on-disk

Recyclable worktrees (available for reuse):
  TASK_040  ../repo-wt/TASK_040  crew/old-feature

Git worktree disk check:
  Run `git worktree list` to verify — orphaned worktrees not tracked in .tasks/ will show there.
```

**Cross-reference with git**: Run `git worktree list` and compare against `.tasks/` state. If any worktree paths appear in git but not in any task state, flag them as potentially orphaned:

```
Orphaned worktrees (in git but not in .tasks/):
  /path/to/repo-wt/unknown-dir  abc1234 [crew/old-branch]
    -> Run: git worktree remove /path/to/repo-wt/unknown-dir
```

### Resume Commands

Show host-aware resume commands. Detect AI host from `config_get_effective()` -> `worktree.ai_host` (if `auto`, default to `claude`):

- **Claude**: `/crew resume TASK_XXX`
- **Gemini / Copilot**: `@crew-resume TASK_XXX`

### Context Usage

For the active task, call `workflow_get_context_usage()` and display:

```
Context Usage for TASK_042:
  Total Size: 285 KB (~71,250 tokens)
  Usage: 35% of estimated context window
  Files: 23 files in task directory

  Largest Files:
    repomix-output.txt    120 KB
    gemini-analysis.md     45 KB
    plan.md                12 KB

  Recommendation: Context usage is moderate. Consider saving important discoveries.
```

**If context is high (>60%)**, suggest:
```
Context usage is high (78%). Consider:
  - Save important discoveries: workflow_save_discovery()
  - Prune old outputs: workflow_prune_old_outputs()
```

### Model Health

Call `workflow_get_resilience_status()` and display:

```
Model Health:
  claude-opus-4:   Available
  claude-sonnet-4: Available
  gemini:          Cooldown (billing) - available in 4h 32m

Recent Errors:
  gemini: billing error at 14:32 - "Quota exceeded"
```

### Memory Status

Show discoveries saved for the active task:

```
Discoveries for TASK_042:
  Decisions:   3 saved
  Patterns:    5 saved
  Gotchas:     2 saved
  Blockers:    1 saved (resolved)
  Preferences: 1 saved

Linked Tasks: TASK_039 (builds_on), TASK_040 (related)
```

### Actions

- **Resume a task**: `/crew resume TASK_XXX` (Claude) or `@crew-resume TASK_XXX` (Gemini/Copilot)
- **Cleanup a worktree**: `python3 scripts/cleanup-worktree.py TASK_XXX --remove-branch`
- **View task details**: Read `.tasks/TASK_XXX/plan.md`
- **View agent outputs**: Check `.tasks/TASK_XXX/*.md`
- **Check context**: `workflow_get_context_usage()`
- **Prune context**: `workflow_prune_old_outputs()`
- **Search memories**: `workflow_search_memories("query")`
- **Check model health**: `workflow_get_resilience_status()`
- **List git worktrees**: `git worktree list`

### Implementation

**Allowed read-only MCP tools:** `workflow_get_state`, `workflow_get_context_usage`, `workflow_get_resilience_status`, `workflow_get_discoveries`, `workflow_get_linked_tasks`, `workflow_get_worktree_info`, `config_get_effective`

**FORBIDDEN tools** (do NOT call these): `workflow_transition`, `workflow_complete_phase`, `workflow_can_transition`, `workflow_can_stop`, `workflow_is_complete`, `workflow_add_review_issue`, `workflow_cleanup_worktree`, or any tool that modifies state.

When invoked:

1. **List Tasks** — Read `.tasks/` directory contents and each `state.json`
2. **Cross-reference git worktrees** — `git worktree list` (read-only)
3. **Get Context Usage** (for active task) — `workflow_get_context_usage()`
4. **Get Model Health** — `workflow_get_resilience_status()`
5. **Get Memory Status** (for active task) — `workflow_get_discoveries()`, `workflow_get_linked_tasks()`
