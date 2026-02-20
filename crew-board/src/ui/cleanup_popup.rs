use crate::app::{App, CleanupStep};
use crate::ui::styles;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, List, ListItem, Paragraph, Wrap},
    Frame,
};

const SPINNER: &[char] = &['\u{25d0}', '\u{25d3}', '\u{25d1}', '\u{25d2}']; // same as create popup

pub fn draw(frame: &mut Frame, app: &App) {
    let popup = match &app.cleanup_popup {
        Some(p) => p,
        None => return,
    };

    let area = centered_rect(65, 70, frame.area());
    frame.render_widget(Clear, area);

    let title = format!(" Cleanup Worktrees: {} ", popup.repo_name);
    let block = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    match popup.step {
        CleanupStep::SelectWorktrees => draw_select(frame, inner, popup),
        CleanupStep::Settings => draw_settings(frame, inner, popup),
        CleanupStep::Preview => draw_preview(frame, inner, popup),
        CleanupStep::Executing => draw_executing(frame, inner, popup),
        CleanupStep::Done => draw_done(frame, inner, popup),
    }
}

fn draw_select(frame: &mut Frame, area: Rect, popup: &crate::app::CleanupPopup) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(2),
            Constraint::Min(5),
            Constraint::Length(1),
        ])
        .split(area);

    let selected_count = popup.selected.len();
    let total = popup.candidates.len();
    let header = if total == 0 {
        Paragraph::new(Line::from(Span::styled(
            "No active worktrees found. Press Esc to close.",
            Style::default().fg(Color::DarkGray),
        )))
    } else {
        Paragraph::new(Line::from(vec![
            Span::styled(
                "Select worktrees to clean up",
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                format!("  ({}/{} selected)", selected_count, total),
                Style::default().fg(Color::DarkGray),
            ),
        ]))
    };
    frame.render_widget(header, chunks[0]);

    if !popup.candidates.is_empty() {
        let items: Vec<ListItem> = popup
            .candidates
            .iter()
            .enumerate()
            .map(|(i, c)| {
                let is_cursor = i == popup.cursor;
                let is_selected = popup.selected.contains(&i);

                let checkbox = if is_selected { "[x]" } else { "[ ]" };
                let prefix = if is_cursor { ">" } else { " " };

                let status_icon = if c.is_complete {
                    "done"
                } else {
                    c.phase.as_deref().unwrap_or("?")
                };

                let size_str = c
                    .disk_size
                    .map(format_size)
                    .unwrap_or_else(|| "?".to_string());

                let warn = if c.has_unmerged { " !" } else { "" };

                let accent = styles::get_scheme(c.color_scheme_index).tab;

                let style = if is_cursor {
                    styles::popup_selected_style()
                } else if is_selected {
                    Style::default().fg(Color::White)
                } else {
                    Style::default().fg(Color::DarkGray)
                };

                let line = Line::from(vec![
                    Span::styled(format!("{} {} ", prefix, checkbox), style),
                    Span::styled("| ", Style::default().fg(accent)),
                    Span::styled(format!("{:<10}", c.task_id), style),
                    Span::styled(
                        format!("[{}]", status_icon),
                        if c.is_complete {
                            Style::default().fg(Color::Green)
                        } else {
                            Style::default().fg(Color::Yellow)
                        },
                    ),
                    Span::styled(format!(" {}", size_str), Style::default().fg(Color::DarkGray)),
                    Span::styled(warn.to_string(), Style::default().fg(Color::Red)),
                ]);
                ListItem::new(line)
            })
            .collect();

        frame.render_widget(List::new(items), chunks[1]);
    }

    let hint_text = if popup.candidates.is_empty() {
        "Esc close"
    } else {
        "Space toggle  a all  Enter next  Esc cancel"
    };
    let hint = Paragraph::new(Line::from(Span::styled(
        hint_text,
        Style::default().fg(Color::DarkGray),
    )));
    frame.render_widget(hint, chunks[2]);
}

fn draw_settings(frame: &mut Frame, area: Rect, popup: &crate::app::CleanupPopup) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(2),
            Constraint::Min(3),
            Constraint::Length(1),
        ])
        .split(area);

    let header = Paragraph::new(Line::from(Span::styled(
        "Cleanup Settings:",
        Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD),
    )));
    frame.render_widget(header, chunks[0]);

    let settings = [
        (popup.remove_branch, "Delete feature branches after cleanup"),
        (
            popup.keep_on_disk,
            "Keep worktree on disk (mark recyclable)",
        ),
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
        "Space toggle  Enter preview  Esc cancel",
        Style::default().fg(Color::DarkGray),
    )));
    frame.render_widget(hint, chunks[2]);
}

