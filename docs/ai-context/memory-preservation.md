# Memory Preservation for AI Agents

This document describes how AI agents can preserve critical learnings across context compaction events using the workflow memory system.

## The Problem

When Claude's context window fills up, older content is compacted (summarized or dropped). Critical insights discovered during a task - debugging findings, human preferences, architectural decisions - can be lost. This forces agents to re-discover the same things repeatedly.

## Server-Side Compaction

The Anthropic API now supports server-side compaction (`compact-2026-01-12`) which auto-summarizes conversation context before it hits limits. When `compaction.enabled: true` in workflow config:

- The API automatically summarizes older turns rather than dropping them
- Custom instructions preserve task ID, workflow phase, progress, and active concerns
- After compaction fires, workflow state and discoveries are re-injected
- Compaction token costs are tracked via `workflow_record_cost(compaction_tokens=N)`

This largely replaces manual `workflow_flush_context` usage. However, the discovery tools below remain valuable for cross-task learning and explicit state preservation.

## The Solution

Three MCP tools allow agents to save discoveries to persistent storage before compaction occurs:

| Tool | Purpose |
|------|---------|
| `workflow_save_discovery` | Save a single learning |
| `workflow_get_discoveries` | Retrieve saved learnings |
| `workflow_flush_context` | Get all learnings for reload |

A fourth tool enables cross-task learning:

| Tool | Purpose |
|------|---------|
| `workflow_search_memories` | Search learnings across all tasks |

## Discovery Categories

Each discovery must be classified into one of five categories:

| Category | When to Use | Examples |
|----------|-------------|----------|
| `decision` | Human made a choice, trade-off was accepted | "User chose REST over GraphQL for simplicity", "Using Redis for cache, not Memcached" |
| `pattern` | Found a convention, "how we do X here" | "All API responses wrap in {data, error, meta}", "Tests use factory functions in tests/factories/" |
| `gotcha` | Something non-obvious caused problems | "Redis connection pool exhausts if not explicitly closed", "TypeScript strict mode breaks legacy imports" |
| `blocker` | Cannot proceed without human input | "Need AWS credentials for S3 integration", "Design decision needed: sync or async processing?" |
| `preference` | Learned a user preference | "User prefers verbose logging during dev", "Keep functions under 50 lines" |

## When to Save Discoveries

Save a discovery when:

1. **Human makes a decision** - Any time the user chooses between alternatives
2. **Something breaks unexpectedly** - The cause wasn't obvious from the code
3. **You find a pattern** - Especially undocumented conventions
4. **You're blocked** - Something needs human resolution
5. **User expresses a preference** - Even casual remarks about style/approach

Do NOT save:

- Obvious facts from documentation
- Temporary debugging thoughts
- Step-by-step progress updates
- Things already in the codebase's README or docs

## How to Use the Tools

### Saving a Discovery

```python
workflow_save_discovery(
    category="gotcha",
    content="Redis connection requires explicit close() in test teardown or pool exhausts after ~10 tests"
)
```

Response:
```json
{
    "success": true,
    "discovery": {
        "timestamp": "2024-01-15T10:30:00.000000",
        "category": "gotcha",
        "content": "Redis connection requires explicit close()..."
    },
    "task_id": "TASK_001_jwt-authentication"
}
```

### Retrieving Discoveries

Get all discoveries:
```python
workflow_get_discoveries()
```

Filter by category:
```python
workflow_get_discoveries(category="decision")
```

Response:
```json
{
    "discoveries": [
        {
            "timestamp": "2024-01-15T10:30:00.000000",
            "category": "decision",
            "content": "Using JWT with short-lived tokens (15min) + refresh tokens"
        }
    ],
    "count": 1,
    "task_id": "TASK_001_jwt-authentication"
}
```

### Before Context Compaction

When context is getting full (or when prompted to preserve state), call:

```python
workflow_flush_context()
```

