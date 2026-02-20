# Workflow Configuration

View and modify workflow configuration settings.

## Command: /crew-config

### Display Current Configuration

1. Read `~/.opencode/workflow-config.yaml`
2. Parse the YAML and display the **actual values** in a formatted table
3. Use `✓ Enabled` / `✗ Disabled` based on the real config values — do NOT use hardcoded defaults

Display format:

```
┌─────────────────────────────────────────────────────────────┐
│ Workflow Configuration (~/.opencode/workflow-config.yaml)       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ PLANNING CHECKPOINTS                                         │
│   After Architect:  <value from checkpoints.planning>        │
│   After Developer:  <value>                                  │
│   After Reviewer:   <value>                                  │
│   After Skeptic:    <value>                                  │
│                                                              │
│ IMPLEMENTATION CHECKPOINTS                                   │
│   At 25%:           <value from checkpoints.implementation>  │
│   At 50%:           <value>                                  │
│   At 75%:           <value>                                  │
│   Before Commit:    <value>                                  │
│                                                              │
│ FEEDBACK TRIGGERS                                            │
│   On Deviation:     <value from checkpoints.feedback>        │
│   On Test Failure:  <value>                                  │
│   On Major Change:  <value>                                  │
│                                                              │
│ MODELS                                                       │
│   <list each agent and its model from models section>        │
│                                                              │
│ PATHS                                                        │
│   Knowledge Base:   <knowledge_base value>                   │
│   Task Directory:   <task_directory value>                   │
│                                                              │
│ WORKFLOW MODE                                                │
│   Default:          <workflow_mode.default_mode value>        │
│   Modes: full | turbo | fast | minimal | auto                │
│                                                              │
│ EFFORT LEVELS                                                │
│   API: thinking=adaptive, output_config.effort=<level>       │
│   Values: low | medium | high | max (max=Opus 4.6 only)     │
│                                                              │
│ COMPACTION                                                   │
│   Enabled:          <compaction.enabled value>                │
│   Model:            <compaction.model value>                  │
│   Trigger:          <compaction.trigger_tokens value> tokens  │
│   Pause after:      <compaction.pause_after_compaction value> │
│                                                              │
│ COST TRACKING                                                │
│   Enabled:          <cost_tracking.enabled value>             │
│                                                              │
│ AGENT TEAMS (experimental)                                   │
│   Enabled:          <agent_teams.enabled value>               │
│   Parallel Review:  <agent_teams.parallel_review.enabled>     │
│   Parallel Impl:    <agent_teams.parallel_implementation...>  │
│     Max Concurrent:  <max_concurrent_agents value>           │
│     Independent Only: <require_independent_steps value>      │
│                                                              │
│ SUBAGENT LIMITS                                              │
│   Planning:         <subagent_limits.max_turns.planning_agents> turns │
│   Implementation:   <subagent_limits.max_turns.implementation_agents> turns │
│   Documentation:    <subagent_limits.max_turns.documentation_agents> turns │
│   Consultation:     <subagent_limits.max_turns.consultation_agents> turns │
│   Direct Tools:     <subagent_limits.prefer_direct_tools>    │
│   Timeout:          <subagent_limits.agent_timeout>s         │
│                                                              │
│ PARALLELIZATION                                              │
│   Enabled:          <parallelization.enabled value>           │
│   Timeout:          <parallelization.timeout_seconds value>s  │
│   Merge Strategy:   <parallelization.merge_strategy value>    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

Also check for project-level overrides at `<repo>/.claude/workflow-config.yaml` and display any differences.

### Interactive Configuration

After displaying, ask the user what they want to change:

**Checkpoint Settings:**
- "Which planning checkpoints should require approval?"
- "Which implementation checkpoints should be enabled?"

**Path Settings:**
- "Where is your knowledge base (docs/ai-context/)?"
- "Where should task files be stored?"

**Model Settings:**
- "Which model should agents use? (opus/sonnet/haiku)"

### Quick Presets

Offer preset configurations:

1. **Maximum Control** (default)
   - All planning checkpoints enabled
   - 50% and commit checkpoints enabled
   - All feedback triggers enabled

2. **Fast Flow**
   - Only after_architect and before_commit checkpoints
   - Only on_deviation trigger
   - Good for familiar tasks

3. **Full Auto** (use with caution)
   - Only before_commit checkpoint
   - Minimal human interruption
   - For very well-defined tasks

### Apply Changes

After getting user preferences:
1. Update `~/.opencode/workflow-config.yaml`
2. Confirm changes
3. Show new configuration

Now, read `~/.opencode/workflow-config.yaml`, display the current configuration with actual values, and ask what the user wants to change.
