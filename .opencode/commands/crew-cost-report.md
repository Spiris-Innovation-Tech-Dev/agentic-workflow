# Workflow Cost Report

Display a detailed cost breakdown for the current or specified task.

## Command: /crew-cost-report $ARGUMENTS

### Step 1: Find Task

If $ARGUMENTS contains a task ID (e.g. `TASK_042`), use that.
Otherwise, find the active task from `.tasks/.active_task` or scan `.tasks/`.

### Step 2: Get Cost Summary

Call `workflow_get_cost_summary(task_id="<task_id>")` via MCP.

### Step 3: Display Report

Format the cost data as a table:

```
Cost Report: TASK_XXX (<description>)
Mode: <workflow mode>

By Agent:
  Agent              Input Tokens  Output Tokens  Cost ($)   Duration
  ─────────────────  ────────────  ─────────────  ─────────  ────────
  Architect              12,450         3,200      $0.18     45s
  Developer              18,300         8,100      $0.42     62s
  Reviewer                8,200         2,400      $0.12     28s
  Skeptic                 9,100         3,800      $0.16     35s
  Implementer            45,000        22,000      $1.24    180s
  Technical Writer        6,500         4,200      $0.14     22s
  ─────────────────  ────────────  ─────────────  ─────────  ────────
  Total                  99,550        43,700      $2.26    372s

By Model:
  Model              Tokens Used    Cost ($)
  ─────────────────  ───────────    ────────
  opus                  98,000      $2.10
  sonnet                45,250      $0.16
  ─────────────────  ───────────    ────────
  Total                143,250      $2.26

Mode Comparison:
  Current (full):  $2.26  ← you are here
  If turbo:       ~$1.40  (estimated -38%)
  If fast:        ~$1.80  (estimated -20%)
  If minimal:     ~$0.90  (estimated -60%)
```

### Step 4: Recommendations

Based on the data, suggest optimizations:
- If one agent consumed >40% of total cost, note it
- If total cost is high, suggest trying a faster mode for similar future tasks
- If implementation phase dominated, note that implementation complexity drives cost

Now, find the task and display the cost report:

Arguments: $ARGUMENTS
