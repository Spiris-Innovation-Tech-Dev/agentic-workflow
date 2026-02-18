use crate::app::{ActiveView, App, CreateStep, DetailMode, FocusPane, LaunchStep};
use crate::ui::styles;
use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};

pub fn draw(frame: &mut Frame, app: &App, area: Rect) {
    let elapsed = app.last_refresh.elapsed().as_secs();
    let hints = context_hints(app);

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
            format!("{}  ({}s ago)", hints, elapsed),
            styles::hint_style(),
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
        styles::hint_style(),
    )]);

    let paragraph = Paragraph::new(vec![view_tabs, stats]);
    frame.render_widget(paragraph, area);
}

fn context_hints(app: &App) -> String {
    // Popups take priority
    if let Some(popup) = &app.search_popup {
        let count = popup.results.len();
        return if count > 0 {
            format!("↑↓ select  Enter go  Esc cancel  ({} results)", count)
        } else {
            "Type to search  Esc cancel".to_string()
        };
    }
    if let Some(popup) = &app.create_popup {
        return match popup.step {
            CreateStep::InputDescription => "Enter next  Esc cancel".to_string(),
            CreateStep::SelectHost => "↑↓ select  Enter confirm  Esc cancel".to_string(),
            CreateStep::ToggleSettings => "↑↓ nav  Space toggle  Enter confirm  Esc cancel".to_string(),
            CreateStep::Confirm => "Enter create  Esc cancel".to_string(),
            CreateStep::Executing => "Creating worktree...".to_string(),
            CreateStep::Done => "Enter confirm  Esc close".to_string(),
        };
    }
    if let Some(popup) = &app.launch_popup {
        return match popup.step {
            LaunchStep::SelectTerminal | LaunchStep::SelectHost => {
                "↑↓ select  Enter confirm  Esc cancel".to_string()
            }
            LaunchStep::Done => "Enter close  Esc close".to_string(),
        };
    }

    // View-specific hints
    match app.active_view {
        ActiveView::Tasks => match app.focus_pane {
            FocusPane::Left => {
                "↑↓ nav  Enter expand  d docs  h history  Tab right  F3 search  F2 launch  n new-wt  q quit".to_string()
            }
            FocusPane::Right => match &app.detail_mode {
                DetailMode::Overview => {
                    "PgUp/PgDn scroll  d docs  h history  Tab left  F2 launch  q quit".to_string()
                }
                DetailMode::DocList { .. } => {
                    "↑↓ select  Enter read  Esc back  Tab switch pane".to_string()
                }
                DetailMode::DocReader { .. } => {
                    "PgUp/PgDn scroll  Esc back  Tab switch pane".to_string()
                }
                DetailMode::History => {
                    "PgUp/PgDn scroll  Esc back  Tab switch pane".to_string()
                }
            },
        },
        ActiveView::BeadsIssues => {
            "↑↓ nav  Tab switch pane  F3 search  q quit".to_string()
        }
        ActiveView::Config => {
            "PgUp/PgDn scroll  q quit".to_string()
        }
        ActiveView::CostSummary => {
            "PgUp/PgDn scroll  q quit".to_string()
        }
    }
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
