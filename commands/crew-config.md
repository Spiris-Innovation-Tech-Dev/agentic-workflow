# Workflow Configuration

View and modify workflow configuration settings.

## Command: /crew-config

### Current Configuration

Read and display `~/.claude/crew-config.yaml`:

```
┌─────────────────────────────────────────────────────────────┐
│ Workflow Configuration                                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ PLANNING CHECKPOINTS                                         │
│   After Architect:  ✓ Enabled                               │
│   After Developer:  ✗ Disabled                              │
│   After Reviewer:   ✓ Enabled                               │
│   After Skeptic:    ✓ Enabled                               │
│                                                              │
│ IMPLEMENTATION CHECKPOINTS                                   │
│   At 25%:           ✗ Disabled                              │
│   At 50%:           ✓ Enabled                               │
│   At 75%:           ✗ Disabled                              │
│   Before Commit:    ✓ Enabled                               │
│                                                              │
│ FEEDBACK TRIGGERS                                            │
│   On Deviation:     ✓ Enabled                               │
│   On Test Failure:  ✓ Enabled                               │
│   On Major Change:  ✓ Enabled                               │
│                                                              │
│ MODELS                                                       │
│   All agents:       opus                                     │
│                                                              │
│ PATHS                                                        │
│   Knowledge Base:   docs/ai-context/                         │
│   Task Directory:   .tasks/                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Interactive Configuration

Ask the user what they want to change:

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
1. Update `~/.claude/crew-config.yaml`
2. Confirm changes
3. Show new configuration

Now, display current configuration and ask what the user wants to change.
