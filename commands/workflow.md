# Agentic Development Workflow

You are the entry point for the AI-augmented development workflow. This workflow orchestrates multiple specialized agents to plan, implement, and validate development tasks.

## Command: /workflow $ARGS

Parse the arguments to determine the action:

### Actions

1. **`/workflow <task description> [options]`** or **`/workflow start <task description> [options]`**
   - Start a new workflow for the given task
   - Creates .tasks/TASK_XXX directory
   - Begins with Architect agent

2. **`/workflow resume <task_id>`**
   - Resume an existing workflow from its last state
   - Reads state from .tasks/TASK_XXX/state.yaml

3. **`/workflow status`**
   - Show status of all active workflows
   - List .tasks/ contents

4. **`/workflow proceed`**
   - Skip current checkpoint and continue

5. **`/workflow config`**
   - Show/edit workflow configuration

### Command-Line Options

These options override configuration file settings for this task only:

| Option | Description | Example |
|--------|-------------|---------|
| `--loop-mode` | Enable Ralph-style autonomous looping | `--loop-mode` |
| `--no-loop` | Disable loop mode (even if config enables it) | `--no-loop` |
| `--max-iterations <n>` | Set max iterations per step | `--max-iterations 20` |
| `--verify <method>` | Verification method: tests\|build\|lint\|all | `--verify tests` |
| `--no-checkpoints` | Skip all human checkpoints (autonomous) | `--no-checkpoints` |
| `--beads <issue>` | Link to beads issue | `--beads PROJ-42` |
| `--config <file>` | Use specific config file | `--config ./my-config.yaml` |
| `--task <file>` | Read task description from file | `--task ./task.md` |

### Task Description Patterns

**Pattern 1: Simple inline task**
```
/workflow "Add user authentication with JWT"
```

**Pattern 2: Options first, then multi-line task**
```
/workflow --loop-mode --no-checkpoints --max-iterations 50

Implement a complete caching layer:

## Requirements
- Redis-based cache for API responses
- Cache invalidation on writes
- TTL configuration per endpoint
- Fallback to direct DB on cache miss

## Success Criteria
- All existing tests pass
- Cache hit rate > 80% for read endpoints
- No performance regression
```

**Pattern 3: Task file for complex/reusable tasks**
```
/workflow --loop-mode --task ./tasks/implement-caching.md
```

**Pattern 4: Beads issue as task source**
```
/workflow --beads CACHE-12 --loop-mode
```
(Reads task description from beads issue body)

### Argument Parsing Rules

1. **Options can come before or after task description**
2. **Task description is everything that's not an option**
3. **If `--task <file>` provided, read description from file**
4. **If `--beads <issue>` provided and no description, read from issue**
5. **Multi-line input is supported** - just keep typing after the command

### Task File Format (for --task option)

Create a `.md` file with your task description:

```markdown
# Task: Implement Caching Layer

## Description
Add Redis-based caching to improve API performance.

## Requirements
- [ ] Cache GET responses with configurable TTL
- [ ] Invalidate cache on POST/PUT/DELETE
- [ ] Add cache-control headers
- [ ] Implement cache warming on startup

## Success Criteria
- All tests pass
- Response time < 50ms for cached endpoints
- Cache hit rate > 80%

## Notes
- Use existing Redis connection from config
- Follow patterns in src/cache/base.ts
```

### Examples

```bash
# Simple task
/workflow "Add logout button to navbar"

# Loop mode for test fixing
/workflow --loop-mode --verify tests "Fix all failing unit tests"

# Complex overnight task with file
/workflow --loop-mode --no-checkpoints --max-iterations 50 --task ./migrate-to-v2.md

# From beads issue
/workflow --beads API-42 --loop-mode

# Multi-line inline (just keep typing)
/workflow --loop-mode --no-checkpoints

Refactor the authentication module:

1. Extract JWT logic to separate service
2. Add refresh token support
3. Update all endpoints to use new service
4. Ensure all auth tests pass

Output <promise>COMPLETE</promise> when done.
```

## Starting a New Workflow

When starting a new workflow:

### Step 1: Setup

1. Generate task ID: `TASK_XXX` where XXX is next available number
2. Create directory: `.tasks/TASK_XXX_<slugified-name>/`
3. Create state file: `state.yaml`
4. Check for `docs/ai-context/` - load if exists
5. Check for repomix config - generate context if available

### Step 2: Load Agent Prompts

Read the agent prompts from `~/.claude/agents/`:
- orchestrator.md
- architect.md
- developer.md
- reviewer.md
- skeptic.md
- implementer.md
- feedback.md
- technical-writer.md

