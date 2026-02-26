# Copilot CLI Instructions for Agentic Workflow

## Worktree Auto-Resume

If a `.crew-resume` file exists in the repository root, you are in a **git worktree** created by crew-board. On session startup:
1. Read `.crew-resume` immediately
2. Note the `task_id` and `tasks_path` values
3. Run the resume command shown in the file (e.g., `@crew-resume TASK_XXX`)
4. Do NOT create a new `.tasks/` directory — the symlink already points to the main repo

This repository implements a multi-agent development workflow system. You have access to specialized agents for different development phases.

## Available Custom Agents

Use these agents with `/agent` command or by mentioning them in your prompt:

### Planning Phase Agents

**crew-architect** - Analyzes system-wide architectural implications
- Use for: System design, integration points, risk analysis
- Example: "Use crew-architect to analyze adding a caching layer"

**crew-developer** - Creates detailed step-by-step implementation plans
- Use for: Breaking down features into executable steps
- Example: "Use crew-developer to create a plan for user authentication"

**crew-reviewer** - Validates plans for completeness and correctness
- Use for: Checking plans before implementation
- Example: "Use crew-reviewer to validate the authentication plan"

**crew-skeptic** - Stress-tests plans for edge cases and failure modes
- Use for: Finding what could go wrong in production
- Example: "Use crew-skeptic to find edge cases in the caching design"

### Implementation Phase Agents

**crew-implementer** - Executes implementation plans step-by-step
- Use for: Carrying out detailed plans
- Example: "Use crew-implementer to execute the plan in .tasks/TASK_001/plan.md"

**crew-feedback** - Compares implementation against original plan
- Use for: QA and deviation detection
- Example: "Use crew-feedback to verify the implementation matches the plan"

### Documentation Phase Agents

**crew-technical-writer** - Updates AI-context documentation
- Use for: Documenting patterns and conventions learned during implementation
- Example: "Use crew-technical-writer to document the authentication pattern"

## MCP Tools Available

The agentic-workflow MCP server provides 50+ tools for workflow management:

### Workflow State Management
- `workflow_initialize` - Start a new workflow task
- `workflow_get_state` - Read current task state
- `workflow_transition` - Move between workflow phases
- `workflow_complete_phase` - Mark phase as complete

### Memory & Learning
- `workflow_save_discovery` - Save learnings (patterns, gotchas, decisions)
- `workflow_get_discoveries` - Retrieve saved learnings
- `workflow_flush_context` - Get all discoveries for context reload
- `workflow_search_memories` - Search across tasks

### Configuration
- `config_get_effective` - Get merged configuration
- `config_get_checkpoint` - Check if checkpoint is enabled
- `workflow_get_effort_level` - Get thinking depth for agent

### Progress Tracking
- `workflow_set_implementation_progress` - Track implementation steps
- `workflow_complete_step` - Mark individual steps complete
- `workflow_add_concern` - Flag issues or concerns
- `workflow_add_review_issue` - Record review findings

### Cost Tracking
- `workflow_record_cost` - Record token usage and costs
- `workflow_get_cost_summary` - Get cost breakdown by agent

## Workflow Pattern

### Full Multi-Agent Workflow

For complex features requiring multiple perspectives:

```
1. Initialize: workflow_initialize({description: "Add caching layer"})
2. Architect: Use crew-architect to analyze system impact
3. Developer: Use crew-developer to create implementation plan
4. Reviewer: Use crew-reviewer to validate the plan
5. Skeptic: Use crew-skeptic to stress-test for edge cases
6. Implement: Use crew-implementer to execute the plan
7. Feedback: Use crew-feedback to verify against plan
8. Document: Use crew-technical-writer to update docs
```

### Quick Consultation

For getting a single agent's opinion without full workflow:

```
Use crew-skeptic to analyze "What edge cases should I consider for this rate limiting implementation?"
```

### Task State Location

All workflow state is stored in `.tasks/TASK_XXX/`:
- `state.json` - Current phase, progress, checkpoints
- `plan.md` - Implementation plan
- `architect.md` - Architectural analysis
- `discoveries.jsonl` - Saved learnings

## Configuration

Configuration cascade (each level overrides previous):
1. Global: `~/.claude/` or `~/.copilot/` or `~/.gemini/` or `~/.opencode/workflow-config.yaml`
2. Project: `.claude/` or `.copilot/` or `.gemini/` or `.opencode/workflow-config.yaml`
3. Task: `.tasks/TASK_XXX/config.yaml`
4. Runtime: Parameters passed to MCP tools

