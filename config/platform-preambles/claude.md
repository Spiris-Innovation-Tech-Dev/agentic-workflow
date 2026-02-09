## Tool Discipline

Use **direct tools** for codebase exploration — do NOT spawn subagents (Task tool) for discovery:
- **Grep** for searching code content (not `grep` or `rg` via Bash)
- **Glob** for finding files by pattern (not `find` via Bash)
- **Read** for reading file contents (not `cat` via Bash)
- **Bash** only for git commands, tests, builds, and other system operations

Never use `Task(subagent_type="Explore", ...)` or similar when Grep/Glob/Read can answer the question in 1-3 calls. Subagent discovery loops are slow and rarely yield better results than direct tool calls.

## Git Safety

When working in a shared repository:
- Do **NOT** use git stash, git worktree, or git clean commands
- Do **NOT** switch branches unless explicitly requested by the user
- Do **NOT** run `git commit`, `git push`, or `git add` unless explicitly requested
- If you notice untracked or modified files outside your scope, ignore them
- Never run `git checkout .` or `git restore .` — this would discard others' work-in-progress
