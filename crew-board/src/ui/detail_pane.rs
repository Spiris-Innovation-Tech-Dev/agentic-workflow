use crate::app::{App, DetailMode, FocusPane, TreeRow};
use crate::data::task::{self, Interaction, Discovery, PHASE_ORDER};
use crate::ui::styles;
use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};

pub fn draw(frame: &mut Frame, app: &App, area: Rect) {
    let is_focused = app.focus_pane == FocusPane::Right;
    let border_style = if is_focused {
        styles::focused_border_style()
    } else {
        styles::unfocused_border_style()
    };

    // If a repo row is selected, show repo summary
    if let Some(TreeRow::Repo(ri)) = app.current_tree_row() {
        draw_repo_summary(frame, app, *ri, area, border_style, is_focused);
        return;
    }

    // Dispatch based on detail mode
    match &app.detail_mode {
        DetailMode::Overview => draw_overview(frame, app, area, border_style, is_focused),
        DetailMode::DocList { cursor } => {
            draw_doc_list(frame, app, area, border_style, *cursor, is_focused)
        }
        DetailMode::DocReader {
            artifact_index,
            content,
        } => draw_doc_reader(frame, app, area, border_style, *artifact_index, content, is_focused),
        DetailMode::History => draw_history(frame, app, area, border_style, is_focused),
    }
}

// ── Overview (default task detail) ──────────────────────────────────────────

