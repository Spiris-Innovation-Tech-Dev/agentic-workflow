use crate::app::{ActiveView, App, CleanupStep, CreateStep, DetailMode, FocusPane, LaunchStep};
use crate::ui::styles;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};

pub fn draw(frame: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Length(1)])
        .split(area);

    // Line 1: View tabs + contextual hints + stats
    draw_info_line(frame, app, chunks[0]);

    // Line 2: NC-style F-key bar
    draw_fkey_bar(frame, app, chunks[1]);
}

fn draw_info_line(frame: &mut Frame, app: &App, area: Rect) {
    let elapsed = app.last_refresh.elapsed().as_secs();
    let hints = context_hints(app);

    let total_tasks: usize = app.repos.iter().map(|r| r.tasks.len()).sum();
    let active_tasks: usize = app.repos.iter().map(|r| r.active_task_count()).sum();
    let total_issues: usize = app.repos.iter().map(|r| r.issues.len()).sum();
    let open_issues: usize = app.repos.iter().map(|r| r.open_issue_count()).sum();

    let line = Line::from(vec![
        tab_span("1:Tasks", app.active_view == ActiveView::Tasks),
        Span::raw(" "),
        tab_span("2:Issues", app.active_view == ActiveView::BeadsIssues),
        Span::raw(" "),
        tab_span("3:Config", app.active_view == ActiveView::Config),
        Span::raw(" "),
        tab_span("4:Cost", app.active_view == ActiveView::CostSummary),
        Span::raw("  "),
        Span::styled(hints, styles::hint_style()),
        Span::styled(
            format!(
                "  {} repos {} tasks({} active) {} issues({} open) ({}s)",
                app.repos.len(),
                total_tasks,
                active_tasks,
                total_issues,
                open_issues,
                elapsed,
            ),
            Style::default().fg(Color::DarkGray),
        ),
    ]);

    let paragraph = Paragraph::new(line);
    frame.render_widget(paragraph, area);
}

fn draw_fkey_bar(frame: &mut Frame, app: &App, area: Rect) {
    // When a popup is active, show popup-specific hints in the bar
    if let Some(hints) = popup_hints(app) {
        let line = Line::from(vec![Span::styled(
            hints,
            Style::default().fg(Color::Black).bg(Color::Cyan),
        )]);
        let paragraph = Paragraph::new(line);
        frame.render_widget(paragraph, area);
        return;
    }

    // NC-style F-key bar
    let mut spans: Vec<Span> = Vec::new();

    // Pad the start slightly
    spans.push(Span::raw(" "));

    spans.extend(fkey_spans(1, "Help"));
    spans.extend(fkey_spans(2, "Launch"));
    spans.extend(fkey_spans(3, "Search"));
    spans.extend(fkey_spans(4, "New"));
    spans.extend(fkey_spans(5, "Rfrsh"));
    spans.extend(fkey_spans(6, "Clean"));

    // Fill gap to push F10 to the right
    // Calculate used width: " " + keys + F10 key
    // Each key: "F{n}" (2-3 chars) + label + " " spacer
    let used: usize = 1 // leading space
        + fkey_width(1, "Help")
        + fkey_width(2, "Launch")
        + fkey_width(3, "Search")
        + fkey_width(4, "New")
        + fkey_width(5, "Rfrsh")
        + fkey_width(6, "Clean")
        + fkey_width(10, "Quit");
    let total_width = area.width as usize;
    let gap = total_width.saturating_sub(used);
    if gap > 0 {
        spans.push(Span::styled(
            " ".repeat(gap),
            Style::default().bg(Color::Black),
        ));
    }

    spans.extend(fkey_spans(10, "Quit"));

    let line = Line::from(spans);
    let paragraph = Paragraph::new(line);
    frame.render_widget(paragraph, area);
}

