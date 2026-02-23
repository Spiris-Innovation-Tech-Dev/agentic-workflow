# Agentic Development Workflow

You orchestrate the /crew workflow by running the orchestrator script for routing decisions and handling each action with full intelligence.

## Command: /crew $ARGS

### Initialize

Run: `python3 {__scripts_dir__}/crew_orchestrator.py init --args "$ARGS"`

The script returns JSON with `action` and routing details. Handle by action:

- **start** → Display task summary (ID, mode, optional agents), log the user's task description, then run Context Preparation and Beads Integration (below), then enter Action Loop with `result.next`:
  ```
  python3 {__scripts_dir__}/crew_orchestrator.py log-interaction --task-id <id> --role human --content "<original task description>" --type message --phase init
  ```
- **resume** → Display `result.resume_state.display_summary`, enter Action Loop with `result.next`
- **status** → List `.tasks/` contents and show active workflows
- **config** → Call `config_get_effective()` and display configuration
- **ask** → Go to Single Agent Consultation with `result.agent` and `result.question`
- **error** → Show `result.errors` to user

### Context Preparation (if configured)

If `config.gemini_research.enabled` is true:
1. Check prerequisites: `which repomix`, `which gemini`
2. Run file discovery, generate repomix config, run repomix
3. Run Gemini analysis, save outputs to task directory
4. If tools unavailable and `fallback_to_opus: true`, skip and continue

### Beads Integration (if configured)

If `result.beads_issue` is set:
1. `bd update <issue> --status=in_progress`
2. `bd comments add <issue> "Workflow <task_id> started"`

### Action Loop

Loop on the returned JSON action from the orchestrator:

#### action: "spawn_agent"

1. Read agent prompt from `next.agent_prompt_path`
2. Compose prompt using Agent Prompt Composition (below)
3. If `next.beads_comment`, run: `bd comments add <issue> "<comment>"`
4. If `next.parallel_with` is set:
   - Spawn both agents simultaneously using parallel Task calls with `run_in_background: true`
   - Wait for both with TaskOutput
   - Call `workflow_start_parallel_phase`, `workflow_complete_parallel_phase` for each, then `workflow_merge_parallel_results`
5. Otherwise spawn single agent:
   ```
   Task(subagent_type: "general-purpose", model: "opus", max_turns: next.max_turns, prompt: "<composed prompt>")
   ```
6. Save agent output to `.tasks/<task_id>/<agent>.md`
7. Run: `python3 {__scripts_dir__}/crew_orchestrator.py agent-done --task-id <id> --agent <agent> --output-file <path> [--input-tokens N --output-tokens N --model opus]`
8. If `result.has_blocking_issues` and recommendation is REVISE → inform user, loop continues via `result.next`
9. Continue loop with `result.next`

#### action: "checkpoint"

Summarize the preceding agent's key findings, then present to user:
```
AskUserQuestion: "Based on [Agent]'s analysis: [summary]. How would you like to proceed?"
Options: Approve, Revise, Restart, Skip
```
After user responds, run: `python3 {__scripts_dir__}/crew_orchestrator.py checkpoint-done --task-id <id> --decision <decision> [--notes "..."] --question "<checkpoint summary that was presented>"`
The `--question` flag logs both the checkpoint question and response to `interactions.jsonl`.
Continue loop with `result.next`.

#### action: "implement_step" / "verify" / "retry" / "next_step" / "escalate"

Run: `python3 {__scripts_dir__}/crew_orchestrator.py impl-action --task-id <id> [--verified true/false] [--error "..."]`
- **implement_step**: Spawn implementer for `step_id`. If `loop_mode`, run verification after.
- **verify**: Run verification command, then call impl-action again with result.
- **retry**: Re-attempt with `should_try_different_approach` guidance. Use `known_solution` if available.
- **next_step**: Call `workflow_complete_step(step_id)`, then get next action.
- **checkpoint**: Present progress checkpoint to user.
- **escalate**: Pause and ask user for help. Show `reason`. Log the escalation and response:
  ```
  python3 {__scripts_dir__}/crew_orchestrator.py log-interaction --task-id <id> --role agent --content "<reason>" --type escalation_question --agent implementer --phase implementer
  ```
  After user responds:
  ```
  python3 {__scripts_dir__}/crew_orchestrator.py log-interaction --task-id <id> --role human --content "<user response>" --type escalation_response --phase implementer
  ```
- **complete**: Implementation done, continue to next phase (feedback → technical_writer → complete).

**Note**: After the implementer returns "complete", the action loop continues with `result.next` which will be `spawn_agent` for the remaining phases (feedback and/or technical_writer). The final `action: "complete"` only arrives after ALL phases including technical_writer are done. **Never commit before the technical-writer has run.**

#### action: "complete"

Run: `python3 {__scripts_dir__}/crew_orchestrator.py complete --task-id <id> [--files <comma-separated>]`
- Display cost summary as formatted table
- Suggest commit message to user
- Execute worktree commands based on `worktree_action` (prompt/auto/never)
- Execute beads commands to close/sync issues
- Handle Jira transitions from `result.jira_actions`: for each action with `"prompt"` → ask user, with `"execute"` → call `jira_issues_transition` (check `only_from` first via `jira_issues_get`)
- Ask human to approve commit. Record concern outcomes if any were raised.

### Single Agent Consultation

1. Load agent prompt from `~/{__platform_dir__}/agents/<agent>.md`
2. Gather context: `options.context` (files), `options.diff` (git diff), `options.plan` (plan file), `options.file` (question from file)
3. Spawn: `Task(subagent_type: "general-purpose", model: options.model or "opus", max_turns: 15, prompt: "<agent prompt + question + context>")`
4. Return response directly to user (no state saved)

## Agent Prompt Composition

When building prompts for agents, include:
1. **Agent prompt** from `~/{__platform_dir__}/agents/<agent>.md`
2. **Task description** from `.tasks/<task_id>/task.md`
3. **Previous agent outputs** (context_files from orchestrator response)
4. **Gemini analysis** (if available, extract relevant section)
5. **Knowledge base inventory** (list files, substitute `{knowledge_base}` path)
6. **Variable substitution**: Replace `{knowledge_base}` and `{task_directory}` with config values

## Error Handling

If an agent fails or produces invalid output:
1. Retry once with clarified instructions
2. If still failing, escalate to human
3. Never silently continue past errors

## Interaction Logging

When the user provides ad-hoc guidance mid-workflow (outside of checkpoints), log it:
```
python3 {__scripts_dir__}/crew_orchestrator.py log-interaction --task-id <id> --role human --content "<user input>" --type guidance --phase <current_phase>
```

## Output to User

Keep the user informed throughout:
- Show which agent is running and its purpose
- Summarize agent outputs concisely
- Clearly indicate checkpoints with options
- Show progress percentage during implementation
- Explain what happens next

Now, process the command arguments and begin the workflow:

Arguments: $ARGS
