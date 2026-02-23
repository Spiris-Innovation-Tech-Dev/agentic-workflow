use crate::app::App;
use crate::ui::styles;
use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};

pub fn draw(frame: &mut Frame, app: &App, area: Rect) {
    let repo = match app.current_repo() {
        Some(r) => r,
        None => {
            let block = Block::default()
                .title(" Cost Summary ")
                .borders(Borders::ALL);
            frame.render_widget(
                Paragraph::new("No repo selected").block(block),
                area,
            );
            return;
        }
    };

    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::from(Span::styled(
        "Cost Summary",
        Style::default()
            .fg(Color::Cyan)
            .add_modifier(Modifier::BOLD),
    )));
    lines.push(Line::from(""));

    let mut has_cost_data = false;
    for loaded in &repo.tasks {
        let task = &loaded.state;
        // Show estimated cost from workflow mode
        if let Some(ref mode) = task.workflow_mode {
            if !mode.estimated_cost.is_empty() {
                has_cost_data = true;
                lines.push(Line::from(vec![
                    Span::styled(
                        format!("{}: ", task.task_id),
                        Style::default().add_modifier(Modifier::BOLD),
                    ),
                    Span::styled(
                        mode.effective.as_str(),
                        Style::default().fg(Color::Yellow),
                    ),
                    Span::raw(" mode, est. "),
                    Span::styled(
                        mode.estimated_cost.as_str(),
                        Style::default().fg(Color::Green),
                    ),
                ]));
            }
        }

        // Show actual cost summary if available
        if let Some(ref cost) = task.cost_summary {
            has_cost_data = true;
            if let Some(total) = cost.get("total_cost") {
                lines.push(Line::from(vec![
                    Span::styled(
                        format!("  {} actual: ", task.task_id),
                        styles::dim_style(),
                    ),
                    Span::styled(
                        format!("${:.4}", total.as_f64().unwrap_or(0.0)),
                        Style::default().fg(Color::Green),
                    ),
                ]));
            }
        }
    }

    if !has_cost_data {
        lines.push(Line::from(Span::styled(
            "No cost data available yet.",
            styles::dim_style(),
        )));
        lines.push(Line::from(""));
        lines.push(Line::from(
            "Cost data is recorded during workflow execution.",
        ));
    }

    let text = Text::from(lines);
    let block = Block::default()
        .title(" Cost Summary ")
        .borders(Borders::ALL);
    let paragraph = Paragraph::new(text)
        .block(block)
        .wrap(Wrap { trim: false })
        .scroll((app.detail_scroll, 0));

    frame.render_widget(paragraph, area);
}
