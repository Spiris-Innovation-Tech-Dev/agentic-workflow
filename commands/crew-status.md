# Workflow Status

Show the status of all active workflows, context usage, and model health.

## Command: /crew-status

List all task directories in `.tasks/` and summarize their state.

### For Each Task

Read `.tasks/TASK_XXX/state.json` and display:

```
┌─────────────────────────────────────────────────────────────┐
│ TASK_042: auth-jwt                                          │
├─────────────────────────────────────────────────────────────┤
│ Phase:    Implementation                                    │
│ Progress: ████████████░░░░░░░░ 60% (12/20 steps)           │
│ Agent:    Implementer                                       │
│ Updated:  2 hours ago                                       │
│                                                             │
│ Last Action: Completed Step 2.3 - Added auth middleware     │
│ Next:        Step 2.4 - Add token refresh endpoint          │
│                                                             │
│ Context:  ███████░░░░░░░░░░░░░ 35% (~70k tokens)           │
│ Memory:   12 discoveries saved                              │
│                                                             │
│ Resume: /crew resume TASK_042                               │
└─────────────────────────────────────────────────────────────┘
```

### Summary Table

If multiple tasks:

```
| Task ID  | Name       | Phase          | Progress | Context | Last Update |
|----------|------------|----------------|----------|---------|-------------|
| TASK_042 | auth-jwt   | Implementation | 60%      | 35%     | 2 hours ago |
| TASK_043 | api-cache  | Planning       | -        | 12%     | 5 mins ago  |
| TASK_041 | db-migrate | Complete       | 100%     | -       | Yesterday   |
```

### Context Usage

For the active task, call `workflow_get_context_usage()` and display:

```
Context Usage for TASK_042:
├── Total Size: 285 KB (~71,250 tokens)
├── Usage: 35% of estimated context window
├── Files: 23 files in task directory
│
├── Largest Files:
│   ├── repomix-output.txt    120 KB
│   ├── gemini-analysis.md     45 KB
│   └── plan.md                12 KB
│
└── Recommendation: Context usage is moderate. Consider saving important discoveries.
```

**If context is high (>60%)**, suggest:
```
⚠️  Context usage is high (78%). Consider:
    • Save important discoveries: workflow_save_discovery()
    • Prune old outputs: workflow_prune_old_outputs()
```

### Model Health

Call `workflow_get_resilience_status()` and display:

```
Model Health:
├── claude-opus-4:   ✓ Available
├── claude-sonnet-4: ✓ Available
└── gemini:          ⚠️ Cooldown (billing) - available in 4h 32m

Recent Errors:
└── gemini: billing error at 14:32 - "Quota exceeded"
```

**If models are in cooldown:**
```
⚠️  Primary model (claude-opus-4) in cooldown for 45s
    Fallback: claude-sonnet-4 available
```

### Memory Status

Show discoveries saved for the active task:

```
Discoveries for TASK_042:
├── Decisions:   3 saved
├── Patterns:    5 saved
├── Gotchas:     2 saved
├── Blockers:    1 saved (resolved)
└── Preferences: 1 saved

Linked Tasks: TASK_039 (builds_on), TASK_040 (related)
```

### Actions

- **Resume a task**: `/crew resume TASK_XXX`
- **View task details**: Read `.tasks/TASK_XXX/plan.md`
- **View agent outputs**: Check `.tasks/TASK_XXX/*.md`
- **Check context**: `workflow_get_context_usage()`
- **Prune context**: `workflow_prune_old_outputs()`
- **Search memories**: `workflow_search_memories("query")`
- **Check model health**: `workflow_get_resilience_status()`

### Implementation

When `/crew-status` is invoked:

1. **List Tasks**
   ```python
   # Scan .tasks/ directory
   for task_dir in Path(".tasks").iterdir():
       if task_dir.is_dir() and (task_dir / "state.json").exists():
           # Load and display state
   ```

2. **Get Context Usage** (for active task)
   ```python
   usage = workflow_get_context_usage(task_id=active_task)
   # Display usage.total_size_kb, usage.context_usage_percent, usage.recommendation
   ```

3. **Get Model Health**
   ```python
   status = workflow_get_resilience_status()
   # Display status.models with cooldown info
   ```

4. **Get Memory Status** (for active task)
   ```python
   discoveries = workflow_flush_context(task_id=active_task)
   # Display discoveries.by_category counts

   linked = workflow_get_linked_tasks(task_id=active_task)
   # Display linked.linked_tasks
   ```

Now, scan `.tasks/` directory and show status of all workflows with context and model health.
