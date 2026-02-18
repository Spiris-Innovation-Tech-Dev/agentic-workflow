mod app;
mod data;
mod discovery;
mod launcher;
mod settings;
mod ui;

use anyhow::Result;
use app::{ActiveView, App, DetailMode, FocusPane};
use clap::Parser;
use crossterm::{
    event::{self, Event, KeyCode, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};
use std::io;
use std::time::Duration;

#[derive(Parser, Debug)]
#[command(
    name = "crew-board",
    about = "Cross-project task dashboard for agentic-workflow"
)]
struct Cli {
    /// Repository paths to monitor (repeatable)
    #[arg(short, long = "repo")]
    repos: Vec<String>,

    /// Parent directory to scan for repos containing .tasks/ (repeatable)
    #[arg(short, long = "scan")]
    scans: Vec<String>,

    /// Poll interval in seconds
    #[arg(short, long)]
    poll_interval: Option<u64>,
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    let cfg = settings::Settings::load();

    // Merge: CLI args override config. If CLI has values, use them; otherwise fall back to config.
    let repos = if cli.repos.is_empty() {
        cfg.repos
    } else {
        cli.repos
    };

    let scans = if cli.scans.is_empty() {
        cfg.scan
    } else {
        cli.scans
    };

    let poll_interval = cli.poll_interval.or(cfg.poll_interval).unwrap_or(3);

    let repo_paths = discovery::discover_repos(&repos, &scans);
    if repo_paths.is_empty() {
        eprintln!("No repos found.");
        if let Some(path) = settings::config_path() {
            eprintln!(
                "Create {} with:\n\n  scan = [\"/path/to/your/projects\"]\n",
                path.display()
            );
        }
        eprintln!("Or use: crew-board --repo <path> or --scan <dir>");
        std::process::exit(1);
    }

    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // Create app
    let mut app = App::new(repo_paths, poll_interval);

    // Main loop
    let result = run_app(&mut terminal, &mut app);

    // Restore terminal
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    result
}

fn run_app(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    app: &mut App,
) -> Result<()> {
    loop {
        terminal.draw(|frame| ui::draw(frame, app))?;

        // Poll for events with short timeout for responsive UI
        let timeout = Duration::from_millis(250);
        if event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                // If launch popup is open, route keys there
                if app.launch_popup.is_some() {
                    match key.code {
                        KeyCode::Esc => app.close_launch_popup(),
                        KeyCode::Up | KeyCode::Char('k') => app.popup_up(),
                        KeyCode::Down | KeyCode::Char('j') => app.popup_down(),
                        KeyCode::Enter => app.popup_confirm(),
                        _ => {}
                    }
                } else if app.focus_pane == FocusPane::Right
                    && app.detail_mode != DetailMode::Overview
                {
                    // Right pane has focus and we're in a doc/history mode
                    match key.code {
                        KeyCode::Esc | KeyCode::Backspace => app.detail_back(),
                        KeyCode::Up | KeyCode::Char('k') => {
                            if matches!(app.detail_mode, DetailMode::DocList { .. }) {
                                app.detail_nav_up();
                            } else {
                                app.scroll_detail_up();
                            }
                        }
                        KeyCode::Down | KeyCode::Char('j') => {
                            if matches!(app.detail_mode, DetailMode::DocList { .. }) {
                                app.detail_nav_down();
                            } else {
                                app.scroll_detail_down();
                            }
                        }
                        KeyCode::Enter => app.detail_open_doc(),
                        KeyCode::PageDown => app.scroll_detail_down(),
                        KeyCode::PageUp => app.scroll_detail_up(),
                        KeyCode::Tab => app.toggle_focus(),
                        KeyCode::Char('q') => app.should_quit = true,
                        _ => {}
                    }
                } else {
                    match (key.modifiers, key.code) {
                        // Quit
                        (_, KeyCode::Char('q')) | (_, KeyCode::Esc) => app.should_quit = true,
                        (KeyModifiers::CONTROL, KeyCode::Char('c')) => app.should_quit = true,

                        // Launch terminal
                        (_, KeyCode::F(2)) => app.open_launch_popup(),

                        // Refresh
                        (_, KeyCode::F(5)) => app.refresh(),

                        // Documents & History (right pane shortcuts)
                        (_, KeyCode::Char('d')) => app.enter_doc_list(),
                        (_, KeyCode::Char('h')) => app.enter_history(),

                        // Tree: expand/collapse repo
                        (_, KeyCode::Enter) => app.tree_toggle(),
                        (_, KeyCode::Char(' ')) => app.tree_toggle(),

                        // Item navigation
                        (_, KeyCode::Up) | (_, KeyCode::Char('k')) => app.prev_item(),
                        (_, KeyCode::Down) | (_, KeyCode::Char('j')) => app.next_item(),

                        // Pane focus
                        (_, KeyCode::Tab) => app.toggle_focus(),

                        // View switching (number keys)
                        (_, KeyCode::Char('1')) => app.set_view(ActiveView::Tasks),
                        (_, KeyCode::Char('2')) => app.set_view(ActiveView::BeadsIssues),
                        (_, KeyCode::Char('3')) => app.set_view(ActiveView::Config),
                        (_, KeyCode::Char('4')) => app.set_view(ActiveView::CostSummary),

                        // Cycle views
                        (_, KeyCode::Char('`')) => app.next_view(),

                        // Detail scroll
                        (_, KeyCode::PageDown) => app.scroll_detail_down(),
                        (_, KeyCode::PageUp) => app.scroll_detail_up(),

                        _ => {}
                    }
                }
            }
        }

        if app.should_quit {
            return Ok(());
        }

        // Auto-refresh on poll interval
        if app.last_refresh.elapsed() >= Duration::from_secs(app.poll_interval_secs) {
            app.refresh();
        }
    }
}
