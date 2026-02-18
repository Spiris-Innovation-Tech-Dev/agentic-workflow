use crate::app::{App, CreateStep};
use crate::ui::styles;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, List, ListItem, Paragraph},
    Frame,
};

const SPINNER: &[char] = &['◐', '◓', '◑', '◒'];

pub fn draw(frame: &mut Frame, app: &App) {
    let popup = match &app.create_popup {
        Some(p) => p,
        None => return,
    };

    let area = centered_rect(55, 50, frame.area());
    frame.render_widget(Clear, area);

    let title = format!(" New Worktree: {} ", popup.repo_name);
    let block = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    match popup.step {
        CreateStep::InputDescription => draw_input(frame, inner, popup),
        CreateStep::SelectHost => draw_host_selection(frame, inner, popup),
        CreateStep::ToggleSettings => draw_settings(frame, inner, popup),
        CreateStep::Confirm => draw_confirm(frame, inner, popup),
        CreateStep::Executing => draw_executing(frame, inner, popup),
        CreateStep::Done => draw_done(frame, inner, popup),
    }
}

fn draw_input(
    frame: &mut Frame,
    area: Rect,
    popup: &crate::app::CreateWorktreePopup,
) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(2),
            Constraint::Length(3),
            Constraint::Min(0),
            Constraint::Length(1),
        ])
        .split(area);

    // Header
    let header = Paragraph::new(Line::from(Span::styled(
        "Task description:",
        Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD),
    )));
    frame.render_widget(header, chunks[0]);

    // Input field with border
    let input_block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::DarkGray));
    let input_inner = input_block.inner(chunks[1]);
    frame.render_widget(input_block, chunks[1]);

    let input_text = popup.description_input.value();
    let cursor_pos = popup.description_input.visual_cursor();

    let input_para = Paragraph::new(Line::from(Span::raw(input_text)));
    frame.render_widget(input_para, input_inner);

    // Position cursor
    frame.set_cursor_position((
        input_inner.x + cursor_pos as u16,
        input_inner.y,
    ));

    // Hint
    let hint = Paragraph::new(Line::from(Span::styled(
        "Enter confirm  Esc cancel",
        Style::default().fg(Color::DarkGray),
    )));
    frame.render_widget(hint, chunks[3]);
}

fn draw_host_selection(
    frame: &mut Frame,
    area: Rect,
    popup: &crate::app::CreateWorktreePopup,
) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(2),
            Constraint::Min(3),
            Constraint::Length(1),
        ])
        .split(area);

    let header = Paragraph::new(Line::from(Span::styled(
        "Select AI Host:",
        Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD),
    )));
    frame.render_widget(header, chunks[0]);

    let items: Vec<ListItem> = popup
        .hosts
        .iter()
        .enumerate()
        .map(|(i, host)| {
            let prefix = if i == popup.host_cursor { "▸ " } else { "  " };
            let style = if i == popup.host_cursor {
                styles::popup_selected_style()
            } else {
                Style::default().fg(Color::White)
            };
            ListItem::new(Line::from(Span::styled(
                format!("{}{}", prefix, host.label()),
                style,
            )))
        })
        .collect();

    frame.render_widget(List::new(items), chunks[1]);

    let hint = Paragraph::new(Line::from(Span::styled(
        "↑↓ select  Enter confirm  Esc cancel",
        Style::default().fg(Color::DarkGray),
    )));
    frame.render_widget(hint, chunks[2]);
}

fn draw_settings(
    frame: &mut Frame,
    area: Rect,
    popup: &crate::app::CreateWorktreePopup,
) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(2),
            Constraint::Min(3),
            Constraint::Length(1),
        ])
        .split(area);

    let header = Paragraph::new(Line::from(Span::styled(
        "Settings:",
        Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD),
    )));
    frame.render_widget(header, chunks[0]);

    let settings = [
        (popup.pull, "Pull latest before creating"),
        (popup.launch_after, "Launch terminal after creation"),
    ];

    let items: Vec<ListItem> = settings
        .iter()
        .enumerate()
        .map(|(i, (enabled, label))| {
            let check = if *enabled { "[x]" } else { "[ ]" };
            let style = if i == popup.settings_cursor {
                styles::popup_selected_style()
            } else {
                Style::default().fg(Color::White)
            };
            ListItem::new(Line::from(Span::styled(
                format!("{} {}", check, label),
                style,
            )))
        })
        .collect();

    frame.render_widget(List::new(items), chunks[1]);

    let hint = Paragraph::new(Line::from(Span::styled(
        "Space toggle  Enter confirm  Esc cancel",
        Style::default().fg(Color::DarkGray),
    )));
    frame.render_widget(hint, chunks[2]);
}

