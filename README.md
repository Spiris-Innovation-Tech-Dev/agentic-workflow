# Agentic Workflow

<p align="center">
  <img src="logo.png" alt="Agentic Workflow Logo" width="300">
</p>

A multi-agent development workflow for Claude Code that orchestrates specialized AI agents through planning, implementation, and documentation phases.

## Why Agentic Workflow?

Complex development tasks require multiple perspectives: architecture considerations, detailed planning, security review, edge case analysis, and careful implementation. Managing this manually with AI means constant context switching and oversight.

**Agentic Workflow** solves this by:

- **Orchestrating specialized agents** - Each agent has a focused role (architect, developer, reviewer, skeptic, etc.)
- **Maintaining human control** - Configurable checkpoints let you review and approve at critical stages
- **Supporting autonomous execution** - Loop mode handles repetitive fix tasks while you sleep
- **Preserving context** - Gemini integration provides massive context analysis; state files enable resumption

## Features

- **Multi-agent architecture** - 7 specialized agents for different concerns
- **Single agent consultation** - Quick `/crew ask` for second opinions without full workflow
- **Human checkpoints** - Control points for review and approval at each phase
- **Loop mode** - Autonomous iteration until tests/build pass (Ralph Wiggum-style)
- **Configuration cascade** - Global → Project → Task → CLI overrides
- **Gemini + Repomix integration** - Large-context codebase analysis for research phases
- **State management** - Resume interrupted workflows from any point
- **Beads integration** - Optional issue tracking integration
- **Technical documentation** - Automatic AI-context documentation updates

## Prerequisites

