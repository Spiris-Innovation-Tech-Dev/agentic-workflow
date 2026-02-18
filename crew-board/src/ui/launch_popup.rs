use crate::app::{App, LaunchStep};
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, List, ListItem, Paragraph},
    Frame,
};

pub fn draw(frame: &mut Frame, app: &App) {
    let popup = match &app.launch_popup {
        Some(p) => p,
        None => return,
    };

    let area = centered_rect(50, 60, frame.area());

    // Clear the background
    frame.render_widget(Clear, area);

    let title = format!(" Launch: {} ", popup.task_id);
    let block = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    match popup.step {
        LaunchStep::SelectTerminal => {
            draw_selection(
                frame,
                inner,
                "Select Terminal:",
                &popup
                    .terminals
                    .iter()
                    .map(|t| t.label())
                    .collect::<Vec<_>>(),
                popup.terminal_cursor,
            );
        }
        LaunchStep::SelectHost => {
            draw_selection(
                frame,
                inner,
                "Select AI Host:",
                &popup.hosts.iter().map(|h| h.label()).collect::<Vec<_>>(),
                popup.host_cursor,
            );
        }
        LaunchStep::Done => {
            let msg = popup.result_msg.as_deref().unwrap_or("Done");
            let lines = vec![
                Line::from(""),
                Line::from(Span::styled(msg, Style::default().fg(Color::Green))),
                Line::from(""),
                Line::from(Span::styled(
                    "Press Enter or Esc to close",
                    Style::default().fg(Color::DarkGray),
                )),
            ];
            let para = Paragraph::new(lines);
            frame.render_widget(para, inner);
        }
    }
}

fn draw_selection(frame: &mut Frame, area: Rect, header: &str, items: &[&str], cursor: usize) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(2), Constraint::Min(3), Constraint::Length(1)])
        .split(area);

    // Header
    let header_line = Paragraph::new(Line::from(Span::styled(
        header,
        Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD),
    )));
    frame.render_widget(header_line, chunks[0]);

    // Items
    let list_items: Vec<ListItem> = items
        .iter()
        .enumerate()
        .map(|(i, label)| {
            let prefix = if i == cursor { "▸ " } else { "  " };
            let style = if i == cursor {
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(Color::White)
            };
            ListItem::new(Line::from(Span::styled(
                format!("{}{}", prefix, label),
                style,
            )))
        })
        .collect();

    let list = List::new(list_items);
    frame.render_widget(list, chunks[1]);

    // Hint
    let hint = Paragraph::new(Line::from(Span::styled(
        "↑↓ select  Enter confirm  Esc cancel",
        Style::default().fg(Color::DarkGray),
    )));
    frame.render_widget(hint, chunks[2]);
}

/// Create a centered rectangle.
fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(area);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}