fn draw_overview(frame: &mut Frame, app: &App, area: Rect, border_style: Style, is_focused: bool) {
    let task = match app.current_task() {
        Some(t) => t,
        None => {
            let focus_marker = if is_focused { " ◄" } else { "" };
            let block = Block::default()
                .title(format!(" Details{} ", focus_marker))
                .borders(Borders::ALL)
                .border_style(border_style);
            let para = Paragraph::new("Select a task or repo").block(block);
            frame.render_widget(para, area);
            return;
        }
    };

    let mut lines: Vec<Line> = Vec::new();

    // Task ID and description
    lines.push(Line::from(vec![Span::styled(
        task.task_id.as_str(),
        Style::default()
            .fg(Color::Cyan)
            .add_modifier(Modifier::BOLD),
    )]));
    if !task.description.is_empty() {
        let desc = if task.description.len() > 200 {
            format!("{}...", &task.description[..200])
        } else {
            task.description.clone()
        };
        lines.push(Line::from(Span::styled(
            desc,
            Style::default().fg(Color::White),
        )));
    }
    lines.push(Line::from(""));

    // Workflow mode
    if let Some(ref mode) = task.workflow_mode {
        lines.push(Line::from(vec![
            Span::styled("Mode: ", styles::dim_style()),
            Span::styled(
                mode.effective.as_str(),
                Style::default().fg(Color::Yellow),
            ),
            if !mode.estimated_cost.is_empty() {
                Span::styled(format!(" ({})", mode.estimated_cost), styles::dim_style())
            } else {
                Span::raw("")
            },
        ]));
    }

    // Iteration
    lines.push(Line::from(vec![
        Span::styled("Iteration: ", styles::dim_style()),
        Span::raw(format!("{}", task.iteration)),
    ]));
    lines.push(Line::from(""));

    // Worktree info
    if let Some(ref wt) = task.worktree {
        let scheme_name = wt
            .launch
            .as_ref()
            .map(|l| l.color_scheme.as_str())
            .unwrap_or("none");
        let accent = styles::get_scheme(wt.color_scheme_index).tab;

        lines.push(Line::from(Span::styled(
            "── Worktree ──",
            styles::header_style(),
        )));
        lines.push(Line::from(vec![
            Span::styled("Status: ", styles::dim_style()),
            Span::styled(
                wt.status.as_str(),
                if wt.status == "active" {
                    Style::default().fg(Color::Green)
                } else {
                    Style::default().fg(Color::DarkGray)
                },
            ),
        ]));
        lines.push(Line::from(vec![
            Span::styled("Branch: ", styles::dim_style()),
            Span::raw(wt.branch.as_str()),
        ]));
        lines.push(Line::from(vec![
            Span::styled("Color:  ", styles::dim_style()),
            Span::styled(format!("■ {}", scheme_name), Style::default().fg(accent)),
        ]));
        if let Some(ref launch) = wt.launch {
            lines.push(Line::from(vec![
                Span::styled("Host:   ", styles::dim_style()),
                Span::raw(launch.ai_host.as_str()),
                Span::styled(" | ", styles::dim_style()),
                Span::raw(launch.terminal_env.as_str()),
            ]));
        }
        lines.push(Line::from(""));
    }

    // Phase progress
    lines.push(Line::from(Span::styled(
        "── Phases ──",
        styles::header_style(),
    )));
    let current_phase = task.phase.as_deref().unwrap_or("");
    for phase in PHASE_ORDER {
        let is_completed = task.phases_completed.contains(&phase.to_string());
        let is_current = *phase == current_phase;
        let symbol = if is_completed {
            "✓"
        } else if is_current {
            "▸"
        } else {
            "○"
        };
        let style = styles::phase_style(phase, is_current, is_completed);
        lines.push(Line::from(vec![
            Span::styled(format!("  {} ", symbol), style),
            Span::styled(*phase, style),
        ]));
    }
    lines.push(Line::from(""));

    // Implementation progress bar
    if task.implementation_progress.total_steps > 0 {
        let prog = &task.implementation_progress;
        let pct = (prog.current_step as f64 / prog.total_steps as f64 * 100.0) as u32;
        let filled = (pct as usize) / 5; // 20 chars wide
        let empty = 20usize.saturating_sub(filled);
        lines.push(Line::from(Span::styled(
            "── Implementation ──",
            styles::header_style(),
        )));
        lines.push(Line::from(vec![
            Span::styled(
                format!("  {}{}", "█".repeat(filled), "░".repeat(empty)),
                Style::default().fg(Color::Green),
            ),
            Span::raw(format!(
                " {}% ({}/{})",
                pct, prog.current_step, prog.total_steps
            )),
        ]));
        if !prog.steps_completed.is_empty() {
            lines.push(Line::from(vec![
                Span::styled("  Steps: ", styles::dim_style()),
                Span::raw(prog.steps_completed.join(", ")),
            ]));
        }
        lines.push(Line::from(""));
    }

    // Review issues count
    if !task.review_issues.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("Review Issues: ", Style::default().fg(Color::Red)),
            Span::raw(format!("{}", task.review_issues.len())),
        ]));
    }

    // Concerns count
    if !task.concerns.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("Concerns: ", Style::default().fg(Color::Yellow)),
            Span::raw(format!("{}", task.concerns.len())),
        ]));
    }

    // Documents indicator
    if !app.cached_artifacts.is_empty() {
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled(
            "── Documents ──",
            styles::header_style(),
        )));
        let doc_names: Vec<&str> = app
            .cached_artifacts
            .iter()
            .map(|a| a.label.as_str())
            .collect();
        lines.push(Line::from(vec![
            Span::styled(
                format!("  {} docs: ", app.cached_artifacts.len()),
                styles::dim_style(),
            ),
            Span::styled(
                doc_names.join(", "),
                Style::default().fg(Color::White),
            ),
        ]));
        lines.push(Line::from(Span::styled(
            "  Press 'd' to browse documents",
            Style::default().fg(Color::DarkGray),
        )));
    }

    // Decisions indicator
    if !task.human_decisions.is_empty() {
        lines.push(Line::from(""));
        lines.push(Line::from(vec![
            Span::styled(
                format!("  {} decisions", task.human_decisions.len()),
                styles::dim_style(),
            ),
            Span::styled(
                "  Press 'h' for history",
                Style::default().fg(Color::DarkGray),
            ),
        ]));
    }

    // Timestamps
    lines.push(Line::from(""));
    lines.push(Line::from(vec![
        Span::styled("Created: ", styles::dim_style()),
        Span::raw(format_timestamp(&task.created_at)),
    ]));
    lines.push(Line::from(vec![
        Span::styled("Updated: ", styles::dim_style()),
        Span::raw(format_timestamp(&task.updated_at)),
    ]));

    let focus_marker = if is_focused { " ◄" } else { "" };
    let breadcrumb = format!(" {} > Overview{} ", task.task_id, focus_marker);
    let text = Text::from(lines);
    let block = Block::default()
        .title(breadcrumb)
        .borders(Borders::ALL)
        .border_style(border_style);
    let paragraph = Paragraph::new(text)
        .block(block)
        .wrap(Wrap { trim: false })
        .scroll((app.detail_scroll, 0));

    frame.render_widget(paragraph, area);
}

// ── Document List ───────────────────────────────────────────────────────────

