use crate::app::{App, FocusPane};
use crate::ui::styles;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, List, ListItem, ListState, Paragraph, Wrap},
    Frame,
};

pub fn draw(frame: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(40), Constraint::Percentage(60)])
        .split(area);

    draw_issue_list(frame, app, chunks[0]);
    draw_issue_detail(frame, app, chunks[1]);
}

fn draw_issue_list(frame: &mut Frame, app: &App, area: Rect) {
    let repo = match app.current_repo() {
        Some(r) => r,
        None => return,
    };

    let is_focused = app.focus_pane == FocusPane::Left;
    let border_style = if is_focused {
        Style::default().fg(Color::Cyan)
    } else {
        Style::default().fg(Color::DarkGray)
    };

    let items: Vec<ListItem> = repo
        .issues
        .iter()
        .map(|issue| {
            let priority_color = match issue.priority {
                0 => Color::Red,
                1 => Color::LightRed,
                2 => Color::Yellow,
                3 => Color::Blue,
                _ => Color::DarkGray,
            };

            let line = Line::from(vec![
                Span::styled(
                    format!("{} ", issue.status_symbol()),
                    Style::default().fg(match issue.status.as_str() {
                        "open" => Color::Yellow,
                        "in_progress" => Color::Green,
                        "done" | "closed" => Color::DarkGray,
                        _ => Color::White,
                    }),
                ),
                Span::styled(
                    issue.id.as_str(),
                    Style::default().add_modifier(Modifier::BOLD),
                ),
                Span::raw(" "),
                Span::styled(
                    format!("[P{}]", issue.priority),
                    Style::default().fg(priority_color),
                ),
                Span::raw(" "),
                Span::raw(issue.title.as_str()),
            ]);

            ListItem::new(line)
        })
        .collect();

    let title = format!(" Issues ({}) ", repo.issues.len());
    let list = List::new(items)
        .block(
            Block::default()
                .title(title)
                .borders(Borders::ALL)
                .border_style(border_style),
        )
        .highlight_style(styles::selected_style())
        .highlight_symbol(">> ");

    let mut state = ListState::default();
    state.select(Some(app.selected_issue));
    frame.render_stateful_widget(list, area, &mut state);
}

fn draw_issue_detail(frame: &mut Frame, app: &App, area: Rect) {
    let is_focused = app.focus_pane == FocusPane::Right;
    let border_style = if is_focused {
        Style::default().fg(Color::Cyan)
    } else {
        Style::default().fg(Color::DarkGray)
    };

    let issue = match app.current_issue() {
        Some(i) => i,
        None => {
            let block = Block::default()
                .title(" Issue Details ")
                .borders(Borders::ALL)
                .border_style(border_style);
            frame.render_widget(
                Paragraph::new("No issue selected").block(block),
                area,
            );
            return;
        }
    };

    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::from(vec![
        Span::styled(
            issue.id.as_str(),
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw(format!(" [{}]", issue.issue_type)),
    ]));
    lines.push(Line::from(Span::styled(
        issue.title.as_str(),
        Style::default().add_modifier(Modifier::BOLD),
    )));
    lines.push(Line::from(""));

    lines.push(Line::from(vec![
        Span::styled("Status:   ", styles::dim_style()),
        Span::raw(issue.status.as_str()),
    ]));
    lines.push(Line::from(vec![
        Span::styled("Priority: ", styles::dim_style()),
        Span::raw(issue.priority_label()),
    ]));
    lines.push(Line::from(vec![
        Span::styled("Type:     ", styles::dim_style()),
        Span::raw(issue.issue_type.as_str()),
    ]));
    lines.push(Line::from(vec![
        Span::styled("Author:   ", styles::dim_style()),
        Span::raw(issue.created_by.as_str()),
    ]));
    lines.push(Line::from(""));

    if !issue.description.is_empty() {
        lines.push(Line::from(Span::styled(
            "── Description ──",
            styles::header_style(),
        )));
        for desc_line in issue.description.lines() {
            lines.push(Line::from(desc_line.to_string()));
        }
        lines.push(Line::from(""));
    }

    if !issue.blocked_by.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("Blocked by: ", Style::default().fg(Color::Red)),
            Span::raw(issue.blocked_by.join(", ")),
        ]));
    }

    if !issue.blocks.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("Blocks: ", Style::default().fg(Color::Yellow)),
            Span::raw(issue.blocks.join(", ")),
        ]));
    }

    lines.push(Line::from(""));
    lines.push(Line::from(vec![
        Span::styled("Created: ", styles::dim_style()),
        Span::raw(issue.created_at.as_str()),
    ]));

    let text = Text::from(lines);
    let block = Block::default()
        .title(" Issue Details ")
        .borders(Borders::ALL)
        .border_style(border_style);
    let paragraph = Paragraph::new(text)
        .block(block)
        .wrap(Wrap { trim: false })
        .scroll((app.detail_scroll, 0));

    frame.render_widget(paragraph, area);
}
