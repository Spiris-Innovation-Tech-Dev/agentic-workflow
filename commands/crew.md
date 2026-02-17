# Agentic Development Workflow

You are the entry point for the AI-augmented development workflow. This workflow orchestrates multiple specialized agents to plan, implement, and validate development tasks.

## Command: /crew $ARGS

### Step 1: Parse Arguments

Call the MCP tool to parse all arguments:
```
crew_parse_args(raw_args: "$ARGS")
```

This returns `action`, `task_description`, `options`, and `errors`. Handle errors by showing them to the user.

### Step 2: Route by Action

Based on the parsed `action`:

- **start** → Go to "Starting a New Workflow"
- **resume** → Call `crew_get_resume_state(task_id)`, display summary, then go to "Run Phase Loop"
- **status** → Show status of all active workflows (list `.tasks/` contents)
- **proceed** → Skip current checkpoint, call `crew_get_next_phase()`, go to "Run Phase Loop"
- **config** → Call `config_get_effective()` and display configuration
- **ask** → Go to "Single Agent Consultation"

## Starting a New Workflow

### Step 1: Resolve Task Description

1. If `options.task_file` provided → read description from that file
2. Else if `options.beads` provided and no description → read from beads issue body (`bd show <issue>`)
3. Else → use `task_description` from parsed args

### Step 2: Initialize Task

Call the MCP tool to initialize everything in one step:
```
crew_init_task(task_description: "<resolved description>", options: <parsed options>)
```

This handles: config loading, workflow init, mode detection, KB inventory, optional agent detection, saving config.yaml and task.md.

Display to user:
- Task ID and directory
- Workflow mode (with reason if auto-detected)
- Optional agents enabled (with reasons)
- Effective configuration highlights

### Step 3: Context Preparation (if configured)

If `gemini_research.enabled` is true in the returned config:
1. Check prerequisites: `which repomix`, `which gemini`
2. Run file discovery, generate repomix config, run repomix
3. Run Gemini analysis
4. Save outputs to task directory
5. If tools unavailable and `fallback_to_opus: true`, skip and continue

### Step 4: Beads Integration (if configured)

If `options.beads` was provided or beads auto-create is enabled:
1. Link/create beads issue: `bd update <issue> --status=in_progress`
2. Add start comment: `bd comments add <issue> "Workflow <task_id> started"`

### Step 5: Run Phase Loop

This is the core workflow loop. Repeat until complete:

```
next = crew_get_next_phase(task_id)
```

Based on `next.action`:

#### action: "spawn_agent"
1. Read agent prompt from `next.agent_prompt_path`
2. Substitute variables in prompt: `{knowledge_base}` → `next.variables.kb_path`, `{task_directory}` → `next.variables.task_directory`
3. Read context files listed in `next.context_files`
4. If `next.beads_comment`, run: `bd comments add <issue> "<comment>"`
5. Call `workflow_transition(to_phase: next.agent)` to update state
6. Handle parallel execution if `next.parallel_with` is set:
   - Spawn both agents simultaneously using parallel Task calls with `run_in_background: true`
   - Wait for both with TaskOutput
   - Call `workflow_start_parallel_phase`, `workflow_complete_parallel_phase` for each, then `workflow_merge_parallel_results`
7. Otherwise spawn single agent:
   ```
   Task(
     subagent_type: "general-purpose",
     model: "opus",
     max_turns: next.max_turns,
     prompt: "<agent prompt with context>"
   )
   ```
8. Save agent output to `.tasks/<task_id>/<agent>.md`
9. Parse output: `crew_parse_agent_output(agent: next.agent, output_text: <output>, task_id: <task_id>)`
10. If `has_blocking_issues` and recommendation is REVISE → loop back to developer
11. Call `workflow_complete_phase()` to mark phase done
12. Call `workflow_record_cost()` with token usage

#### action: "checkpoint"
Present checkpoint to user using AskUserQuestion:
```
Based on the [Agent Name]'s analysis:
[Summary of key findings/concerns]
How would you like to proceed?
```
Options: Approve, Revise, Restart, Skip
- **Approve**: Call `workflow_add_human_decision()`, continue loop
- **Revise**: Loop back to developer with feedback
- **Restart**: Re-initialize from architect
- **Skip**: Continue (not recommended)