fn draw_doc_list(frame: &mut Frame, app: &App, area: Rect, border_style: Style, cursor: usize, is_focused: bool) {
    let task = app.current_task();
    let task_id = task.map(|t| t.task_id.as_str()).unwrap_or("?");

    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::from(vec![
        Span::styled(
            task_id.to_string(),
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" — Documents", styles::dim_style()),
    ]));
    lines.push(Line::from(""));

    if app.cached_artifacts.is_empty() {
        lines.push(Line::from(Span::styled(
            "  No documents found",
            styles::dim_style(),
        )));
    } else {
        for (i, artifact) in app.cached_artifacts.iter().enumerate() {
            let is_selected = i == cursor;
            let prefix = if is_selected { "▸ " } else { "  " };

            let size_str = format_size(artifact.size_bytes);
            let time_str = artifact
                .modified
                .map(|m| m.format("%Y-%m-%d %H:%M").to_string())
                .unwrap_or_default();

            let label_style = if is_selected {
                styles::selected_style()
            } else {
                Style::default().fg(Color::White)
            };

            // Icon based on phase
            let icon = match artifact.name.as_str() {
                "architect" => "🏗 ",
                "developer" => "💻 ",
                "reviewer" => "🔍 ",
                "skeptic" => "🤔 ",
                "plan" => "📋 ",
                "implementer" => "⚙ ",
                "technical_writer" => "📝 ",
                _ => "📄 ",
            };

            lines.push(Line::from(vec![
                Span::styled(prefix, label_style),
                Span::raw(icon),
                Span::styled(artifact.label.clone(), label_style),
            ]));
            lines.push(Line::from(vec![
                Span::raw("     "),
                Span::styled(size_str, styles::dim_style()),
                Span::styled("  ", styles::dim_style()),
                Span::styled(time_str, styles::dim_style()),
            ]));

            if is_selected {
                // Show a preview (first 3 non-empty lines)
                if let Ok(content) = std::fs::read_to_string(&artifact.path) {
                    lines.push(Line::from(""));
                    let preview_lines: Vec<&str> = content
                        .lines()
                        .filter(|l| !l.trim().is_empty())
                        .take(3)
                        .collect();
                    for pl in preview_lines {
                        let truncated = if pl.len() > 60 {
                            format!("{}...", &pl[..60])
                        } else {
                            pl.to_string()
                        };
                        lines.push(Line::from(Span::styled(
                            format!("     {}", truncated),
                            Style::default().fg(Color::DarkGray),
                        )));
                    }
                    lines.push(Line::from(""));
                }
            }
        }
    }

    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "↑↓ select  Enter read  Esc back",
        Style::default().fg(Color::DarkGray),
    )));

    let focus_marker = if is_focused { " ◄" } else { "" };
    let breadcrumb = format!(" {} > Documents{} ", task_id, focus_marker);
    let text = Text::from(lines);
    let block = Block::default()
        .title(breadcrumb)
        .borders(Borders::ALL)
        .border_style(border_style);
    let paragraph = Paragraph::new(text)
        .block(block)
        .wrap(Wrap { trim: false })
        .scroll((app.detail_scroll, 0));

    frame.render_widget(paragraph, area);
}

// ── Document Reader ─────────────────────────────────────────────────────────

fn draw_doc_reader(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    border_style: Style,
    artifact_index: usize,
    content: &str,
    is_focused: bool,
) {
    let task_id = app.current_task().map(|t| t.task_id.as_str()).unwrap_or("?");
    let artifact = app.cached_artifacts.get(artifact_index);
    let doc_name = artifact.map(|a| a.label.as_str()).unwrap_or("Document");
    let focus_marker = if is_focused { " ◄" } else { "" };
    let title = format!(" {} > Documents > {}{} ", task_id, doc_name, focus_marker);

    let mut lines: Vec<Line> = Vec::new();

    // Render markdown-like content with basic highlighting
    for line in content.lines() {
        if line.starts_with("# ") {
            lines.push(Line::from(Span::styled(
                line.to_string(),
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            )));
        } else if line.starts_with("## ") {
            lines.push(Line::from(Span::styled(
                line.to_string(),
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD),
            )));
        } else if line.starts_with("### ") {
            lines.push(Line::from(Span::styled(
                line.to_string(),
                Style::default()
                    .fg(Color::Green)
                    .add_modifier(Modifier::BOLD),
            )));
        } else if line.starts_with("- ") || line.starts_with("* ") {
            // Bullet list: highlight the bullet
            lines.push(Line::from(vec![
                Span::styled("• ", Style::default().fg(Color::Cyan)),
                Span::raw(&line[2..]),
            ]));
        } else if line.starts_with("```") {
            lines.push(Line::from(Span::styled(
                line.to_string(),
                Style::default().fg(Color::DarkGray),
            )));
        } else if line.starts_with('>') {
            lines.push(Line::from(Span::styled(
                line.to_string(),
                Style::default().fg(Color::Magenta),
            )));
        } else if line.trim().is_empty() {
            lines.push(Line::from(""));
        } else {
            lines.push(Line::from(Span::raw(line)));
        }
    }

    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "PgUp/PgDn scroll  Esc/Backspace back",
        Style::default().fg(Color::DarkGray),
    )));

    let text = Text::from(lines);
    let block = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_style(border_style);
    let paragraph = Paragraph::new(text)
        .block(block)
        .wrap(Wrap { trim: false })
        .scroll((app.detail_scroll, 0));

    frame.render_widget(paragraph, area);
}

// ── History View ────────────────────────────────────────────────────────────