The system checks `.claude/` first, then `.copilot/`, then `.gemini/`, then `.opencode/`, using whichever exists.

## Best Practices

### When to Use Which Agent

- **Architect**: Before starting any implementation - get system-level perspective
- **Developer**: After architecture approved - create detailed plan
- **Reviewer**: Before implementation - catch issues early
- **Skeptic**: Throughout planning - find edge cases
- **Implementer**: With approved plan - execute step by step
- **Feedback**: After implementation - verify quality
- **Technical Writer**: End of task - capture knowledge

### Using Workflow Tools

Always initialize before starting:
```javascript
workflow_initialize({
  task_id: "TASK_042", // Optional, auto-generated if not provided
  description: "Add JWT authentication"
})
```

Save important learnings:
```javascript
workflow_save_discovery({
  category: "decision" | "pattern" | "gotcha" | "blocker" | "preference",
  content: "Description of what you learned",
  tags: ["authentication", "security"]
})
```

Track progress:
```javascript
workflow_set_implementation_progress({
  total_steps: 10,
  completed_steps: 5,
  current_step: "2.3"
})
```

## Example Usage

### Starting a New Feature

```
I need to add user authentication with JWT. Let me use the workflow:

1. First, let me initialize the task:
   [Use workflow_initialize]

2. Get architectural perspective:
   Use crew-architect to analyze the authentication requirements

3. Create detailed plan:
   Use crew-developer to create implementation plan based on architect's analysis

4. Validate the plan:
   Use crew-reviewer to check for issues
   Use crew-skeptic to find edge cases

5. Implement:
   Use crew-implementer to execute the plan step by step

6. Verify:
   Use crew-feedback to compare implementation vs plan

7. Document:
   Use crew-technical-writer to update AI-context docs
```

### Quick Edge Case Analysis

```
Use crew-skeptic to analyze: "What could go wrong with this caching implementation?"
[Paste code or describe approach]
```

### Reviewing Existing Code

```
Use crew-reviewer to check if this authentication middleware is secure:
[Paste code]
```

## Knowledge Base

This repository maintains AI-context documentation in `docs/ai-context/`:
- `patterns.md` - Common code patterns
- `conventions.md` - Naming and organization rules
- `gotchas.md` - Non-obvious issues and solutions
- `architecture.md` - System design decisions
- `testing.md` - Testing guidelines

Agents reference and update these files during workflow execution.

## Tool Discipline

When exploring the codebase:
- Use `grep` for searching file contents
- Use `glob` for finding files by pattern
- Use `view` for reading files
- Avoid spawning Task agents for simple searches

## Memory Preservation

Discoveries saved with `workflow_save_discovery` persist across:
- Context window compaction
- Session restarts
- Multiple related tasks

Categories for discoveries:
- `decision` - Architectural or design decisions
- `pattern` - Code patterns and conventions
- `gotcha` - Surprising behaviors or issues
- `blocker` - Unresolved issues needing human input
- `preference` - User preferences discovered during work

## Copilot vs Claude Code — What's Different

This workflow system was built for Claude Code and adapted for Copilot. The MCP tools and agents work on both platforms, but some features are Claude Code-only:

### Manual Orchestration (No `/crew` command)

Claude Code has a `/crew` slash command that automatically chains agents through the workflow. In Copilot, you drive each step manually:

1. Call `workflow_initialize` to start a task
2. Invoke each agent yourself (e.g., "Use crew-architect to...")
3. Call `workflow_transition` between phases
4. Call `workflow_complete_phase` when done

### No Automatic Agent Chaining

Claude Code's Task tool spawns sub-agents that run in parallel. Copilot doesn't have an equivalent — each agent invocation is a separate conversation turn. This means:
- You invoke one agent at a time
- You're responsible for passing context between agents
- The MCP tools still track state, so progress persists

### No Hook Enforcement

Claude Code uses hooks to enforce workflow rules (e.g., blocking transitions without checkpoint approval). In Copilot, the workflow tools still track state but don't block invalid operations — discipline is on the user.

### No-Op Features

These config sections exist but have no effect on Copilot (they don't cause errors):
- `effort_levels` — Controls Claude's extended thinking depth
- `compaction` — Controls Claude's context window management
- `agent_teams` — Controls parallel agent spawning

## Getting Help

- View agent details: Check `agents/*.md` (source) or `~/.copilot/agents/crew-*.md` (installed)
- List MCP tools: Use `/mcp show` in Copilot
- Check workflow state: Use `workflow_get_state`
- View cost tracking: Use `workflow_get_cost_summary`
