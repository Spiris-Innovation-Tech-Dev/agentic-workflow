## Tool Discipline

Use direct tools for codebase exploration:
- Use `read_file` for reading file contents
- Use `grep_search` for searching file contents
- Use `list_directory` for finding files
- Use `run_shell_command` for git operations, tests, builds, and other system operations
- Do not spawn sub-agents for simple searches

## Git Safety

When working in a shared repository:
- Do **NOT** use git stash, git worktree directly (use MCP tools instead), or git clean commands
- Do **NOT** switch branches unless explicitly requested by the user
- Do **NOT** run `git commit`, `git push`, or `git add` unless explicitly requested
- If you notice untracked or modified files outside your scope, ignore them
- Never run `git checkout .` or `git restore .` — this would discard others' work-in-progress
