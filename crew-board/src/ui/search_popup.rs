use crate::app::App;
use crate::ui::styles;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Paragraph},
    Frame,
};

pub fn draw(frame: &mut Frame, app: &App) {
    let popup = match &app.search_popup {
        Some(p) => p,
        None => return,
    };

    let area = search_rect(frame.area());
    frame.render_widget(Clear, area);

    let block = Block::default()
        .title(" Search ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    // Layout: input line, separator, results, hint
    let result_count = popup.results.len();
    let max_visible = (inner.height as usize).saturating_sub(3); // input + hint + at least 0 results

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), // input line
            Constraint::Min(1),   // results
            Constraint::Length(1), // hint line
        ])
        .split(inner);

    // Input line with / prefix
    let input_text = popup.input.value();
    let cursor_pos = popup.input.visual_cursor();
    let input_line = Paragraph::new(Line::from(vec![
        Span::styled("/ ", Style::default().fg(Color::DarkGray)),
        Span::raw(input_text),
    ]));
    frame.render_widget(input_line, chunks[0]);

    // Position cursor after "/ " prefix
    frame.set_cursor_position((chunks[0].x + 2 + cursor_pos as u16, chunks[0].y));

    // Results area
    let results_area = chunks[1];
    if popup.results.is_empty() {
        let msg = if input_text.is_empty() {
            "Type to search tasks..."
        } else {
            "No results"
        };
        let empty = Paragraph::new(Line::from(Span::styled(
            msg,
            Style::default().fg(Color::DarkGray),
        )));
        frame.render_widget(empty, results_area);
    } else {
        let visible = result_count.min(max_visible);
        // Scroll window so cursor is always visible
        let scroll_offset = if popup.cursor >= visible {
            popup.cursor - visible + 1
        } else {
            0
        };

        let mut lines = Vec::new();
        for i in scroll_offset..(scroll_offset + visible).min(result_count) {
            let r = &popup.results[i];
            let is_selected = i == popup.cursor;

            let cursor_indicator = if is_selected { "▸ " } else { "  " };

            let sel_style = styles::popup_selected_style();
            let id_style = if is_selected {
                sel_style
            } else {
                Style::default().fg(Color::Cyan)
            };

            let desc_style = if is_selected {
                sel_style
            } else {
                Style::default().fg(Color::White)
            };

            // Truncate description to fit
            let max_desc = (results_area.width as usize)
                .saturating_sub(cursor_indicator.len() + r.task_id.len() + r.match_source.len() + 6);
            let desc = if r.description.len() > max_desc {
                format!("{}…", &r.description[..max_desc.saturating_sub(1)])
            } else {
                r.description.clone()
            };

            lines.push(Line::from(vec![
                Span::styled(cursor_indicator, desc_style),
                Span::styled(&r.task_id, id_style),
                Span::raw("  "),
                Span::styled(desc, desc_style),
                Span::raw(" "),
                Span::styled(
                    format!("[{}]", r.match_source),
                    Style::default().fg(Color::DarkGray),
                ),
            ]));
        }

        let results_para = Paragraph::new(lines);
        frame.render_widget(results_para, results_area);
    }

    // Hint line
    let count_text = if result_count > 0 {
        format!("  {} result{}", result_count, if result_count == 1 { "" } else { "s" })
    } else {
        String::new()
    };
    let hint = Paragraph::new(Line::from(vec![
        Span::styled(
            "↑↓ select  Enter go  Esc cancel",
            Style::default().fg(Color::DarkGray),
        ),
        Span::styled(count_text, Style::default().fg(Color::DarkGray)),
    ]));
    frame.render_widget(hint, chunks[2]);
}

/// Top-anchored overlay: 70% width, up to 60% height.
fn search_rect(area: Rect) -> Rect {
    let width = (area.width as u32 * 70 / 100) as u16;
    let max_height = (area.height as u32 * 60 / 100).max(8) as u16;
    let height = max_height.min(area.height);

    let x = (area.width.saturating_sub(width)) / 2;
    let y = (area.height.saturating_sub(height)) / 4; // Bias toward top

    Rect::new(area.x + x, area.y + y, width, height)
}
