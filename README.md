# Agentic Workflow

A multi-agent development workflow for Claude Code that orchestrates specialized AI agents through planning, implementation, and documentation phases.

## Features

- **Multi-agent architecture** - Specialized agents for different concerns
- **Human checkpoints** - Control points for review and approval
- **Loop mode** - Ralph Wiggum-style autonomous iteration until success
- **Configuration cascade** - Global → Project → Task → Command-line overrides
- **Beads integration** - Optional issue tracking integration
- **Technical documentation** - Automatic AI-context documentation updates

## Installation

```bash
git clone https://github.com/johanyman/agentic-workflow.git
cd agentic-workflow
./install.sh
```

## Quick Start

### Simple task (with checkpoints)
```bash
/workflow "Add user authentication with JWT"
```

### Loop mode (autonomous until tests pass)
```bash
/workflow --loop-mode --verify tests "Fix all failing tests"
```

### Overnight autonomous run
```bash
/workflow --loop-mode --no-checkpoints --max-iterations 50

Migrate all API endpoints to v2:
- Update request/response types
- Add backward compatibility
- Update all tests
```

## Agents

The workflow uses specialized agents, each with a specific focus:

| Agent | Phase | Role |
|-------|-------|------|
| **Architect** | Planning | System design, boundaries, risks |
| **Developer** | Planning | Detailed implementation plan |
| **Reviewer** | Planning | Plan validation, security review |
| **Skeptic** | Planning | Edge cases, failure modes |
| **Implementer** | Implementation | Execute plan step-by-step |
| **Feedback** | Implementation | Detect deviations from plan |
| **Technical Writer** | Documentation | Update AI-context docs |

## Workflow Phases

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

## Command-Line Options

| Option | Description |
|--------|-------------|
| `--loop-mode` | Enable autonomous looping until success |
| `--no-loop` | Disable loop mode |
| `--max-iterations <n>` | Max attempts per step (default: 10) |
| `--verify <method>` | Verification: `tests`, `build`, `lint`, `all` |
| `--no-checkpoints` | Skip human checkpoints (fully autonomous) |
| `--beads <issue>` | Link to beads issue |
| `--task <file>` | Read task from markdown file |

## Configuration

Configuration cascades from global to specific:

```
~/.claude/workflow-config.yaml          ← Global defaults
       ↓
<repo>/.claude/workflow-config.yaml     ← Project overrides
       ↓
.tasks/TASK_XXX/config.yaml             ← Task-specific
       ↓
Command-line args                        ← Highest priority
```

### Key Configuration Options

```yaml
# Checkpoints - when to pause for human approval
checkpoints:
  planning:
    after_architect: true
    after_reviewer: true
    after_skeptic: true
  implementation:
    at_50_percent: true
    before_commit: true

# Loop mode settings
loop_mode:
  enabled: false
  verification:
    method: tests          # tests | build | lint | all
  max_iterations:
    per_step: 10
    before_escalate: 5     # Pause for human after N iterations

# Beads integration
beads:
  enabled: false
  auto_create_issue: false
  sync_status: true
```

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

## Notes
- Use existing Redis connection
- Follow patterns in src/cache/base.ts
```

Then run:
```bash
/workflow --loop-mode --task ./my-task.md
```

## Completion Promises

Agents output signals for clear state management:

| Signal | Meaning |
|--------|---------|
| `<promise>AGENT_COMPLETE</promise>` | Agent finished successfully |
| `<promise>BLOCKED: reason</promise>` | Cannot proceed, needs input |
| `<promise>ESCALATE: reason</promise>` | Critical issue, needs human |

## When to Use What

| Scenario | Recommended |
|----------|-------------|
| New feature (needs design) | Default (with checkpoints) |
| Bug fix with clear repro | `--loop-mode` |
| "Make tests pass" | `--loop-mode --verify tests` |
| Large refactor, review tomorrow | `--loop-mode --no-checkpoints` |
| Security-sensitive | Default (never skip checkpoints) |

## Uninstall

```bash
./uninstall.sh
```

## License

MIT