### Step 3: Load Configuration (Cascade)

Load configuration with cascading overrides:

```
1. Global defaults:  ~/.claude/workflow-config.yaml
       ↓ (merge)
2. Project config:   <repo>/.claude/workflow-config.yaml (if exists)
       ↓ (merge)
3. Task config:      .tasks/TASK_XXX/config.yaml (if resuming)
       ↓ (override)
4. Command args:     --loop-mode, --max-iterations, etc.
```

**Configuration loading:**
1. Read `~/.claude/workflow-config.yaml` as base config
2. Check for `<repo>/.claude/workflow-config.yaml`:
   - If exists, deep-merge into config (project settings override global)
3. If resuming task, check `.tasks/TASK_XXX/config.yaml`:
   - If exists, deep-merge into config (task settings override project)
4. Parse command-line arguments:
   - `--loop-mode` → `loop_mode.enabled: true`
   - `--no-loop` → `loop_mode.enabled: false`
   - `--max-iterations N` → `loop_mode.max_iterations.per_step: N`
   - `--verify METHOD` → `loop_mode.verification.method: METHOD`
   - `--no-checkpoints` → all checkpoints set to `false`
   - `--beads ISSUE` → `beads.enabled: true`, `beads.linked_issue: ISSUE`
   - `--task FILE` → read task description from file
   - `--config FILE` → use specified config file instead of defaults

**Task description resolution:**
1. If `--task <file>` provided → read description from file
2. Else if `--beads <issue>` provided and no inline description → read from beads issue
3. Else → use remaining arguments as description (supports multi-line)

**Save effective config:**
- Write merged config to `.tasks/TASK_XXX/config.yaml`
- This allows resuming with same settings
- Also save resolved task description to `.tasks/TASK_XXX/task.md`

### Step 3.5: Context Preparation Phase

If `gemini_research.enabled` is true in configuration:

#### 3.5.1: Check Prerequisites

1. Verify `repomix` is available: `which repomix`
2. Verify `gemini` CLI is available: `which gemini`
3. If either missing and `fallback_to_opus: true`:
   - Log warning and skip to Step 4
   - Set `state.yaml` → `context_preparation.status: skipped`
4. If either missing and `fallback_to_opus: false`:
   - Stop workflow with error message

#### 3.5.2: Intelligent File Discovery

Use the `/repomix-build` pattern to intelligently find relevant files:

**Core Task Files**:
- Search for files matching keywords in task description
- Use `ag -l "keyword"` to find relevant code

**Base Classes/Interfaces**:
- Parse imports in core files to find base classes
- Look for abstract classes, interfaces, base types
- Check for inheritance chains

**Referenced Files**:
- Trace imports from core files (1-2 levels deep)
- Find files that import the core files (dependents)

**Example Patterns**:
- Search for similar implementations
- Look for files with similar patterns
- Find usage examples in tests

**Documentation**:
- Always include: `docs/ai-context/*` if exists
- Include: `README.md`, `docs/*.md`
- Include: Architecture and pattern documentation

#### 3.5.3: Generate Repomix Config

Create `.tasks/TASK_XXX/repomix-context.json`:

```json
{
  "include": [
    "src/relevant/file.ts",
    "src/base/class.ts",
    "src/referenced/*.ts",
    "src/examples/*.ts",
    "docs/ai-context/*.md"
  ],
  "ignore": [
    "**/*.test.ts",
    "**/node_modules/**",
    "**/*.d.ts",
    "**/dist/**"
  ],
  "output": {
    "filePath": ".tasks/TASK_XXX/repomix-output.txt",
    "style": "xml",
    "showLineNumbers": true
  }
}
```

#### 3.5.4: Run Repomix

Execute repomix to aggregate files:

```bash
repomix -c .tasks/TASK_XXX/repomix-context.json
```

Log the output size and file count for tracking.

#### 3.5.5: Run Gemini Analysis

Execute single comprehensive Gemini analysis with sections for all agents:

```bash
gemini -p "@.tasks/TASK_XXX/repomix-output.txt
{analysis_prompt from workflow-config.yaml}

Task: $TASK_DESCRIPTION" > .tasks/TASK_XXX/gemini-analysis.md
```

The analysis_prompt is loaded from `gemini_research.analysis_prompt` and includes:
- ARCHITECTURAL_CONTEXT (for Architect agent)
- IMPLEMENTATION_PATTERNS (for Developer agent)
- REVIEW_CHECKLIST (for Reviewer agent)
- FAILURE_MODES (for Skeptic agent)

#### 3.5.6: Update State

Add to `.tasks/TASK_XXX/state.yaml`:

```yaml
context_preparation:
  status: complete              # pending | complete | failed | skipped
  started_at: 2024-01-15T10:31:00Z
  completed_at: 2024-01-15T10:33:00Z

  file_discovery:
    total_files: 47
    categories:
      core: 5
      base_classes: 3
      referenced: 12
      examples: 8
      docs: 4

  repomix:
    status: success             # success | failed | skipped
    config_path: .tasks/TASK_XXX/repomix-context.json
    output_path: .tasks/TASK_XXX/repomix-output.txt
    files_included: 47
    output_size_kb: 850

  gemini:
    status: success             # success | failed | timeout | skipped
    analysis_path: .tasks/TASK_XXX/gemini-analysis.md
    analysis_time_seconds: 45
    sections_generated:
      - architectural_context
      - implementation_patterns
      - review_checklist
      - failure_modes
      - documentation_context

  fallbacks_used:
    repomix: false
    gemini: false

  errors: []
```

#### 3.5.7: Error Handling

**If repomix fails**:
- Log error to `.tasks/TASK_XXX/errors.log`
- If `error_handling.repomix_unavailable: fallback`:
  - Use direct file reading (top 10 most relevant files)
  - Set `state.yaml` → `fallbacks_used.repomix: true`
- If `error_handling.repomix_unavailable: fail`:
  - Stop workflow with error

**If Gemini fails**:
- Log error with Gemini output
- If `error_handling.gemini_unavailable: fallback`:
  - Skip Gemini analysis
  - Pass repomix output directly to Opus agents (original behavior)
  - Set `state.yaml` → `fallbacks_used.gemini: true`
- If `error_handling.gemini_unavailable: fail`:
  - Stop workflow with error

**If Gemini times out**:
- Kill process after `gemini_timeout` seconds
- Check if partial output exists in `gemini-analysis.md`
- If partial output usable, continue with warning
- Otherwise apply fallback behavior

### Step 4: Start Planning Loop

Launch the Architect agent first using the Task tool:

```
Task(
  subagent_type: "general-purpose",
  model: "opus",
  prompt: "
[Insert contents of ~/.claude/agents/architect.md]

## Task to Analyze
$TASK_DESCRIPTION

## Codebase Context
[If gemini-analysis.md exists: Extract and insert ARCHITECTURAL_CONTEXT section]
[Else: Insert repomix output or key files]

## Knowledge Base
[Insert docs/ai-context/* contents if they exist]

Provide your architectural analysis.
"
)
```

### Step 5: Process Architect Output

After Architect completes:
1. Save output to `.tasks/TASK_XXX/architect.md`
2. Check if checkpoint is configured (`after_architect: true`)
3. If checkpoint: Present summary and ask human to approve/revise/restart
4. If no checkpoint: Proceed to Developer agent

### Step 6: Continue Through Planning Loop

Architect → Developer → Reviewer → Skeptic

At each step:
1. Load previous agent output
2. Spawn next agent with context
3. Save output
4. Check for checkpoint
5. Handle human input if needed
6. Check for concerns requiring iteration

### Step 7: Start Implementation Loop

Once planning is approved:
1. Save final plan to `.tasks/TASK_XXX/plan.md`
2. Launch Implementer agent for first unchecked step
3. After each step: check progress percentage
4. At checkpoints (25/50/75%): pause for review (unless `--no-checkpoints`)
5. Run Feedback agent to detect deviations
6. Handle deviations per configuration

#### Loop Mode Implementation (if `loop_mode.enabled: true`)

When loop mode is active for implementation phase:

```
For each implementation step:
  iteration = 0
  while not complete and iteration < max_iterations.per_step:
    iteration++

    1. Execute step (Implementer agent)
    2. Run verification:
       - If method=tests: run test suite
       - If method=build: run build command
       - If method=lint: run linter
       - If method=all: run all above

    3. Check result:
       - If passing:
         - Output <promise>STEP_COMPLETE</promise>
         - Move to next step
       - If failing:
         - Read FULL error output
         - Analyze failure
         - If same error 3x: try different approach
         - Retry

    4. Check escalation triggers:
       - If iteration >= before_escalate: pause for human
       - If repeated_failure: escalate
       - If scope_creep detected: escalate

  If max_iterations reached without success:
    Output <promise>BLOCKED: [summary]</promise>
    Escalate to human
```

**Verification commands** (auto-detected or from config):
- `tests`: `npm test`, `pytest`, `go test ./...`, etc.
- `build`: `npm run build`, `go build`, `cargo build`, etc.
- `lint`: `npm run lint`, `eslint`, `golangci-lint`, etc.

