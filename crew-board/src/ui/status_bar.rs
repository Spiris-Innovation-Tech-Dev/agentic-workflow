use crate::app::{ActiveView, App};
use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};

pub fn draw(frame: &mut Frame, app: &App, area: Rect) {
    let elapsed = app.last_refresh.elapsed().as_secs();

    // Top line: view tabs + keybinding hints
    let view_tabs = Line::from(vec![
        tab_span("1:Tasks", app.active_view == ActiveView::Tasks),
        Span::raw(" "),
        tab_span("2:Issues", app.active_view == ActiveView::BeadsIssues),
        Span::raw(" "),
        tab_span("3:Config", app.active_view == ActiveView::Config),
        Span::raw(" "),
        tab_span("4:Cost", app.active_view == ActiveView::CostSummary),
        Span::raw("  │  "),
        Span::styled(
            format!(
                "↑↓ nav  Enter expand  d docs  h history  F2 launch  q quit  ({}s ago)",
                elapsed
            ),
            Style::default().fg(Color::DarkGray),
        ),
    ]);

    // Bottom line: aggregate stats
    let total_tasks: usize = app.repos.iter().map(|r| r.tasks.len()).sum();
    let active_tasks: usize = app.repos.iter().map(|r| r.active_task_count()).sum();
    let total_issues: usize = app.repos.iter().map(|r| r.issues.len()).sum();
    let open_issues: usize = app.repos.iter().map(|r| r.open_issue_count()).sum();

    let stats = Line::from(vec![Span::styled(
        format!(
            " {} repos │ {} tasks ({} active) │ {} issues ({} open)",
            app.repos.len(),
            total_tasks,
            active_tasks,
            total_issues,
            open_issues,
        ),
        Style::default().fg(Color::DarkGray),
    )]);

    let paragraph = Paragraph::new(vec![view_tabs, stats]);
    frame.render_widget(paragraph, area);
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
