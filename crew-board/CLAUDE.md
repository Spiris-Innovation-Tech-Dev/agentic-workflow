# crew-board — Agent Instructions

Rust TUI dashboard for cross-project agentic-workflow task monitoring. Built with ratatui + crossterm.

## Build & Test

```bash
cd crew-board
cargo build                  # Dev build
cargo build --release        # Optimized binary (strip + LTO)
cargo test                   # All 16 unit tests
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
├── launcher.rs      # Terminal launch: detect env, spawn wt.exe/tmux/osascript, color schemes
├── worktree.rs      # Native worktree creation: task ID, git ops, state.json, symlink
├── cleanup.rs       # Worktree cleanup: candidate discovery, dry-run preview, execute via script
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
    ├── status_bar.rs # Bottom: view tabs + contextual keybinding hints + aggregate stats
    ├── launch_popup.rs # F2 popup: terminal + AI host selection
    ├── create_popup.rs # F4 popup: multi-step worktree creation wizard
    ├── cleanup_popup.rs# F6 popup: multi-select worktree cleanup with dry-run preview
    ├── search_popup.rs # F3 popup: full-text search across tasks + artifacts
    └── styles.rs     # 8 crew color schemes, phase styles, selection/border/hint helpers
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
1. Help overlay open → any key closes it
2. Search popup open → search-specific keys
3. Create worktree popup open → popup keys (text input, selection, toggles)
4. Cleanup worktree popup open → popup keys (multi-select, toggles, preview)
5. Launch popup open → popup keys only
6. Right pane focused + non-Overview mode → doc/history navigation
7. Default → tree nav, view switching, shortcuts

**Esc behavior:** Esc never quits the application. It only closes popups, backs out of detail views, or switches focus from right pane to left pane. Use `q` or `F10` to quit.

### Worktree Creation (`F4` key)
Native Rust reimplementation of the core steps from `scripts/setup-worktree.py`. Press `F4` on a repo row to:
1. Enter task description (text input via `tui-input`)
2. Select AI host (Claude/Copilot/Gemini/OpenCode)
3. Toggle settings (pull latest, launch terminal)
4. Background thread runs git operations (~100ms vs ~2s for Python)
5. Shows result with task ID, branch, directory, color scheme
6. Optionally launches a color-themed terminal tab

**What it does:** Validates git repo, fetches/pulls, generates task ID (scans `.tasks/`), creates `state.json`, runs `git worktree add`, symlinks `.tasks/`, assigns color scheme.

**What it skips (deferred to AI agent):** Settings patching, dependency install, WSL path fix, post-setup commands, Jira transitions — all handled by the agent on first `/crew resume`.

The worktree is created at `../{repo-name}-worktrees/TASK_XXX` with branch `crew/{slugified-description}`.

### Worktree Cleanup (`F6` key)
Press `F6` on a repo row to clean up worktrees:
1. Multi-select worktrees with Space (completed tasks pre-selected, `a` toggles all)
2. Toggle settings: delete branch, keep on disk (recyclable)
3. Dry-run preview showing exact git commands and warnings (unmerged branches, incomplete workflows)
4. Background thread runs `scripts/cleanup-worktree.py` for each selected task
5. Shows results with success/failure per worktree

**Safety:** Only removes git worktree directories and branches. The `.tasks/` directory and all task artifacts are NEVER deleted.

**Modes:** Remove (git worktree remove + state update) or Recycle (mark recyclable, keep on disk for reuse).

### UI Style System
Central style helpers in `styles.rs` ensure visual consistency:
- `selected_style()` — blue background (#2A4A6B) for selected rows everywhere
- `focused_border_style()` / `unfocused_border_style()` — bold cyan vs dim gray borders
- `popup_selected_style()` — delegates to `selected_style()` (single source of truth)
- `hint_style()` — dim gray for keybinding hints

Pane focus is indicated by bold border + `◄` marker in the title. Detail pane titles show breadcrumb trails (e.g. `TASK_003 > Documents > Architect Analysis`).

### Status Bar (Norton Commander-style)
Two-line status bar:
- **Line 1**: View tabs + contextual navigation hints + aggregate stats
- **Line 2**: NC-style F-key bar: `F1Help  F2Launch  F3Search  F4New  F5Rfrsh  F6Clean  ...  F10Quit`

When a popup is open, line 2 shows popup-specific hints instead of the F-key bar.

### Color Schemes
8 schemes from Python `CREW_COLOR_SCHEMES` (state_tools.py), indexed by `color_scheme_index` from worktree state. Used for tree row accents, detail pane colors, and terminal tab colors.

`launcher.rs` provides `ColorSchemeHex` with hex strings for terminal commands:
- Windows Terminal: `--tabColor` and `--colorScheme` args to `wt.exe`
- tmux: `set-option window-style bg=...,fg=...`

## Data Sources

| Source | Path | Format |
|--------|------|--------|
| Task state | `.tasks/TASK_XXX/state.json` | JSON |
| Task artifacts | `.tasks/TASK_XXX/*.md` | Markdown |
| Beads issues | `.beads/issues.jsonl` | JSONL (one JSON per line) |
| Config (global) | `~/.claude/workflow-config.yaml` | YAML |
| Config (project) | `config/workflow-config.yaml` | YAML |
| User settings | `~/.config/crew-board.toml` | TOML |

## Adding a New Popup

Follow the pattern established by `launch_popup.rs` and `create_popup.rs`:
1. Create `src/ui/new_popup.rs` with `pub fn draw(frame, app)` using `centered_rect()` for positioning
2. Add popup state struct + step enum to `app.rs`
3. Add `Option<NewPopup>` field to `App` struct
4. Add lifecycle methods: `open_*`, `*_handle_key`, `close_*`
5. Register in `src/ui/mod.rs` — add `pub mod` and draw overlay call
6. Add key routing priority in `main.rs` event loop (popups go first)
7. Add keybinding hint in `status_bar.rs`

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
- **Popup priority**: Help overlay > search popup > create popup > cleanup popup > launch popup > detail nav > default. All must be checked before default key handling.
- **Background threads**: `create_worktree()` runs on `std::thread::spawn`. Poll `JoinHandle::is_finished()` each tick (250ms). No async runtime needed.
- **`F4`/`F6` key scope**: Only works on Repo rows — `open_create_popup()` and `open_cleanup_popup()` return early on Task rows.