#### action: "complete"
Go to "Completion"

#### action: "process_output"
The current phase output needs processing — parse it and check for checkpoint.

### Step 6: Implementation Loop

When the implementer phase is reached, use the implementation action tool:

```
impl = crew_get_implementation_action(task_id, last_verification_passed, last_error_output)
```

Based on `impl.action`:

- **implement_step**: Spawn implementer for `impl.step_id`. If `impl.loop_mode`, run verification after.
- **verify**: Run verification command, then call `crew_get_implementation_action` again with result.
- **retry**: Re-attempt with `impl.should_try_different_approach` guidance. Use `impl.known_solution` if available.
- **next_step**: Call `workflow_complete_step(step_id)`, then get next action.
- **checkpoint**: Present progress checkpoint to user.
- **escalate**: Pause and ask user for help. Show `impl.reason`.
- **complete**: Implementation done, continue to next phase.

### Step 7: Completion

Call `crew_format_completion(task_id, files_changed)` to get:
- Cost summary → display formatted table
- Commit message → suggest to user
- Worktree commands → execute based on `worktree_action` (prompt/auto/never)
- Beads commands → execute to close/sync issues

Display final summary:
```
Workflow Complete: <task_id>
Mode: [mode] | Duration: [time]

Cost Summary:
  Agent (model):    [tokens] tokens  $[cost]
  ...
  Total:            [tokens] tokens  $[cost]
```

Ask human to approve commit. Record concern outcomes if any were raised.

**Jira transitions** (if a Jira issue key is linked to this task):
Read `config_get_effective()` → `worktree.jira.transitions`.

1. **on_complete** — fires now, after workflow completes:
   Execute the Jira transition procedure (see below) with `transitions.on_complete`.

2. **on_cleanup** — fires when worktree cleanup runs (if `cleanup_on_complete` triggers cleanup):
   Execute the Jira transition procedure with `transitions.on_cleanup`.

**Jira transition procedure** (shared by all hooks):
   - Read the hook config → `{to, mode, only_from}`
   - If `to` is empty or `mode` is `never` → skip
   - If `mode` is `prompt` → ask user "Transition <issue> to '<to>'?", if no → skip
   - If `only_from` is non-empty: get current issue status via `jira_issues_get`. If current status is NOT in `only_from` → skip with message "Issue is '<current_status>', skipping transition to '<to>'"
   - List available transitions via `jira_transitions_list`, find match (case-insensitive), execute via `jira_issues_transition`
   - Warn-and-continue on any failure — Jira integration is non-blocking

## Single Agent Consultation

When action is "ask":

1. Load agent prompt from `~/.claude/agents/<agent>.md`
2. Gather context:
   - If `options.context`: Read specified files/directories
   - If `options.diff`: Include `git diff` output
   - If `options.plan`: Include plan file contents
   - If `options.file`: Read question from file
3. Spawn single agent:
   ```
   Task(
     subagent_type: "general-purpose",
     model: options.model or "opus",
     max_turns: 15,
     prompt: "<agent prompt + question + context>"
   )
   ```
4. Return response directly to user (no state saved)

## Agent Prompt Composition

When building prompts for agents, include:

1. **Agent prompt** from `~/.claude/agents/<agent>.md`
2. **Task description** from `.tasks/<task_id>/task.md`
3. **Previous agent outputs** (context_files from `crew_get_next_phase`)
4. **Gemini analysis** (if available, extract relevant section)
5. **Knowledge base inventory** (list files, substitute `{knowledge_base}` path)
6. **Variable substitution**: Replace `{knowledge_base}` and `{task_directory}` with config values

## Error Handling

If an agent fails or produces invalid output:
1. Retry once with clarified instructions
2. If still failing, escalate to human
3. Never silently continue past errors

## Output to User

Keep the user informed throughout:
- Show which agent is running and its purpose
- Summarize agent outputs concisely
- Clearly indicate checkpoints with options
- Show progress percentage during implementation
- Explain what happens next

Now, process the command arguments and begin the workflow:

Arguments: $ARGS
