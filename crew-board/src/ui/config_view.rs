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
            let block = Block::default().title(" Config ").borders(Borders::ALL);
            frame.render_widget(
                Paragraph::new("No repo selected").block(block),
                area,
            );
            return;
        }
    };

    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::from(Span::styled(
        format!("Configuration Cascade for {}", repo.name),
        Style::default()
            .fg(Color::Cyan)
            .add_modifier(Modifier::BOLD),
    )));
    lines.push(Line::from(""));

    if repo.config_cascade.is_empty() {
        lines.push(Line::from("No config files found. Using defaults."));
    } else {
        for (i, level) in repo.config_cascade.iter().enumerate() {
            lines.push(Line::from(vec![Span::styled(
                format!("{}. {} ", i + 1, level.label),
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD),
            )]));
            lines.push(Line::from(vec![
                Span::styled("   Path: ", styles::dim_style()),
                Span::raw(level.path.display().to_string()),
            ]));

            if let serde_yaml::Value::Mapping(ref map) = level.data {
                for (key, _value) in map {
                    if let serde_yaml::Value::String(ref k) = key {
                        lines.push(Line::from(vec![
                            Span::styled("   • ", styles::dim_style()),
                            Span::raw(k.clone()),
                        ]));
                    }
                }
            }
            lines.push(Line::from(""));
        }
    }

    let text = Text::from(lines);
    let block = Block::default().title(" Config ").borders(Borders::ALL);
    let paragraph = Paragraph::new(text)
        .block(block)
        .wrap(Wrap { trim: false })
        .scroll((app.detail_scroll, 0));

    frame.render_widget(paragraph, area);
}