/// Generate styled spans for a single F-key label (NC-style).
/// Number portion: white on dark background. Label: black on cyan.
fn fkey_spans(num: u8, label: &str) -> Vec<Span<'static>> {
    vec![
        Span::styled(
            format!("F{}", num),
            Style::default()
                .fg(Color::White)
                .bg(Color::Black)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            label.to_string(),
            Style::default().fg(Color::Black).bg(Color::Cyan),
        ),
        Span::styled(" ", Style::default().bg(Color::Black)),
    ]
}

/// Calculate the display width of an F-key cell.
fn fkey_width(num: u8, label: &str) -> usize {
    let num_str = format!("F{}", num);
    num_str.len() + label.len() + 1 // +1 for trailing space
}

/// Context hints for the info line (shorter now that F-keys handle actions).
fn context_hints(app: &App) -> String {
    // Popups get their own hints in the F-key bar, so just show navigation hints
    if app.search_popup.is_some()
        || app.create_popup.is_some()
        || app.cleanup_popup.is_some()
        || app.launch_popup.is_some()
    {
        return String::new();
    }

    match app.active_view {
        ActiveView::Tasks => match app.focus_pane {
            FocusPane::Left => "↑↓ nav  Enter expand  Tab→pane  d docs  h hist".to_string(),
            FocusPane::Right => match &app.detail_mode {
                DetailMode::Overview => "PgUp/Dn scroll  d docs  h hist  Tab←pane".to_string(),
                DetailMode::DocList { .. } => "↑↓ select  Enter read  Esc back".to_string(),
                DetailMode::DocReader { .. } => "PgUp/Dn scroll  Esc back".to_string(),
                DetailMode::History => "PgUp/Dn scroll  Esc back".to_string(),
            },
        },
        ActiveView::BeadsIssues => "↑↓ nav  Tab pane".to_string(),
        ActiveView::Config => "PgUp/Dn scroll".to_string(),
        ActiveView::CostSummary => "PgUp/Dn scroll".to_string(),
    }
}

/// If a popup is open, return hints to show in the F-key bar area.
fn popup_hints(app: &App) -> Option<String> {
    if let Some(popup) = &app.search_popup {
        let count = popup.results.len();
        return Some(if count > 0 {
            format!(" ↑↓ select  Enter go  Esc cancel  ({} results)", count)
        } else {
            " Type to search  Esc cancel".to_string()
        });
    }
    if let Some(popup) = &app.create_popup {
        return Some(match popup.step {
            CreateStep::InputDescription => " Enter next  Esc cancel".to_string(),
            CreateStep::SelectHost => " ↑↓ select  Enter confirm  Esc cancel".to_string(),
            CreateStep::ToggleSettings => {
                " ↑↓ nav  Space toggle  Enter confirm  Esc cancel".to_string()
            }
            CreateStep::Confirm => " Enter create  Esc cancel".to_string(),
            CreateStep::Executing => " Creating worktree...".to_string(),
            CreateStep::Done => " Enter confirm  Esc close".to_string(),
        });
    }
    if let Some(popup) = &app.cleanup_popup {
        return Some(match popup.step {
            CleanupStep::SelectWorktrees => {
                let n = popup.selected.len();
                format!(
                    " Space toggle  a select-all  Enter next ({} selected)  Esc cancel",
                    n
                )
            }
            CleanupStep::Settings => " Space toggle  Enter preview  Esc cancel".to_string(),
            CleanupStep::Preview => " Enter EXECUTE  j/k scroll  Esc cancel".to_string(),
            CleanupStep::Executing => " Cleaning worktrees...".to_string(),
            CleanupStep::Done => " Enter close  Esc close".to_string(),
        });
    }
    if let Some(popup) = &app.launch_popup {
        return Some(match popup.step {
            LaunchStep::SelectTerminal | LaunchStep::SelectHost => {
                " ↑↓ select  Enter confirm  Esc cancel".to_string()
            }
            LaunchStep::Done => " Enter close  Esc close".to_string(),
        });
    }
    None
}

fn tab_span(label: &str, active: bool) -> Span<'_> {
    if active {
        Span::styled(
            format!("[{}]", label),
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        )
    } else {
        Span::styled(label.to_string(), Style::default().fg(Color::DarkGray))
    }
}
