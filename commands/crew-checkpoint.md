# Workflow Checkpoint

Save a manual checkpoint of the current workflow state with a summary.

## Command: /crew-checkpoint $ARGS

### Step 1: Find Active Task

Read `.tasks/.active_task` or scan `.tasks/` for the active task. If no active task, tell the user.

### Step 2: Load State

Read `.tasks/TASK_XXX/state.json` and gather:
- Current phase and progress
- Phases completed
- Implementation progress (if in implementer phase)

### Step 3: Save Checkpoint

Call `workflow_save_discovery` with:
```
workflow_save_discovery(category="decision", content="Checkpoint: <phase> — <user's note or auto-summary>")
```

If the user provided arguments ($ARGS), use that as the checkpoint note.
If no arguments, generate a brief summary of what's been done so far.

### Step 4: Display Summary

```
Checkpoint saved for TASK_XXX:
  Phase:    <current phase>
  Progress: <progress if in implementation>
  Note:     <checkpoint note>

  Discoveries saved: <count>
  Resume with: /crew resume TASK_XXX
```

### Step 5: Git Status

Run `git status --short` and if there are changes, suggest:
```
Uncommitted changes detected. Consider committing before continuing.
```

Now, find the active task and save a checkpoint:

Arguments: $ARGS
