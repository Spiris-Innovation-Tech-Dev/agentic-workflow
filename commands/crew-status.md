# Workflow Status

Show the status of all active workflows.

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
│ Resume: /crew resume TASK_042                           │
└─────────────────────────────────────────────────────────────┘
```

### Summary Table

If multiple tasks:

```
| Task ID  | Name       | Phase          | Progress | Last Update |
|----------|------------|----------------|----------|-------------|
| TASK_042 | auth-jwt   | Implementation | 60%      | 2 hours ago |
| TASK_043 | api-cache  | Planning       | -        | 5 mins ago  |
| TASK_041 | db-migrate | Complete       | 100%     | Yesterday   |
```

### Actions

- **Resume a task**: `/crew resume TASK_XXX`
- **View task details**: Read `.tasks/TASK_XXX/plan.md`
- **View agent outputs**: Check `.tasks/TASK_XXX/*.md`

Now, scan `.tasks/` directory and show status of all workflows.
