# crew-board — Agent Instructions

Rust TUI dashboard for cross-project agentic-workflow task monitoring. Built with ratatui + crossterm.

## Build & Test

```bash
cd crew-board
cargo build                  # Dev build
cargo build --release        # Optimized binary (strip + LTO)
cargo test                   # All 12 unit tests
cargo clippy                 # Lint (fix all warnings before committing)
```

The release binary lands at `target/release/crew-board` (~1.6MB).

## Architecture

```
src/
├── main.rs          # CLI parsing (clap), terminal setup, event loop
├── app.rs           # Application state: tree nav, views, popups, doc viewer
├── settings.rs      # Loads ~/.config/crew-board.toml (TOML)
├── discovery.rs     # Repo discovery: --repo paths + --scan directories
├── launcher.rs      # Terminal launch: detect env, spawn wt.exe/tmux/osascript
├── data/
│   ├── mod.rs       # RepoData: aggregates tasks + issues + config per repo
│   ├── task.rs      # Parses .tasks/*/state.json, discovers *.md artifacts
│   ├── beads.rs     # Parses .beads/issues.jsonl (stream, skip malformed)
│   └── config.rs    # Config cascade: global → project → task levels
└── ui/
    ├── mod.rs        # Root layout: main content + status bar + popup overlay
    ├── task_list.rs  # Left pane: tree view with repo/task rows
    ├── detail_pane.rs# Right pane: overview, doc list, doc reader, history
    ├── beads_view.rs # View 2: issues list + detail
    ├── config_view.rs# View 3: config cascade display
    ├── cost_view.rs  # View 4: cost summary from workflow state
    ├── status_bar.rs # Bottom: view tabs + keybindings + aggregate stats
    ├── launch_popup.rs # F2 popup: terminal + AI host selection
    └── styles.rs     # 8 crew color schemes, phase styles, helpers
```

## Key Patterns

### Data Layer
- All structs use `#[serde(default)]` — tolerant of missing/extra fields
- `load_tasks()` and `load_issues()` silently skip malformed entries
- `.tasks/` symlinks in worktrees are resolved via `canonicalize()`
- Artifacts (architect.md, developer.md, etc.) are discovered at runtime from the task directory

### Navigation Model
- Tree view: flattened `Vec<TreeRow>` where `TreeRow` is either `Repo(idx)` or `Task(repo_idx, task_idx)`
- `expanded_repos: HashSet<usize>` tracks which repos are open
- `rebuild_tree()` must be called after any expand/collapse or data refresh

### Detail Pane Modes
```
Overview ──d──> DocList ──Enter──> DocReader
    │                      │            │
    │<─────Esc────────────Esc──────Esc──┘
    │
    │──h──> History
    │          │
    │<───Esc───┘
```
- `cached_artifacts` and `cached_task_dir` prevent re-scanning on every draw
- `ensure_artifacts()` is called on tree cursor change and refresh

### Event Loop
Keys are routed in priority order:
1. Launch popup open → popup keys only
2. Right pane focused + non-Overview mode → doc/history navigation
3. Default → tree nav, view switching, shortcuts

### Color Schemes
8 schemes from Python `CREW_COLOR_SCHEMES` (state_tools.py), indexed by `color_scheme_index` from worktree state. Used for tree row accents and detail pane colors.

## Data Sources

| Source | Path | Format |
|--------|------|--------|
| Task state | `.tasks/TASK_XXX/state.json` | JSON |
| Task artifacts | `.tasks/TASK_XXX/*.md` | Markdown |
| Beads issues | `.beads/issues.jsonl` | JSONL (one JSON per line) |
| Config (global) | `~/.claude/workflow-config.yaml` | YAML |
| Config (project) | `config/workflow-config.yaml` | YAML |
| User settings | `~/.config/crew-board.toml` | TOML |

## Adding a New View

1. Create `src/ui/new_view.rs` with `pub fn draw(frame, app, area)`
2. Register in `src/ui/mod.rs` — add `pub mod` and dispatch in `draw()`
3. Add variant to `ActiveView` enum in `app.rs`
4. Add number key binding in `main.rs`
5. Add tab label in `status_bar.rs`

## Adding a New Data Source

1. Create parser in `src/data/new_source.rs`
2. Add field to `RepoData` in `data/mod.rs`
3. Load in `RepoData::load()`
4. Use `#[serde(default)]` on all fields for resilience

## Common Gotchas

- **Worktree paths**: The `worktree.path` field in state.json is relative. Use `launch.worktree_abs_path` for absolute paths.
- **WSL paths**: `wt.exe` runs on Windows side but receives Linux paths via `wsl.exe --cd`. Always include explicit `cd` in bash commands.
- **Login shells**: `bash -lic` sources profile which may reset cwd. Always prefix commands with `cd <dir> &&`.
- **Tree rebuild**: Forgetting `rebuild_tree()` after changing `expanded_repos` causes stale cursor state.
- **Detail mode reset**: Must reset `detail_mode` to `Overview` when tree cursor changes.