fn draw_confirm(
    frame: &mut Frame,
    area: Rect,
    popup: &crate::app::CreateWorktreePopup,
) {
    let preview = match &popup.preview {
        Some(p) => p,
        None => return,
    };

    let host_label = popup.hosts[popup.host_cursor].label();
    let pull_str = if popup.pull { "Yes" } else { "No" };
    let launch_str = if popup.launch_after { "Yes" } else { "No" };

    let label_style = Style::default().fg(Color::DarkGray);
    let value_style = Style::default().fg(Color::White);
    let highlight_style = Style::default()
        .fg(Color::Cyan)
        .add_modifier(Modifier::BOLD);

    let lines = vec![
        Line::from(Span::styled(
            "Confirm worktree creation:",
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
        Line::from(vec![
            Span::styled("  Task:       ", label_style),
            Span::styled(&preview.task_id, highlight_style),
        ]),
        Line::from(vec![
            Span::styled("  Branch:     ", label_style),
            Span::styled(&preview.branch_name, value_style),
        ]),
        Line::from(vec![
            Span::styled("  Base:       ", label_style),
            Span::styled(&preview.base_branch, value_style),
        ]),
        Line::from(vec![
            Span::styled("  Directory:  ", label_style),
            Span::styled(&preview.worktree_dir, value_style),
        ]),
        Line::from(vec![
            Span::styled("  Color:      ", label_style),
            Span::styled(preview.color_scheme_name, value_style),
        ]),
        Line::from(vec![
            Span::styled("  AI Host:    ", label_style),
            Span::styled(host_label, value_style),
        ]),
        Line::from(vec![
            Span::styled("  Pull first: ", label_style),
            Span::styled(pull_str, value_style),
        ]),
        Line::from(vec![
            Span::styled("  Launch:     ", label_style),
            Span::styled(launch_str, value_style),
        ]),
        Line::from(""),
        Line::from(Span::styled(
            "Enter create  Esc cancel",
            Style::default().fg(Color::DarkGray),
        )),
    ];

    let para = Paragraph::new(lines);
    frame.render_widget(para, area);
}

fn draw_executing(
    frame: &mut Frame,
    area: Rect,
    popup: &crate::app::CreateWorktreePopup,
) {
    let elapsed = popup
        .started_at
        .map(|t| t.elapsed().as_secs_f32())
        .unwrap_or(0.0);

    let spinner_idx = (elapsed * 4.0) as usize % SPINNER.len();
    let spinner_char = SPINNER[spinner_idx];

    let lines = vec![
        Line::from(""),
        Line::from(Span::styled(
            format!("{} Creating worktree... ({:.1}s)", spinner_char, elapsed),
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        )),
    ];

    let para = Paragraph::new(lines);
    frame.render_widget(para, area);
}

fn draw_done(
    frame: &mut Frame,
    area: Rect,
    popup: &crate::app::CreateWorktreePopup,
) {
    match &popup.result {
        Some(Ok(result)) => {
            let scheme_name = crate::launcher::get_hex_scheme(result.color_scheme_index).name;
            let dir_str = result.worktree_abs.to_string_lossy();
            let mut lines = vec![
                Line::from(""),
                Line::from(Span::styled(
                    "✓ Worktree created!",
                    Style::default()
                        .fg(Color::Green)
                        .add_modifier(Modifier::BOLD),
                )),
                Line::from(""),
                Line::from(vec![
                    Span::styled("Task:      ", Style::default().fg(Color::DarkGray)),
                    Span::styled(
                        &result.task_id,
                        Style::default()
                            .fg(Color::Cyan)
                            .add_modifier(Modifier::BOLD),
                    ),
                ]),
                Line::from(vec![
                    Span::styled("Branch:    ", Style::default().fg(Color::DarkGray)),
                    Span::raw(&result.branch_name),
                ]),
                Line::from(vec![
                    Span::styled("Directory: ", Style::default().fg(Color::DarkGray)),
                    Span::raw(dir_str.as_ref()),
                ]),
                Line::from(vec![
                    Span::styled("Color:     ", Style::default().fg(Color::DarkGray)),
                    Span::raw(scheme_name),
                ]),
                Line::from(""),
            ];

            let hint = if popup.launch_after {
                "Enter launch terminal  Esc close"
            } else {
                "Enter close  Esc close"
            };
            lines.push(Line::from(Span::styled(
                hint,
                Style::default().fg(Color::DarkGray),
            )));

            let para = Paragraph::new(lines);
            frame.render_widget(para, area);
        }
        Some(Err(err)) => {
            let lines = vec![
                Line::from(""),
                Line::from(Span::styled(
                    "✗ Error",
                    Style::default()
                        .fg(Color::Red)
                        .add_modifier(Modifier::BOLD),
                )),
                Line::from(""),
                Line::from(Span::styled(
                    err.as_str(),
                    Style::default().fg(Color::Red),
                )),
                Line::from(""),
                Line::from(Span::styled(
                    "Press Esc to close",
                    Style::default().fg(Color::DarkGray),
                )),
            ];
            let para = Paragraph::new(lines);
            frame.render_widget(para, area);
        }
        None => {}
    }
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