**Self-correction protocol:**
1. Read the FULL error output (not just summary)
2. Identify root cause (not just symptom)
3. Check if fix aligns with plan
4. Make minimal changes
5. If same error 3x, try fundamentally different approach

### Step 8: Documentation Phase

After implementation completes, launch the Technical Writer agent:

```
Task(
  subagent_type: "general-purpose",
  model: "opus",
  prompt: "
[Insert contents of ~/.claude/agents/technical-writer.md]

## Task Completed
$TASK_DESCRIPTION

## Files Changed
[List of files created/modified during implementation]

## Files Read/Used (not modified)
[List of files that were referenced, extended, or imported - these may need documentation if undocumented]

## Implementation Notes
[Key findings and patterns discovered during implementation]

## Existing Documentation
[Contents of docs/ai-context/ if exists]

Analyze the implementation and update the AI context documentation.
Focus especially on documenting any existing base classes, frameworks, or patterns that were used but lack documentation.
"
)
```

After Technical Writer completes:
1. Save output to `.tasks/TASK_XXX/documentation-updates.md`
2. If `checkpoints.documentation.after_technical_writer: true`:
   - Present summary of documentation changes
   - Ask human to approve/revise documentation updates
3. Apply approved documentation changes to `docs/ai-context/`

### Step 9: Completion

When all steps complete:
1. Final review checkpoint
2. Generate commit message (include documentation changes)
3. Ask human to approve commit
4. Update lessons-learned.md

## State Management

Track state in `.tasks/TASK_XXX/state.yaml`:

```yaml
task_id: TASK_042
task_name: "auth-jwt"
description: "Add user authentication with JWT"
created_at: 2024-01-15T10:30:00Z
current_phase: planning          # planning | implementation | documentation | complete
current_agent: architect
iteration: 1
progress:
  total_steps: 0
  completed_steps: 0
  percentage: 0
last_checkpoint: null
human_decisions:
  - timestamp: 2024-01-15T10:35:00Z
    checkpoint: after_architect
    decision: approve
    notes: "Proceed with JWT approach"
documentation:
  status: pending                # pending | in_progress | complete | skipped
  findings_count: 0
  docs_created: []
  docs_updated: []
  validation_issues: []

# Loop mode tracking (when enabled)
loop_mode:
  enabled: true
  current_step_iterations: 0
  total_iterations: 0
  verification_results:
    - step: 1
      iterations: 3
      final_status: passed
      errors_encountered:
        - "TypeError: undefined is not a function"
        - "TypeError: undefined is not a function"
    - step: 2
      iterations: 1
      final_status: passed
      errors_encountered: []
  escalations:
    - step: 3
      iteration: 5
      reason: "repeated_failure"
      resolved: true

# Beads integration (when enabled)
beads:
  linked_issue: "CACHE-12"
  comments_added:
    - timestamp: 2024-01-15T10:30:00Z
      comment_id: "c_001"
      content: "Workflow started: TASK_042"
    - timestamp: 2024-01-15T11:00:00Z
      comment_id: "c_002"
      content: "Planning complete, implementation starting"
  status_synced: true
```

## Beads Integration

When `beads.enabled: true` in configuration:

### On Workflow Start
1. If `--beads ISSUE` provided:
   - Link task to existing beads issue
   - Add comment: "Workflow TASK_XXX started for this issue"
2. If `beads.auto_create_issue: true` and no issue linked:
   - Create new beads issue with task description
   - Link task to new issue

### During Workflow
1. If `beads.add_comments: true`:
   - Add comment at each phase transition
   - Add comment at each human checkpoint
   - Add comment on escalations
2. If `beads.sync_status: true`:
   - Update issue status as workflow progresses:
     - `in_progress` when implementation starts
     - `blocked` on escalation
     - `done` on completion

### On Workflow Complete
1. Add final comment with summary
2. Update issue status to `done`
3. Link to commit if created

## Human Checkpoints

When reaching a configured checkpoint, use AskUserQuestion:

```
Based on the [Agent Name]'s analysis:

[Summary of key findings/concerns]

How would you like to proceed?
```

Options:
- **Approve**: Continue to next phase
- **Revise**: Send back with specific feedback
- **Restart**: Start over with different approach
- **Skip**: Skip this agent (not recommended)

## Error Handling

If an agent fails or produces invalid output:
1. Retry once with clarified instructions
2. If still failing, escalate to human
3. Never silently continue past errors

## Output to User

Keep the user informed:
- Show which agent is running
- Summarize agent outputs concisely
- Clearly indicate checkpoints
- Show progress percentage
- Explain what happens next

Now, process the command arguments and begin the workflow:

Arguments: $ARGS
