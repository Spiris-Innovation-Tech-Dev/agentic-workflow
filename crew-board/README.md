# crew-board

Norton Commander-style TUI dashboard for monitoring [agentic-workflow](https://github.com/Spiris-Innovation-Tech-Dev/agentic-workflow) tasks across multiple repositories.

```
┌─ Tasks ──────────────────────┐┌─ Details ─────────────────────────────────┐
│ ▼ agentic-workflow (3 tasks) ││ TASK_003                                  │
│   TASK_001  pending          ││ Crew Board — Cross-Project Dashboard      │
│   TASK_002  architect        ││                                           │
│ ▸ TASK_003  done        ◄────││ Mode: fast ($0.05-0.15)                   │
│ ▶ other-project (1 task)     ││ Iteration: 1                              │
│                              ││                                           │
│                              ││ ── Phases ──                              │
│                              ││   ✓ architect                             │
│                              ││   ✓ developer                             │
│                              ││   ✓ reviewer                              │
│                              ││   ✓ skeptic                               │
│                              ││   ✓ implementer                           │
│                              ││   ✓ technical_writer                      │
│                              ││                                           │
│                              ││ ── Documents ──                           │
│                              ││   3 docs: Architect, Developer, Reviewer  │
│                              ││   Press 'd' to browse documents           │
└──────────────────────────────┘└───────────────────────────────────────────┘
 [1:Tasks] 2:Issues 3:Config 4:Cost  │  ↑↓ nav  d docs  h history  F2 launch
 2 repos │ 4 tasks (1 active) │ 12 issues (3 open)              (5s ago)
```

## Install

```bash
cd crew-board
cargo build --release
cp target/release/crew-board ~/.local/bin/   # or anywhere on PATH
```

Requires Rust 1.70+.

## Usage

```bash
# Scan a parent directory for repos with .tasks/ or .beads/
crew-board --scan /path/to/projects

# Monitor specific repos
crew-board --repo /path/to/repo1 --repo /path/to/repo2

# Both (CLI args override config file)
crew-board --scan /path/to/projects --repo /extra/repo
```

On first run with `--scan`, the path is saved to `~/.config/crew-board.toml` so you can just run `crew-board` next time.

## Configuration

`~/.config/crew-board.toml`:

```toml
# Directories to scan for repos containing .tasks/ or .beads/
scan = ["/path/to/projects", "/another/dir"]

# Explicit repo paths (always included)
repos = ["/path/to/specific/repo"]

# Auto-refresh interval in seconds (default: 3)
poll_interval = 5
```

CLI flags override config values when both are present.

## Views

Switch views with number keys or backtick to cycle:

| Key | View | Shows |
|-----|------|-------|
| `1` | Tasks | Tree of repos and tasks with detail pane |
| `2` | Issues | Beads issue tracker (`.beads/issues.jsonl`) |
| `3` | Config | Configuration cascade (global/project/task) |
| `4` | Cost | Cost estimates and actuals from workflow state |

## Key Bindings

### Navigation
| Key | Action |
|-----|--------|
| `↑`/`k` | Move up |
| `↓`/`j` | Move down |
| `Enter`/`Space` | Expand/collapse repo |
| `Tab` | Switch focus between left and right pane |
| `PgUp`/`PgDn` | Scroll detail pane |

### Task Detail
| Key | Action |
|-----|--------|
| `d` | Browse task documents (architect.md, developer.md, etc.) |
| `h` | View task history (decisions, phases, concerns) |
| `Esc` | Back (reader -> list -> overview) |

### Documents
When in document list (`d`):
| Key | Action |
|-----|--------|
| `↑`/`↓` | Select document (shows preview) |
| `Enter` | Open full document with syntax highlighting |
| `Esc` | Back to overview |

### Actions
| Key | Action |
|-----|--------|
| `F2` | Launch terminal with AI host for selected task |
| `F5` | Force refresh |
| `q`/`Esc` | Quit |

### F2 Launch
Opens a two-step popup:
1. Select terminal environment (auto-detected: WSL tab, tmux, macOS, Linux)
2. Select AI host (Claude Code, GitHub Copilot, Gemini CLI)

Launches in the task's worktree directory if one exists, otherwise the repo root.

## What It Monitors

### Task State (`.tasks/*/state.json`)
- Current phase and completed phases
- Workflow mode (full/fast/turbo/minimal)
- Implementation progress with step tracking
- Worktree info (branch, color scheme, status)
- Review issues, concerns, human decisions
- Cost estimates

### Task Documents (`.tasks/*/*.md`)
- Architect analysis, developer plan, reviewer feedback
- Skeptic concerns, implementation plan
- Browsable with preview and full reading mode

### Beads Issues (`.beads/issues.jsonl`)
- Open/in-progress/closed issue counts
- Priority, labels, descriptions
- Issue detail drilldown

### Configuration
- Global, project, and task-level config cascade
- Shows which config files are active and their key settings

## Architecture

```
crew-board/src/
├── main.rs        — CLI (clap), terminal setup, event loop
├── app.rs         — App state, tree navigation, detail modes, popup state
├── settings.rs    — ~/.config/crew-board.toml loader
├── discovery.rs   — Repo scanning (finds .tasks/ and .beads/ dirs)
├── launcher.rs    — Terminal detection and AI host launch
├── data/          — Data layer (all parsers use serde with #[serde(default)])
│   ├── task.rs    — .tasks/*/state.json + artifact discovery
│   ├── beads.rs   — .beads/issues.jsonl stream parser
│   └── config.rs  — Config cascade loader (YAML)
└── ui/            — ratatui rendering
    ├── task_list.rs    — Tree view (left pane)
    ├── detail_pane.rs  — Overview/docs/history (right pane)
    ├── launch_popup.rs — F2 terminal launch dialog
    └── ...             — Other views and styles
```

## License

MIT
