use crate::app::{App, FocusPane, TreeRow};
use crate::ui::styles;
use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, ListState, Scrollbar, ScrollbarOrientation, ScrollbarState},
    Frame,
};

pub fn draw(frame: &mut Frame, app: &App, area: Rect) {
    let is_focused = app.focus_pane == FocusPane::Left;
    let border_style = if is_focused {
        styles::focused_border_style()
    } else {
        styles::unfocused_border_style()
    };

    let items: Vec<ListItem> = app
        .tree_rows
        .iter()
        .map(|row| match row {
            TreeRow::Repo(ri) => render_repo_row(app, *ri),
            TreeRow::Task(ri, ti) => render_task_row(app, *ri, *ti),
        })
        .collect();

    let items_len = items.len();
    let total_tasks: usize = app.repos.iter().map(|r| r.tasks.len()).sum();
    let focus_marker = if is_focused { " ◄" } else { "" };
    let title = format!(" {} repos, {} tasks{} ", app.repos.len(), total_tasks, focus_marker);
    let list = List::new(items)
        .block(
            Block::default()
                .title(title)
                .borders(Borders::ALL)
                .border_style(border_style),
        )
        .highlight_style(styles::selected_style())
        .highlight_symbol("▌ ");

    let mut state = ListState::default();
    state.select(Some(app.tree_cursor));
    frame.render_stateful_widget(list, area, &mut state);

    // Vertical scrollbar (only when content overflows)
    let visible_height = area.height.saturating_sub(2) as usize; // subtract borders
    if items_len > visible_height {
        let mut scrollbar_state = ScrollbarState::new(items_len)
            .position(app.tree_cursor)
            .viewport_content_length(visible_height);
        let scrollbar = Scrollbar::new(ScrollbarOrientation::VerticalRight)
            .begin_symbol(None)
            .end_symbol(None)
            .track_symbol(Some("│"))
            .thumb_symbol("█");
        frame.render_stateful_widget(scrollbar, area, &mut scrollbar_state);
    }
}

fn render_repo_row<'a>(app: &App, ri: usize) -> ListItem<'a> {
    let repo = &app.repos[ri];
    let expanded = app.expanded_repos.contains(&ri);
    let arrow = if expanded { "▼" } else { "▶" };
    let active = repo.active_task_count();
    let archived = repo.archived_task_count();
    let total = repo.tasks.len();

    let mut spans = vec![
        Span::styled(
            format!("{} ", arrow),
            Style::default().fg(Color::Yellow),
        ),
        Span::styled(
            repo.name.clone(),
            Style::default()
                .fg(Color::White)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            format!("  ({}/{} active", active, total - archived),
            Style::default().fg(Color::DarkGray),
        ),
    ];
    if archived > 0 {
        spans.push(Span::styled(
            format!(", {} deleted", archived),
            Style::default().fg(Color::DarkGray),
        ));
    }
    spans.push(Span::styled(")", Style::default().fg(Color::DarkGray)));

    let line = Line::from(spans);
    ListItem::new(line)
}

fn render_task_row<'a>(app: &App, ri: usize, ti: usize) -> ListItem<'a> {
    let loaded = &app.repos[ri].tasks[ti];
    let task = &loaded.state;

    // Archived (deleted) tasks get a distinct dimmed appearance
    if loaded.archived {
        let mut spans = vec![
            Span::raw("  "),
            Span::styled("✗ ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                task.task_id.clone(),
                Style::default()
                    .fg(Color::DarkGray)
                    .add_modifier(Modifier::DIM),
            ),
            Span::raw(" "),
            Span::styled("[deleted]", Style::default().fg(Color::DarkGray)),
        ];
        if let Some(ref jira) = loaded.jira_key {
            spans.push(Span::raw(" "));
            spans.push(Span::styled(
                jira.clone(),
                Style::default().fg(Color::Yellow),
            ));
        }
        let line = Line::from(spans);
        return ListItem::new(line);
    }

    let phase_label = task.status_label();

    let progress = if task.implementation_progress.total_steps > 0 {
        format!(
            " {}/{}",
            task.implementation_progress.current_step,
            task.implementation_progress.total_steps
        )
    } else {
        String::new()
    };

    let accent_color = task
        .worktree
        .as_ref()
        .map(|wt| styles::get_scheme(wt.color_scheme_index).tab)
        .unwrap_or(Color::DarkGray);

    let status_symbol = if task.is_complete() {
        "✓"
    } else if task.phase.is_some() {
        "▸"
    } else {
        "○"
    };

    let line = Line::from(vec![
        Span::raw("  "), // indent under repo
        Span::styled(
            format!("{} ", status_symbol),
            Style::default().fg(accent_color),
        ),
        Span::styled(
            task.task_id.clone(),
            Style::default().add_modifier(Modifier::BOLD),
        ),
        Span::raw(" "),
        Span::styled(
            format!("[{}]", phase_label),
            styles::phase_style(phase_label, true, task.is_complete()),
        ),
        Span::styled(progress, Style::default().fg(Color::DarkGray)),
    ]);

    ListItem::new(line)
}