fn draw_history(frame: &mut Frame, app: &App, area: Rect, border_style: Style, is_focused: bool) {
    let task = match app.current_task() {
        Some(t) => t,
        None => {
            let focus_marker = if is_focused { " ◄" } else { "" };
            let block = Block::default()
                .title(format!(" History{} ", focus_marker))
                .borders(Borders::ALL)
                .border_style(border_style);
            frame.render_widget(Paragraph::new("No task selected").block(block), area);
            return;
        }
    };

    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::from(vec![
        Span::styled(
            task.task_id.as_str(),
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" — State Inspector", styles::dim_style()),
    ]));
    if !task.description.is_empty() {
        lines.push(Line::from(Span::styled(
            task.description.as_str(),
            Style::default().fg(Color::White),
        )));
    }
    lines.push(Line::from(""));

    // ── Workflow Mode ──
    if let Some(ref mode) = task.workflow_mode {
        lines.push(Line::from(Span::styled(
            "── Workflow Mode ──",
            styles::header_style(),
        )));
        lines.push(Line::from(vec![
            Span::styled("  Effective:  ", styles::dim_style()),
            Span::styled(
                mode.effective.as_str(),
                Style::default().fg(Color::Yellow),
            ),
        ]));
        if !mode.requested.is_empty() && mode.requested != mode.effective {
            lines.push(Line::from(vec![
                Span::styled("  Requested:  ", styles::dim_style()),
                Span::raw(mode.requested.as_str()),
            ]));
        }
        if !mode.detection_reason.is_empty() {
            lines.push(Line::from(vec![
                Span::styled("  Reason:     ", styles::dim_style()),
                Span::raw(mode.detection_reason.as_str()),
            ]));
        }
        if mode.confidence > 0.0 {
            lines.push(Line::from(vec![
                Span::styled("  Confidence: ", styles::dim_style()),
                Span::raw(format!("{:.0}%", mode.confidence * 100.0)),
            ]));
        }
        if !mode.estimated_cost.is_empty() {
            lines.push(Line::from(vec![
                Span::styled("  Est. cost:  ", styles::dim_style()),
                Span::styled(
                    mode.estimated_cost.as_str(),
                    Style::default().fg(Color::Green),
                ),
            ]));
        }
        if !mode.phases.is_empty() {
            lines.push(Line::from(vec![
                Span::styled("  Phases:     ", styles::dim_style()),
                Span::raw(mode.phases.join(", ")),
            ]));
        }
        lines.push(Line::from(""));
    }

    // ── Phase Timeline ──
    lines.push(Line::from(Span::styled(
        "── Phase Timeline ──",
        styles::header_style(),
    )));
    lines.push(Line::from(vec![
        Span::styled("  Iteration: ", styles::dim_style()),
        Span::styled(
            format!("{}", task.iteration),
            Style::default().fg(Color::Yellow),
        ),
    ]));
    let current_phase = task.phase.as_deref().unwrap_or("");
    for phase in PHASE_ORDER {
        let is_completed = task.phases_completed.contains(&phase.to_string());
        let is_current = *phase == current_phase;
        let (symbol, status_label) = if is_completed {
            ("✓", "completed")
        } else if is_current {
            ("▸", "in progress")
        } else {
            ("○", "pending")
        };
        let style = styles::phase_style(phase, is_current, is_completed);
        lines.push(Line::from(vec![
            Span::styled(format!("  {} ", symbol), style),
            Span::styled(format!("{:<18}", phase), style),
            Span::styled(status_label, styles::dim_style()),
        ]));
    }
    lines.push(Line::from(""));

    // ── Implementation Progress ──
    if task.implementation_progress.total_steps > 0 {
        let prog = &task.implementation_progress;
        let pct = (prog.current_step as f64 / prog.total_steps as f64 * 100.0) as u32;
        let filled = (pct as usize) / 5;
        let empty = 20usize.saturating_sub(filled);

        lines.push(Line::from(Span::styled(
            "── Implementation Progress ──",
            styles::header_style(),
        )));
        lines.push(Line::from(vec![
            Span::styled(
                format!("  {}{}", "█".repeat(filled), "░".repeat(empty)),
                Style::default().fg(Color::Green),
            ),
            Span::raw(format!(
                " {}% ({}/{})",
                pct, prog.current_step, prog.total_steps
            )),
        ]));
        if !prog.steps_completed.is_empty() {
            lines.push(Line::from(vec![
                Span::styled("  Completed:  ", styles::dim_style()),
                Span::raw(prog.steps_completed.join(", ")),
            ]));
        }
        lines.push(Line::from(""));
    }

    // ── Interactions ──
    render_interactions_section(&mut lines, &app.cached_interactions);

    // ── Discoveries ──
    render_discoveries_section(&mut lines, &app.cached_discoveries);

    // ── Knowledge Base ──
    if let Some(ref kb) = task.knowledge_base_inventory {
        let has_content = kb.path.as_ref().is_some_and(|p| !p.is_empty()) || !kb.files.is_empty();
        if has_content {
            lines.push(Line::from(Span::styled(
                "── Knowledge Base ──",
                styles::header_style(),
            )));
            if let Some(ref path) = kb.path {
                if !path.is_empty() {
                    lines.push(Line::from(vec![
                        Span::styled("  Path: ", styles::dim_style()),
                        Span::raw(path.as_str()),
                    ]));
                }
            }
            if !kb.files.is_empty() {
                lines.push(Line::from(vec![
                    Span::styled(
                        format!("  {} files:", kb.files.len()),
                        styles::dim_style(),
                    ),
                ]));
                for f in &kb.files {
                    lines.push(Line::from(vec![
                        Span::styled("    ", styles::dim_style()),
                        Span::raw(f.as_str()),
                    ]));
                }
            }
            lines.push(Line::from(""));
        }
    }

    // ── Worktree ──
    if let Some(ref wt) = task.worktree {
        let accent = styles::get_scheme(wt.color_scheme_index).tab;

        lines.push(Line::from(Span::styled(
            "── Worktree ──",
            styles::header_style(),
        )));
        lines.push(Line::from(vec![
            Span::styled("  Status:   ", styles::dim_style()),
            Span::styled(
                wt.status.as_str(),
                if wt.status == "active" {
                    Style::default().fg(Color::Green)
                } else {
                    Style::default().fg(Color::DarkGray)
                },
            ),
        ]));
        lines.push(Line::from(vec![
            Span::styled("  Branch:   ", styles::dim_style()),
            Span::raw(wt.branch.as_str()),
        ]));
        if !wt.base_branch.is_empty() {
            lines.push(Line::from(vec![
                Span::styled("  Base:     ", styles::dim_style()),
                Span::raw(wt.base_branch.as_str()),
            ]));
        }
        if !wt.path.is_empty() {
            lines.push(Line::from(vec![
                Span::styled("  Path:     ", styles::dim_style()),
                Span::raw(wt.path.as_str()),
            ]));
        }
        if let Some(ref launch) = wt.launch {
            let scheme_name = launch.color_scheme.as_str();
            lines.push(Line::from(vec![
                Span::styled("  Color:    ", styles::dim_style()),
                Span::styled(format!("■ {}", scheme_name), Style::default().fg(accent)),
            ]));
            lines.push(Line::from(vec![
                Span::styled("  AI Host:  ", styles::dim_style()),
                Span::raw(launch.ai_host.as_str()),
            ]));
            lines.push(Line::from(vec![
                Span::styled("  Terminal: ", styles::dim_style()),
                Span::raw(launch.terminal_env.as_str()),
            ]));
            if !launch.worktree_abs_path.is_empty() {
                lines.push(Line::from(vec![
                    Span::styled("  Abs path: ", styles::dim_style()),
                    Span::raw(launch.worktree_abs_path.as_str()),
                ]));
            }
            if !launch.launched_at.is_empty() {
                lines.push(Line::from(vec![
                    Span::styled("  Launched: ", styles::dim_style()),
                    Span::raw(format_timestamp(&launch.launched_at)),
                ]));
            }
        }
        if !wt.created_at.is_empty() {
            lines.push(Line::from(vec![
                Span::styled("  Created:  ", styles::dim_style()),
                Span::raw(format_timestamp(&wt.created_at)),
            ]));
        }
        lines.push(Line::from(""));
    }

    // ── Human Decisions ──
    let decisions = task::parse_decisions(&task.human_decisions);
    if !decisions.is_empty() {
        lines.push(Line::from(Span::styled(
            format!("── Human Decisions ({}) ──", decisions.len()),
            styles::header_style(),
        )));
        for (i, decision) in decisions.iter().enumerate() {
            lines.push(Line::from(vec![
                Span::styled(
                    format!("  {}. ", i + 1),
                    Style::default().fg(Color::Yellow),
                ),
                Span::styled(&decision.checkpoint, Style::default().fg(Color::Cyan)),
                Span::styled(" → ", styles::dim_style()),
                Span::styled(
                    &decision.decision,
                    if decision.decision == "approve" {
                        Style::default().fg(Color::Green)
                    } else {
                        Style::default().fg(Color::Red)
                    },
                ),
            ]));
            if !decision.timestamp.is_empty() {
                lines.push(Line::from(Span::styled(
                    format!("     at {}", format_timestamp(&decision.timestamp)),
                    Style::default().fg(Color::DarkGray),
                )));
            }
            if !decision.notes.is_empty() {
                let note_lines = wrap_text(&decision.notes, 60);
                for nl in note_lines {
                    lines.push(Line::from(Span::styled(
                        format!("     {}", nl),
                        styles::dim_style(),
                    )));
                }
            }
            lines.push(Line::from(""));
        }
    }

    // ── Files Changed ──
    if !task.files_changed.is_empty() {
        lines.push(Line::from(Span::styled(
            format!("── Files Changed ({}) ──", task.files_changed.len()),
            styles::header_style(),
        )));
        for f in &task.files_changed {
            lines.push(Line::from(vec![
                Span::styled("  ", styles::dim_style()),
                Span::styled(f.as_str(), Style::default().fg(Color::White)),
            ]));
        }
        lines.push(Line::from(""));
    }

    // ── Optional Phases ──
    if !task.optional_phases.is_empty() {
        lines.push(Line::from(Span::styled(
            format!("── Optional Phases ({}) ──", task.optional_phases.len()),
            styles::header_style(),
        )));
        for phase_name in &task.optional_phases {
            let reason = task
                .optional_phase_reasons
                .as_ref()
                .and_then(|v| v.get(phase_name))
                .and_then(|r| r.get("reason"))
                .and_then(|r| r.as_str())
                .unwrap_or("");
            lines.push(Line::from(vec![
                Span::styled("  + ", Style::default().fg(Color::Magenta)),
                Span::styled(phase_name.as_str(), Style::default().fg(Color::Magenta)),
            ]));
            if !reason.is_empty() {
                lines.push(Line::from(Span::styled(
                    format!("    {}", reason),
                    styles::dim_style(),
                )));
            }
        }
        lines.push(Line::from(""));
    }

    // ── Review Issues ──
    if !task.review_issues.is_empty() {
        lines.push(Line::from(Span::styled(
            "── Review Issues ──",
            styles::header_style(),
        )));
        for issue in &task.review_issues {
            let severity = issue
                .get("severity")
                .and_then(|s| s.as_str())
                .unwrap_or("?");
            let desc = issue
                .get("description")
                .and_then(|d| d.as_str())
                .unwrap_or_else(|| {
                    issue
                        .get("issue")
                        .and_then(|d| d.as_str())
                        .unwrap_or("(no description)")
                });
            let sev_style = match severity {
                "high" | "H" => Style::default().fg(Color::Red),
                "medium" | "M" => Style::default().fg(Color::Yellow),
                _ => Style::default().fg(Color::DarkGray),
            };
            lines.push(Line::from(vec![
                Span::styled(format!("  [{}] ", severity), sev_style),
                Span::raw(desc),
            ]));
        }
        lines.push(Line::from(""));
    }

    // ── Concerns ──
    if !task.concerns.is_empty() {
        lines.push(Line::from(Span::styled(
            "── Concerns ──",
            styles::header_style(),
        )));
        for concern in &task.concerns {
            let text_val = concern
                .get("concern")
                .or_else(|| concern.get("text"))
                .and_then(|c| c.as_str())
                .unwrap_or("(unknown)");
            let status = concern
                .get("status")
                .and_then(|s| s.as_str())
                .unwrap_or("open");
            let status_style = if status == "addressed" {
                Style::default().fg(Color::Green)
            } else {
                Style::default().fg(Color::Yellow)
            };
            lines.push(Line::from(vec![
                Span::styled(format!("  [{}] ", status), status_style),
                Span::raw(text_val),
            ]));
        }
        lines.push(Line::from(""));
    }

    // ── Docs Needed ──
    if !task.docs_needed.is_empty() {
        lines.push(Line::from(Span::styled(
            "── Documentation Gaps ──",
            styles::header_style(),
        )));
        for doc in &task.docs_needed {
            lines.push(Line::from(vec![
                Span::styled("  • ", Style::default().fg(Color::Yellow)),
                Span::raw(doc.as_str()),
            ]));
        }
        lines.push(Line::from(""));
    }

    // ── Cost Summary ──
    if let Some(ref cost) = task.cost_summary {
        lines.push(Line::from(Span::styled(
            "── Cost Summary ──",
            styles::header_style(),
        )));
        if let Some(obj) = cost.as_object() {
            for (key, val) in obj {
                let display = match val {
                    serde_json::Value::String(s) => s.clone(),
                    serde_json::Value::Number(n) => {
                        if let Some(f) = n.as_f64() {
                            format!("${:.4}", f)
                        } else {
                            n.to_string()
                        }
                    }
                    other => other.to_string(),
                };
                lines.push(Line::from(vec![
                    Span::styled(format!("  {}: ", key), styles::dim_style()),
                    Span::raw(display),
                ]));
            }
        } else {
            lines.push(Line::from(vec![
                Span::styled("  ", styles::dim_style()),
                Span::raw(cost.to_string()),
            ]));
        }
        lines.push(Line::from(""));
    }

    // ── Timeline ──
    lines.push(Line::from(Span::styled(
        "── Timeline ──",
        styles::header_style(),
    )));
    if let Some(ref status) = task.status {
        let status_style = match status.as_str() {
            "completed" => Style::default().fg(Color::Green),
            "active" | "in_progress" => Style::default().fg(Color::Yellow),
            _ => Style::default().fg(Color::White),
        };
        lines.push(Line::from(vec![
            Span::styled("  Status:    ", styles::dim_style()),
            Span::styled(status.as_str(), status_style),
        ]));
    }
    lines.push(Line::from(vec![
        Span::styled("  Created:   ", styles::dim_style()),
        Span::raw(format_timestamp(&task.created_at)),
    ]));
    lines.push(Line::from(vec![
        Span::styled("  Updated:   ", styles::dim_style()),
        Span::raw(format_timestamp(&task.updated_at)),
    ]));
    if let Some(ref completed_at) = task.completed_at {
        lines.push(Line::from(vec![
            Span::styled("  Completed: ", styles::dim_style()),
            Span::styled(
                format_timestamp(completed_at),
                Style::default().fg(Color::Green),
            ),
        ]));
    }

    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "PgUp/PgDn scroll  Esc back",
        Style::default().fg(Color::DarkGray),
    )));

    let focus_marker = if is_focused { " ◄" } else { "" };
    let breadcrumb = format!(" {} > History{} ", task.task_id, focus_marker);
    let text = Text::from(lines);
    let block = Block::default()
        .title(breadcrumb)
        .borders(Borders::ALL)
        .border_style(border_style);
    let paragraph = Paragraph::new(text)
        .block(block)
        .wrap(Wrap { trim: false })
        .scroll((app.detail_scroll, 0));

    frame.render_widget(paragraph, area);
}