- [Claude Code](https://github.com/anthropics/claude-code) CLI installed
- Git
- (Optional) [Gemini CLI](https://github.com/google/gemini-cli) for large-context analysis
- (Optional) [Repomix](https://github.com/yamadashy/repomix) for intelligent file aggregation
- (Optional) [Beads](https://github.com/johanyman/beads) for issue tracking

## Installation

```bash
git clone https://github.com/johanyman/agentic-workflow.git
cd agentic-workflow
./install.sh
```

The installer copies:
- Commands to `~/.claude/commands/`
- Agents to `~/.claude/agents/`
- Config to `~/.claude/workflow-config.yaml`

Existing config files are backed up with a timestamp.

## Quick Start

### Simple task with checkpoints
```bash
/crew "Add user authentication with JWT"
```

### Loop mode (autonomous until tests pass)
```bash
/crew --loop-mode --verify tests "Fix all failing tests"
```

### From a task file
```bash
/crew --loop-mode --task ./tasks/implement-caching.md
```

### Overnight autonomous run
```bash
/crew --loop-mode --no-checkpoints --max-iterations 50

Migrate all API endpoints to v2:
- Update request/response types
- Add backward compatibility
- Update all tests
```

### With beads issue tracking
```bash
/crew --beads CACHE-12 --loop-mode
```

### Quick consultation (no full workflow)
```bash
# Get architect's opinion on a design decision
/crew ask architect "Should we use WebSockets or SSE for real-time updates?"

# Have skeptic review your plan for edge cases
/crew ask skeptic --plan .tasks/TASK_042/plan.md

# Reviewer check on specific code
/crew ask reviewer "Is this secure?" --context src/auth/
```

## Workflow Lifecycle

Each `/crew` invocation is a **complete cycle** that runs through all phases:

```
/crew "task" → Planning → Implementation → Documentation → Complete
```

### After Completion

When a crew finishes:
- All changes are made but **not committed** (unless you approve)
- Documentation updates are proposed
- The task state is saved in `.tasks/TASK_XXX/`

### Starting a New Task

If you have feedback or want changes after a crew completes, **start a new crew**:

```bash
# Original task completed, now want refinements
/crew "Refine the authentication - add rate limiting"
```

The new crew will:
1. See the changes from the previous task (they're in the codebase)
2. Run through all agents again with fresh analysis
3. Build on or modify the previous work

### Resuming Interrupted Work

If a crew is interrupted (you close the terminal, etc.), resume it:

```bash
/crew-resume           # Lists resumable tasks
/crew-resume TASK_042  # Resume specific task
```

### Why Start Fresh?

Each crew invocation brings fresh perspectives from all agents. For significant changes or new requirements, a new crew ensures:
- Architect re-evaluates system impact
- Developer creates a proper plan
- Reviewer and Skeptic validate the approach
- Full documentation cycle runs

For small tweaks, you can always make direct edits without using the crew.

## Architecture

### Workflow Phases

```
┌─────────────────┐     ┌─────────────────────┐     ┌────────────┐     ┌─────────────┐
│  CONTEXT PREP   │ ──▶ │   PLANNING LOOP     │ ──▶ │ IMPLEMENT  │ ──▶ │ DOCUMENT    │
│ (Gemini+Repomix)│     │                     │     │   LOOP     │     │             │
└─────────────────┘     └─────────────────────┘     └────────────┘     └─────────────┘
                              │
                              ▼
                    Architect → Developer → Reviewer → Skeptic
                        │           │           │          │
                        ▼           ▼           ▼          ▼
                   [checkpoint] [optional]  [checkpoint] [checkpoint]
```

### Agents

| Agent | Phase | Role | Output |
|-------|-------|------|--------|
| **Architect** | Planning | System design, boundaries, risks, integration points | Architectural analysis |
| **Developer** | Planning | Detailed step-by-step implementation plan | `TASK_XXX.md` with checkboxes |
| **Reviewer** | Planning | Plan validation, security review, pattern compliance | Review findings |
| **Skeptic** | Planning | Edge cases, failure modes, "3 AM scenarios" | Risk analysis |
| **Implementer** | Implementation | Execute plan step-by-step, verify each step | Completed task, test results |
| **Feedback** | Implementation | Detect deviations, classify severity, recommend fixes | Deviation analysis |
| **Technical Writer** | Documentation | Update AI-context docs with discovered patterns | Documentation updates |

### Agent Details

#### Architect (Planning Phase)
Analyzes system-wide implications before any code is written:
- Identifies affected modules and integration points
- Evaluates risks, constraints, and alternatives
- Raises questions requiring human decision
- Reviews security and performance implications

#### Developer (Planning Phase)
Translates architectural guidance into an executable plan:
- Creates detailed step-by-step instructions in `TASK_XXX.md`
- Specifies exact file paths, imports, and code changes
- Includes verification commands for each step
- Documents rollback procedures and warning signs

#### Reviewer (Planning Phase)
Validates the developer's plan before execution:
- Checks code syntax and pattern compliance
- Verifies security considerations are addressed
- Ensures test coverage is planned
- Identifies missing steps or ambiguities

#### Skeptic (Planning Phase)
Stress-tests the plan for real-world scenarios:
- Considers race conditions and concurrency issues
- Evaluates external dependency failure modes
- Questions assumptions and identifies risks
- Proposes additional test cases for edge cases

#### Implementer (Implementation Phase)
Executes the approved plan:
- Follows instructions precisely from `TASK_XXX.md`
- Runs verification after each step
- Reports any deviations or blockers
- Marks checkboxes as steps complete

#### Feedback (Implementation Phase)
Monitors implementation quality:
- Compares actual changes vs planned changes
- Classifies deviations (acceptable, concerning, critical)
- Validates against knowledge base patterns
- Escalates issues requiring human judgment

#### Technical Writer (Documentation Phase)
Captures knowledge for future AI sessions:
- Documents discovered patterns and conventions
- Updates `docs/ai-context/` files
- Validates existing documentation accuracy
- Captures non-obvious implementation details

## Commands

### `/crew`
Main command for starting or resuming workflows.

```bash
/crew [options] [task description]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--loop-mode` | Enable autonomous looping until verification passes |
| `--no-loop` | Disable loop mode |
| `--max-iterations <n>` | Max attempts per step (default: 10) |
| `--verify <method>` | Verification: `tests`, `build`, `lint`, `all`, `custom` |
| `--no-checkpoints` | Skip human checkpoints (fully autonomous) |
| `--beads <issue>` | Link to beads issue (e.g., `AUTH-42`) |
| `--task <file>` | Read task from markdown file |

### `/crew-status`
Display status of all active workflows.

```bash
/crew-status
```

Shows:
- Task ID and description
- Current phase and progress percentage
- Active agent
- Next steps and resume command

### `/crew-resume`
Resume an interrupted workflow.

```bash
/crew-resume [task-id]
```

Without `task-id`, shows a list of resumable tasks.

### `/crew-config`
View or modify configuration.

```bash
/crew-config
```

Interactive menu offering:
- View current settings
- Apply presets (Maximum Control, Fast Flow, Full Auto)
- Edit individual settings

### `/crew ask`
Invoke a single agent for quick consultation without starting a full workflow.

```bash
/crew ask <agent> <question> [options]
```

**Available Agents:**

| Agent | Best For |
|-------|----------|
| `architect` | System design, trade-offs, architectural decisions |
| `developer` | Implementation approach, code structure |
| `reviewer` | Code review, plan validation, correctness checks |
| `skeptic` | Edge cases, failure modes, what could go wrong |
| `feedback` | Comparing implementation vs plan |

**Options:**

| Option | Description |
|--------|-------------|
| `--context <path>` | Include specific files/directories as context |
| `--file <path>` | Read the question from a file |
| `--plan <path>` | Include a plan file (for reviewer/skeptic) |
| `--diff` | Include current git diff as context |
| `--model <model>` | Override model (default: opus) |

**Examples:**

```bash
# Quick architectural decision
/crew ask architect "Redis vs Memcached for our caching needs?"

# Review code with context
/crew ask reviewer "Is this auth implementation secure?" --context src/auth/

# Skeptic review of current changes
/crew ask skeptic "What could go wrong?" --diff

# Multi-line question
/crew ask architect

We're considering two approaches:
1. Direct Stripe integration
2. Payment abstraction layer

What are the trade-offs for future multi-provider support?
```

## Configuration

Configuration uses a cascade system where each level overrides the previous:

```
~/.claude/crew-config.yaml          ← Global defaults
       ↓
<repo>/.claude/crew-config.yaml     ← Project overrides
       ↓
.tasks/TASK_XXX/config.yaml             ← Task-specific
       ↓
Command-line args                        ← Highest priority
```

### Configuration Reference

#### Checkpoints

Control when the workflow pauses for human approval:

```yaml
checkpoints:
  planning:
    after_architect: true      # Review architectural concerns
    after_developer: false     # Auto-proceed to reviewer
    after_reviewer: true       # Review gaps found
    after_skeptic: true        # Review edge cases

  implementation:
    at_25_percent: false       # Auto-proceed early
    at_50_percent: true        # Halfway review
    at_75_percent: false       # Auto-proceed to completion
    before_commit: true        # Always review before commit

  documentation:
    after_technical_writer: true

  feedback:
    on_deviation: true         # When implementation deviates
    on_test_failure: true      # When tests fail
    on_major_change: true      # When scope creeps
```

#### Loop Mode

Configure autonomous iteration behavior:

```yaml
loop_mode:
  enabled: false               # Override with --loop-mode

  phases:
    planning: false            # Planning needs human judgment
    implementation: true       # Loop until verification passes
    documentation: false       # Docs are one-shot

  max_iterations:
    per_step: 10               # Attempts per implementation step
    per_phase: 30              # Total iterations per phase
    before_escalate: 5         # Pause for human after N tries

  verification:
    method: tests              # tests | build | lint | all | custom
    custom_command: ""         # When method is "custom"
    require_all_pass: true     # For "all": tests AND build AND lint

  self_correction:
    enabled: true              # Analyze failures and retry
    max_same_error: 3          # Try different approach after N identical errors
    read_full_output: true     # Force reading complete error output

  escalation:
    on_repeated_failure: true  # Same error 3x = escalate
    on_scope_creep: true       # Deviation from plan = escalate
    on_security_concern: true  # Security changes = escalate
```

#### Agent Models

```yaml
models:
  orchestrator: opus
  architect: opus
  developer: opus
  reviewer: opus
  skeptic: opus
  implementer: opus
  feedback: opus
  technical-writer: opus
```

#### Gemini Integration

```yaml
gemini_research:
  enabled: true
  fallback_to_opus: true       # Use Opus if Gemini unavailable

  context_gathering:
    include_base_classes: true
    include_referenced: true
    include_examples: true
    include_docs: true
    max_files: 100

  error_handling:
    repomix_unavailable: fallback  # fallback | warn | fail
    gemini_unavailable: fallback
    gemini_timeout: 120
```

#### Beads Integration

```yaml
beads:
  enabled: false
  auto_create_issue: false     # Create issue when starting
  auto_link: true              # Link to mentioned issues
  sync_status: true            # Update issue status
  add_comments: true           # Add progress comments
```

#### Auto-actions

```yaml
auto_actions:
  run_tests: true
  create_files: true
  modify_files: true
  run_build: true
  git_add: false               # Require approval
  git_commit: false            # Require approval
  git_push: false              # Require approval
```

## State Management

All workflow state is stored in `.tasks/TASK_XXX/`:

```
.tasks/
└── TASK_001_jwt-authentication/
    ├── state.json           # Current phase, progress, checkpoints
    ├── task.md              # Original task description
    ├── config.yaml          # Effective config (cascaded)
    ├── architect.md         # Architect output
    ├── developer.md         # Developer output
    ├── reviewer.md          # Reviewer findings
    ├── skeptic.md           # Skeptic analysis
    ├── plan.md              # Final approved plan
    ├── gemini-analysis.md   # Gemini research (if enabled)
    ├── repomix-context.json # Repomix config
    ├── repomix-output.txt   # Aggregated codebase
    └── errors.log           # Any failures
```

### State File Format

```json
{
  "task_id": "TASK_001",
  "description": "Add JWT authentication",
  "phase": "implementer",
  "phases_completed": ["architect", "developer", "reviewer", "skeptic"],
  "review_issues": [],
  "iteration": 1,
  "docs_needed": [],
  "implementation_progress": {
    "total_steps": 20,
    "current_step": 10,
    "steps_completed": ["1.1", "1.2", "2.1", "2.2", "2.3"]
  },
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T12:30:00Z"
}
```

### Memory Preservation

Agents can save discoveries to persistent memory that survives context compaction:

```
.tasks/
└── TASK_001_jwt-authentication/
    └── memory/
        └── discoveries.jsonl    # Agent learnings in JSONL format
```

**MCP Tools:**

| Tool | Purpose |
|------|---------|
| `workflow_save_discovery` | Save a learning to memory |
| `workflow_get_discoveries` | Retrieve saved learnings |
| `workflow_flush_context` | Get all learnings grouped by category (for context reload) |
| `workflow_search_memories` | Search learnings across multiple tasks |

**Discovery Categories:**

| Category | Use For |
|----------|---------|
| `decision` | Human decisions, architectural choices, trade-offs made |
| `pattern` | Code patterns, conventions, "how we do X here" |
| `gotcha` | Non-obvious issues, surprising behaviors, things that broke |
| `blocker` | Unresolved issues requiring human input |
| `preference` | User preferences discovered during the task |

See [docs/ai-context/memory-preservation.md](docs/ai-context/memory-preservation.md) for detailed usage guidance.

## Task Files

For complex tasks, create a markdown file:

```markdown
# Task: Implement Caching Layer

## Requirements
- [ ] Cache GET responses with configurable TTL
- [ ] Invalidate cache on POST/PUT/DELETE
- [ ] Add cache-control headers

## Success Criteria
- All tests pass
- Response time < 50ms for cached endpoints

## Technical Notes
- Use existing Redis connection from `src/lib/redis.ts`
- Follow patterns in `src/cache/base.ts`
- See `docs/api/caching.md` for API design

## Out of Scope
- Cache warming
- Multi-region cache sync
```

Run with:
```bash
/crew --loop-mode --task ./tasks/implement-caching.md
```

## Completion Signals

Agents output structured signals for state management:

| Signal | Meaning |
|--------|---------|
| `<promise>COMPLETE</promise>` | Agent finished successfully |
| `<promise>BLOCKED: reason</promise>` | Cannot proceed, needs input |
| `<promise>ESCALATE: reason</promise>` | Critical issue, needs human |

## When to Use What

| Scenario | Recommended Approach |
|----------|----------------------|
| Quick design question | `/crew ask architect "question"` |
| Second opinion on approach | `/crew ask skeptic` or `/crew ask reviewer` |
| New feature (needs design) | `/crew` (default with checkpoints) |
| Bug fix with clear repro | `/crew --loop-mode --verify tests` |
| "Make tests pass" | `/crew --loop-mode --verify tests` |
| "Fix the build" | `/crew --loop-mode --verify build` |
| Large refactor, review tomorrow | `/crew --loop-mode --no-checkpoints` |
| Security-sensitive changes | `/crew` (never skip checkpoints) |
| Overnight migration | `/crew --loop-mode --no-checkpoints --max-iterations 50` |

## Gemini + Repomix Integration

When enabled, the workflow uses Gemini's massive context window to analyze your codebase:

1. **Repomix** aggregates relevant files (base classes, referenced code, examples, docs)
2. **Gemini** analyzes the aggregated context and produces sections:
   - `ARCHITECTURAL_CONTEXT` - For the Architect agent
   - `IMPLEMENTATION_PATTERNS` - For the Developer agent
   - `REVIEW_CHECKLIST` - For the Reviewer agent
   - `FAILURE_MODES` - For the Skeptic agent
   - `DOCUMENTATION_CONTEXT` - For the Technical Writer agent

3. Each agent receives only its relevant section, keeping context focused

If Gemini or Repomix are unavailable, the workflow falls back to direct file context with Claude.

## Examples

See the `/examples` directory:

- `fix-tests.md` - Loop mode example for autonomous test fixing
- `implement-caching.md` - Multi-requirement feature implementation

## Troubleshooting

### Workflow stuck in loop
Check `.tasks/TASK_XXX/errors.log` for repeated errors. The workflow escalates after `max_same_error` identical failures, but you can manually resume:
```bash
/crew-resume TASK_XXX
```

### Gemini analysis timeout
Increase the timeout in config:
```yaml
gemini_research:
  error_handling:
    gemini_timeout: 300  # 5 minutes
```

### Agent not following plan
The Feedback agent detects deviations. If `escalation.on_scope_creep: true`, the workflow pauses for human review. Check the deviation classification in the agent output.

### Resume after crash
State is persisted to `.tasks/TASK_XXX/state.json`. Run:
```bash
/crew-resume
```
to see all resumable tasks.

## Uninstall

```bash
./uninstall.sh
```

This removes:
- Commands from `~/.claude/commands/`
- Agents from `~/.claude/agents/`
- Config from `~/.claude/crew-config.yaml`

Task state in `.tasks/` is preserved.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with `./install.sh` in a test environment
5. Submit a pull request

## License

MIT
