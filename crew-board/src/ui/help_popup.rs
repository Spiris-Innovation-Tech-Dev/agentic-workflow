use crate::app::App;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Paragraph, Wrap},
    Frame,
};

pub fn draw(frame: &mut Frame, _app: &App) {
    let area = centered_rect(60, 75, frame.area());
    frame.render_widget(Clear, area);

    let block = Block::default()
        .title(" Help — crew-board ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let bold = Style::default()
        .fg(Color::Yellow)
        .add_modifier(Modifier::BOLD);
    let key_style = Style::default().fg(Color::Cyan);
    let dim = Style::default().fg(Color::DarkGray);

    let lines = vec![
        Line::from(Span::styled("Function Keys", bold)),
        Line::from(""),
        key_line("F1", "Show this help", key_style),
        key_line("F2", "Launch terminal with AI host", key_style),
        key_line("F3", "Search across tasks & documents", key_style),
        key_line("F4", "Create new worktree (on repo row)", key_style),
        key_line("F5", "Force refresh", key_style),
        key_line("F10", "Quit", key_style),
        Line::from(""),
        Line::from(Span::styled("Navigation", bold)),
        Line::from(""),
        key_line("↑/↓ or j/k", "Move up/down", key_style),
        key_line("Enter/Space", "Expand/collapse repo", key_style),
        key_line("Tab", "Switch pane focus", key_style),
        key_line("PgUp/PgDn", "Scroll detail pane", key_style),
        key_line("1-4", "Switch views (Tasks/Issues/Config/Cost)", key_style),
        key_line("`", "Cycle views", key_style),
        Line::from(""),
        Line::from(Span::styled("Detail Pane", bold)),
        Line::from(""),
        key_line("d", "Browse task documents", key_style),
        key_line("h", "View task history", key_style),
        key_line("Esc", "Back (close popup / exit detail view)", key_style),
        Line::from(""),
        Line::from(Span::styled("Quit", bold)),
        Line::from(""),
        key_line("q", "Quit application", key_style),
        key_line("Ctrl+C", "Quit application", key_style),
        Line::from(""),
        Line::from(Span::styled("Press any key to close", dim)),
    ];

    let paragraph = Paragraph::new(lines).wrap(Wrap { trim: false });
    frame.render_widget(paragraph, inner);
}

fn key_line<'a>(key: &'a str, desc: &'a str, key_style: Style) -> Line<'a> {
    Line::from(vec![
        Span::styled(format!("  {:<14}", key), key_style),
        Span::raw(desc),
    ])
}

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