// ── Repo Summary ────────────────────────────────────────────────────────────

fn draw_repo_summary(
    frame: &mut Frame,
    app: &App,
    ri: usize,
    area: Rect,
    border_style: Style,
    is_focused: bool,
) {
    let repo = &app.repos[ri];
    let mut lines: Vec<Line> = Vec::new();

    lines.push(Line::from(Span::styled(
        repo.name.clone(),
        Style::default()
            .fg(Color::Cyan)
            .add_modifier(Modifier::BOLD),
    )));
    lines.push(Line::from(Span::styled(
        repo.path.display().to_string(),
        styles::dim_style(),
    )));
    lines.push(Line::from(""));

    // Task stats
    let total = repo.tasks.len();
    let active = repo.active_task_count();
    let done = total - active;
    lines.push(Line::from(Span::styled(
        "── Tasks ──",
        styles::header_style(),
    )));
    lines.push(Line::from(vec![
        Span::styled("  Total:  ", styles::dim_style()),
        Span::raw(format!("{}", total)),
    ]));
    lines.push(Line::from(vec![
        Span::styled("  Active: ", styles::dim_style()),
        Span::styled(format!("{}", active), Style::default().fg(Color::Yellow)),
    ]));
    lines.push(Line::from(vec![
        Span::styled("  Done:   ", styles::dim_style()),
        Span::styled(format!("{}", done), Style::default().fg(Color::Green)),
    ]));
    lines.push(Line::from(""));

    // Issue stats
    let open = repo.open_issue_count();
    let in_prog = repo
        .issues
        .iter()
        .filter(|i| i.status == "in_progress")
        .count();
    let closed = repo.issues.len() - open - in_prog;
    lines.push(Line::from(Span::styled(
        "── Issues ──",
        styles::header_style(),
    )));
    lines.push(Line::from(vec![
        Span::styled("  Open:        ", styles::dim_style()),
        Span::styled(format!("{}", open), Style::default().fg(Color::Yellow)),
    ]));
    lines.push(Line::from(vec![
        Span::styled("  In Progress: ", styles::dim_style()),
        Span::styled(
            format!("{}", in_prog),
            Style::default().fg(Color::Green),
        ),
    ]));
    lines.push(Line::from(vec![
        Span::styled("  Closed:      ", styles::dim_style()),
        Span::raw(format!("{}", closed)),
    ]));
    lines.push(Line::from(""));

    // Config info
    if !repo.config_cascade.is_empty() {
        lines.push(Line::from(Span::styled(
            "── Config ──",
            styles::header_style(),
        )));
        for level in &repo.config_cascade {
            lines.push(Line::from(vec![
                Span::styled("  • ", styles::dim_style()),
                Span::raw(format!("{}: {}", level.label, level.path.display())),
            ]));
        }
    }

    let focus_marker = if is_focused { " ◄" } else { "" };
    let text = Text::from(lines);
    let block = Block::default()
        .title(format!(" Repo Summary{} ", focus_marker))
        .borders(Borders::ALL)
        .border_style(border_style);
    let paragraph = Paragraph::new(text)
        .block(block)
        .wrap(Wrap { trim: false })
        .scroll((app.detail_scroll, 0));

    frame.render_widget(paragraph, area);
}

