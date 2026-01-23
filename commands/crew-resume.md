# Resume Workflow

Resume an existing workflow from its saved state.

## Command: /crew-resume $ARGS

Arguments should be a task ID like `TASK_042` or a path like `.tasks/TASK_042_auth-jwt`.

### Step 1: Load State

Read `.tasks/TASK_XXX/state.yaml`:

```yaml
task_id: TASK_042
task_name: "auth-jwt"
description: "Add user authentication with JWT"
current_phase: implementation
current_agent: implementer
iteration: 1
progress:
  total_steps: 20
  completed_steps: 12
  percentage: 60
last_checkpoint: 50_percent
```

### Step 2: Load Context

Load all saved artifacts:
- `.tasks/TASK_XXX/architect.md` - Architect analysis
- `.tasks/TASK_XXX/developer.md` - Developer plan
- `.tasks/TASK_XXX/reviewer.md` - Reviewer feedback
- `.tasks/TASK_XXX/skeptic.md` - Skeptic concerns
- `.tasks/TASK_XXX/plan.md` - Final implementation plan

### Step 3: Determine Resume Point

Based on `current_phase` and `current_agent`:

**If in Planning phase:**
- Resume the planning loop at the current agent
- Provide previous agent outputs as context

**If in Implementation phase:**
- Load plan.md
- Find first unchecked step
- Resume implementation from there

**If at Checkpoint:**
- Show checkpoint summary
- Ask human how to proceed

### Step 4: Show Resume Summary

```
┌─────────────────────────────────────────────────────────────┐
│ Resuming: TASK_042 - auth-jwt                               │
├─────────────────────────────────────────────────────────────┤
│ Where we left off:                                          │
│   Phase: Implementation                                     │
│   Last completed: Step 2.3 - Added auth middleware          │
│   Progress: 60% (12/20 steps)                              │
│                                                             │
│ What's next:                                                │
│   Step 2.4 - Add token refresh endpoint                     │
│                                                             │
│ Context loaded:                                             │
│   ✓ Architect analysis                                      │
│   ✓ Implementation plan (20 steps)                          │
│   ✓ Previous checkpoints (25%, 50%)                         │
└─────────────────────────────────────────────────────────────┘

Ready to continue?
```

### Step 5: Continue Workflow

Based on state, invoke the appropriate agent:
- Load agent prompt from `~/.claude/agents/`
- Provide all necessary context
- Continue workflow loop

Now, find and resume the specified task:

Task ID: $ARGS
