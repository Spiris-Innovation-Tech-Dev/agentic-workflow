# Changelog

All notable changes to crew-board are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [0.3.2] - 2026-02-27

### Fixed
- **Search debounce** — F3 search now waits 200ms after the last keystroke before
  running the search, instead of searching on every single keypress. Reduces
  unnecessary disk I/O when typing quickly.

## [0.3.1] - 2026-02-26

### Fixed
- **Tree navigation no longer wraps** — pressing Down at the last item or Up at
  the first item now stops (clamps) instead of wrapping around to the other end

### Added
- **Arrow key expand/collapse** — Right arrow (or `l`) expands a repo node,
  Left arrow collapses it
- **PgUp/PgDn tree paging** — page through the task list a screenful at a time,
  clamped to top/bottom like the arrow keys
- **Vertical scrollbars** — both left pane (task list) and right pane (detail,
  documents, history, repo summary) now show a scrollbar when content overflows
  the visible area

## [0.3.0] - 2026-02-23

### Added
- **Archived task support** — deleted tasks now appear in the tree view with a
  `✗` marker and `[deleted]` label instead of silently disappearing
- **Gap detection** — task IDs between 1 and the highest known ID that are
  missing from disk are filled in as archived placeholders
- **`.registry.jsonl`** — append-only registry in `.tasks/` records task
  metadata at creation time; used to enrich archived task display with
  description and branch info
- **`metadata.json` fallback** — task directories with no `state.json` but a
  `metadata.json` (written by external setup scripts) are loaded as archived
  tasks with description, branch, and Jira key
- **Jira key display** — archived tasks from `metadata.json` show their Jira
  key in the task list row and detail pane (yellow text)
- **`LoadedTask` wrapper** — replaces bare `(PathBuf, TaskState)` tuples with a
  struct carrying `dir`, `state`, `archived` flag, and optional `jira_key`
- Repo summary now shows archived task count alongside active/total

### Changed
- Data layer refactored from `Vec<(PathBuf, TaskState)>` to `Vec<LoadedTask>`
  across all modules (app, cleanup, cost_view, search, detail_pane, task_list)
- Archived tasks are excluded from cleanup candidates, search file scanning,
  document/history views, and terminal launch
- `active_task_count()` excludes archived tasks; new `archived_task_count()`
  method added to `RepoData`

## [0.2.0] - 2026-02-19

### Added
- **F1 Help overlay** listing all keybindings (press any key to dismiss)
- **Norton Commander-style F-key bar** at the bottom of the screen
  (`F1Help  F2Launch  F3Search  F4New  F5Rfrsh  ...  F10Quit`)
- **Enhanced History view** ("State Inspector") showing full state.json details:
  workflow mode (effective, requested, detection reason, confidence, cost estimate),
  implementation progress bar with step breakdown, worktree details (branch, base,
  path, color, AI host, terminal), documentation gaps, and cost summary
- `F10` as an additional quit binding

### Changed
- **Esc never quits** — it only closes popups, backs out of detail views, or
  switches focus from right pane to left pane. Use `q` or `F10` to quit.
- New worktree shortcut moved from `n` to `F4` for F-key consistency
- Status bar redesigned: line 1 shows view tabs + navigation hints + stats,
  line 2 shows the NC-style F-key bar (or popup hints when a popup is open)
- Context hints simplified (F-key actions removed since they're in the bar)

## [0.1.0] - 2026-02-18

### Added
- Initial release — Norton Commander-style TUI dashboard
- Dual-pane layout: tree view (left) + detail pane (right)
- Four views: Tasks, Issues (beads), Config cascade, Cost summary
- Task tree with repo grouping, expand/collapse, phase indicators
- Detail pane modes: Overview, Document list, Document reader, History
- Markdown rendering with basic syntax highlighting in document reader
- Beads issue tracker integration (`.beads/issues.jsonl`)
- Config cascade display (global/project/task YAML)
- `F2` Launch popup: terminal detection + AI host selection
- `F3` Full-text search across tasks, state.json, and artifact files
- `n` New worktree wizard: description input, host selection, settings toggles,
  background git operations, color-themed terminal launch
- 8 color schemes (from Python `CREW_COLOR_SCHEMES`), assigned per task
- Auto-refresh on configurable poll interval
- `~/.config/crew-board.toml` for persistent scan paths and settings
- CI/CD pipeline: 6-target build matrix (Linux/Windows/macOS, amd64/arm64),
  clippy + test gates, GitHub Release with platform binaries