// ── Interactions & Discoveries Renderers ─────────────────────────────────

fn render_interactions_section(lines: &mut Vec<Line>, interactions: &[Interaction]) {
    if interactions.is_empty() {
        return;
    }

    lines.push(Line::from(Span::styled(
        format!("── Interactions ({} entries) ──", interactions.len()),
        styles::header_style(),
    )));

    // Group by phase
    let mut current_phase = String::new();
    for entry in interactions {
        // Phase header when phase changes
        if !entry.phase.is_empty() && entry.phase != current_phase {
            current_phase = entry.phase.clone();
            lines.push(Line::from(Span::styled(
                format!("  {}:", current_phase),
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD),
            )));
        }

        let (marker, marker_color) = match entry.type_.as_str() {
            "checkpoint_question" => ("[Q]", Color::Cyan),
            "checkpoint_response" => ("[A]", Color::Green),
            "escalation_question" => ("[?]", Color::Magenta),
            "escalation_response" => ("[!]", Color::Magenta),
            "guidance" => ("[G]", Color::Blue),
            _ => match entry.role.as_str() {
                "agent" => ("[>]", Color::DarkGray),
                "human" => ("[H]", Color::Green),
                "system" => ("[S]", Color::DarkGray),
                _ => ("[-]", Color::DarkGray),
            },
        };

        // Truncate content to 120 chars
        let content = if entry.content.len() > 120 {
            format!("{}...", &entry.content[..120])
        } else {
            entry.content.clone()
        };

        // Wrap content lines
        let content_lines = wrap_text(&content, 70);
        if let Some((first, rest)) = content_lines.split_first() {
            lines.push(Line::from(vec![
                Span::styled(format!("    {} ", marker), Style::default().fg(marker_color)),
                Span::raw(first.clone()),
            ]));
            for continuation in rest {
                lines.push(Line::from(Span::styled(
                    format!("        {}", continuation),
                    styles::dim_style(),
                )));
            }
        }
    }
    lines.push(Line::from(""));
}