Response:
```json
{
    "discoveries": [...],
    "count": 5,
    "by_category": {
        "decision": [
            {"timestamp": "...", "content": "Using JWT with short-lived tokens..."}
        ],
        "gotcha": [
            {"timestamp": "...", "content": "Redis connection requires explicit close()..."}
        ],
        "pattern": [
            {"timestamp": "...", "content": "All services extend BaseService in src/services/base.ts"}
        ]
    },
    "task_id": "TASK_001_jwt-authentication"
}
```

### After Context Reload

When resuming after compaction, reload your discoveries:

```python
# Get all discoveries to restore context
discoveries = workflow_get_discoveries()

# Or load specific categories first
decisions = workflow_get_discoveries(category="decision")
gotchas = workflow_get_discoveries(category="gotcha")
```

### Cross-Task Learning

Search for learnings from past tasks:

```python
workflow_search_memories(
    query="redis connection",
    category="gotcha",  # optional filter
    max_results=10
)
```

Response:
```json
{
    "results": [
        {
            "task_id": "TASK_001_jwt-authentication",
            "timestamp": "2024-01-15T10:30:00.000000",
            "category": "gotcha",
            "content": "Redis connection requires explicit close()...",
            "relevance": 2
        }
    ],
    "count": 1,
    "tasks_searched": 5
}
```

## Storage Format

Discoveries are stored in `.tasks/TASK_XXX/memory/discoveries.jsonl` as newline-delimited JSON:

```jsonl
{"timestamp": "2024-01-15T10:30:00.000000", "category": "decision", "content": "Using JWT..."}
{"timestamp": "2024-01-15T10:35:00.000000", "category": "gotcha", "content": "Redis requires..."}
```

This format:
- Supports append-only writes (safe for concurrent access)
- Is human-readable for debugging
- Survives partial writes (malformed lines are skipped)

## Best Practices

### Write Good Discovery Content

Good:
```
"Redis connection pool exhausts if connections aren't explicitly closed in test teardown.
Fixed by adding pool.disconnect() in afterEach() hook."
```

Bad:
```
"Redis broke"
```

Include:
- What the issue/pattern is
- Why it matters
- How it was resolved (if applicable)

### Save Early, Save Often

Don't wait until context is full. Save discoveries as you learn them:

```python
# Discovered something? Save it immediately
workflow_save_discovery(
    category="pattern",
    content="Error responses use ErrorBoundary component from src/components/errors/ErrorBoundary.tsx"
)
```

### Check Past Memories First

Before starting a new task, check if previous tasks discovered relevant patterns:

```python
# Starting work on authentication?
workflow_search_memories(query="auth authentication jwt token")
```

### Categorize Accurately

The category determines how discoverable the learning is later:

- Use `decision` for choices (these help understand "why")
- Use `pattern` for conventions (these help with consistency)
- Use `gotcha` for problems (these prevent repeated mistakes)
- Use `blocker` sparingly - only for truly blocking issues
- Use `preference` for style/approach preferences

## Integration with Workflow

The memory preservation tools integrate with the broader agentic workflow:

1. **Architect agent** - Save architectural decisions
2. **Developer agent** - Save patterns and implementation decisions
3. **Implementer agent** - Save gotchas discovered during coding
4. **Feedback agent** - Save deviations and their resolutions
5. **Technical Writer** - Reference decisions and patterns in documentation

## Troubleshooting

### "No active task found"

The tools require an active task context. Either:
- Specify `task_id` explicitly: `workflow_save_discovery(task_id="TASK_001", ...)`
- Ensure a task is active via the workflow state

### Empty discoveries after reload

Check:
1. Task ID is correct
2. File exists: `.tasks/TASK_XXX/memory/discoveries.jsonl`
3. File isn't empty or malformed

### Search returns no results

- Keywords must match exactly (case-insensitive)
- Check if discoveries exist: `workflow_get_discoveries()`
- Try broader search terms