fn draw_preview(frame: &mut Frame, area: Rect, popup: &crate::app::CleanupPopup) {
    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::from(Span::styled(
        "Dry-run preview:",
        Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD),
    )));
    lines.push(Line::from(""));

    let mode_str = if popup.keep_on_disk {
        "recyclable"
    } else {
        "remove"
    };
    lines.push(Line::from(vec![
        Span::styled("  Mode: ", Style::default().fg(Color::DarkGray)),
        Span::styled(mode_str, Style::default().fg(Color::White)),
    ]));
    lines.push(Line::from(vec![
        Span::styled("  Tasks: ", Style::default().fg(Color::DarkGray)),
        Span::raw(format!("{}", popup.preview.len())),
    ]));
    lines.push(Line::from(""));

    // Safety note
    lines.push(Line::from(Span::styled(
        "  .tasks/ directory is NEVER deleted",
        Style::default().fg(Color::Green),
    )));
    lines.push(Line::from(""));

    for action in &popup.preview {
        let accent_color = popup
            .candidates
            .iter()
            .find(|c| c.task_id == action.task_id)
            .map(|c| styles::get_scheme(c.color_scheme_index).tab)
            .unwrap_or(Color::White);

        lines.push(Line::from(vec![
            Span::styled("| ", Style::default().fg(accent_color)),
            Span::styled(
                &action.task_id,
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
        ]));

        for cmd in &action.commands {
            lines.push(Line::from(vec![
                Span::raw("    "),
                Span::styled(cmd.as_str(), Style::default().fg(Color::White)),
            ]));
        }

        for warn in &action.warnings {
            lines.push(Line::from(vec![
                Span::raw("    "),
                Span::styled(
                    format!("! {}", warn),
                    Style::default().fg(Color::Red),
                ),
            ]));
        }
        lines.push(Line::from(""));
    }

    let total_warnings: usize = popup.preview.iter().map(|a| a.warnings.len()).sum();
    if total_warnings > 0 {
        lines.push(Line::from(Span::styled(
            format!(
                "  {} warning(s) above -- review before confirming",
                total_warnings
            ),
            Style::default().fg(Color::Red),
        )));
        lines.push(Line::from(""));
    }

    lines.push(Line::from(Span::styled(
        "Enter EXECUTE  Esc cancel  j/k scroll",
        Style::default().fg(Color::DarkGray),
    )));

    let para = Paragraph::new(lines)
        .wrap(Wrap { trim: false })
        .scroll((popup.scroll, 0));
    frame.render_widget(para, area);
}

fn draw_executing(frame: &mut Frame, area: Rect, popup: &crate::app::CleanupPopup) {
    let elapsed = popup
        .started_at
        .map(|t| t.elapsed().as_secs_f32())
        .unwrap_or(0.0);
    let spinner_idx = (elapsed * 4.0) as usize % SPINNER.len();
    let spinner_char = SPINNER[spinner_idx];

    let task_count = popup.selected.len();
    let lines = vec![
        Line::from(""),
        Line::from(Span::styled(
            format!(
                "{} Cleaning up {} worktree{}... ({:.1}s)",
                spinner_char,
                task_count,
                if task_count != 1 { "s" } else { "" },
                elapsed
            ),
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        )),
    ];
    frame.render_widget(Paragraph::new(lines), area);
}

fn draw_done(frame: &mut Frame, area: Rect, popup: &crate::app::CleanupPopup) {
    let results = match &popup.results {
        Some(r) => r,
        None => return,
    };

    let mut lines: Vec<Line> = Vec::new();

    let success_count = results.iter().filter(|r| r.success).count();
    let fail_count = results.len() - success_count;

    if fail_count == 0 {
        lines.push(Line::from(Span::styled(
            format!(
                "Done -- {} worktree{} cleaned",
                success_count,
                if success_count != 1 { "s" } else { "" }
            ),
            Style::default()
                .fg(Color::Green)
                .add_modifier(Modifier::BOLD),
        )));
    } else {
        lines.push(Line::from(Span::styled(
            format!(
                "Completed with {} error{}",
                fail_count,
                if fail_count != 1 { "s" } else { "" }
            ),
            Style::default()
                .fg(Color::Red)
                .add_modifier(Modifier::BOLD),
        )));
    }
    lines.push(Line::from(""));

    for result in results {
        let (symbol, color) = if result.success {
            ("ok", Color::Green)
        } else {
            ("FAIL", Color::Red)
        };
        lines.push(Line::from(vec![
            Span::styled(format!("  [{}] ", symbol), Style::default().fg(color)),
            Span::styled(
                &result.task_id,
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
        ]));
        if !result.message.is_empty() {
            let first_line = result.message.lines().next().unwrap_or("");
            lines.push(Line::from(vec![
                Span::raw("       "),
                Span::styled(first_line, Style::default().fg(Color::DarkGray)),
            ]));
        }
    }

    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "Enter close  Esc close",
        Style::default().fg(Color::DarkGray),
    )));

    let para = Paragraph::new(lines)
        .wrap(Wrap { trim: false })
        .scroll((popup.scroll, 0));
    frame.render_widget(para, area);
}

fn format_size(bytes: u64) -> String {
    if bytes < 1024 {
        format!("{}B", bytes)
    } else if bytes < 1024 * 1024 {
        format!("{:.1}KB", bytes as f64 / 1024.0)
    } else if bytes < 1024 * 1024 * 1024 {
        format!("{:.1}MB", bytes as f64 / (1024.0 * 1024.0))
    } else {
        format!("{:.1}GB", bytes as f64 / (1024.0 * 1024.0 * 1024.0))
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