fn render_discoveries_section(lines: &mut Vec<Line>, discoveries: &[Discovery]) {
    if discoveries.is_empty() {
        return;
    }

    lines.push(Line::from(Span::styled(
        format!("── Discoveries ({}) ──", discoveries.len()),
        styles::header_style(),
    )));

    for entry in discoveries {
        let (icon, cat_color) = match entry.category.as_str() {
            "decision" => ("D", Color::Cyan),
            "pattern" => ("P", Color::Blue),
            "gotcha" => ("!", Color::Yellow),
            "blocker" => ("X", Color::Red),
            "preference" => ("~", Color::Magenta),
            _ => ("-", Color::DarkGray),
        };

        let content = if entry.content.len() > 120 {
            format!("{}...", &entry.content[..120])
        } else {
            entry.content.clone()
        };

        let content_lines = wrap_text(&content, 65);
        if let Some((first, rest)) = content_lines.split_first() {
            lines.push(Line::from(vec![
                Span::styled(
                    format!("  [{}] ", icon),
                    Style::default().fg(cat_color),
                ),
                Span::styled(
                    format!("{}: ", entry.category),
                    Style::default().fg(cat_color),
                ),
                Span::raw(first.clone()),
            ]));
            for continuation in rest {
                lines.push(Line::from(Span::styled(
                    format!("       {}", continuation),
                    styles::dim_style(),
                )));
            }
        }
    }
    lines.push(Line::from(""));
}

// ── Helpers ─────────────────────────────────────────────────────────────────

fn format_timestamp(ts: &str) -> String {
    if ts.len() >= 19 {
        ts[..19].to_string()
    } else {
        ts.to_string()
    }
}

fn format_size(bytes: u64) -> String {
    if bytes < 1024 {
        format!("{}B", bytes)
    } else if bytes < 1024 * 1024 {
        format!("{:.1}KB", bytes as f64 / 1024.0)
    } else {
        format!("{:.1}MB", bytes as f64 / (1024.0 * 1024.0))
    }
}

fn wrap_text(text: &str, width: usize) -> Vec<String> {
    let mut result = Vec::new();
    let mut current = String::new();
    for word in text.split_whitespace() {
        if current.len() + word.len() + 1 > width && !current.is_empty() {
            result.push(current);
            current = String::new();
        }
        if !current.is_empty() {
            current.push(' ');
        }
        current.push_str(word);
    }
    if !current.is_empty() {
        result.push(current);
    }
    result
}
