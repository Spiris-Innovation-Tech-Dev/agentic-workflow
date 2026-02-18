pub mod beads_view;
pub mod config_view;
pub mod cost_view;
pub mod create_popup;
pub mod detail_pane;
pub mod launch_popup;
pub mod search_popup;
pub mod status_bar;
pub mod styles;
pub mod task_list;

use crate::app::{ActiveView, App};
use ratatui::{
    layout::{Constraint, Direction, Layout},
    Frame,
};

pub fn draw(frame: &mut Frame, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(10),  // Main content
            Constraint::Length(2), // Status bar
        ])
        .split(frame.area());

    // Main content: dual-pane or single-pane depending on view
    match app.active_view {
        ActiveView::Tasks => draw_dual_pane(frame, app, chunks[0]),
        ActiveView::BeadsIssues => beads_view::draw(frame, app, chunks[0]),
        ActiveView::Config => config_view::draw(frame, app, chunks[0]),
        ActiveView::CostSummary => cost_view::draw(frame, app, chunks[0]),
    };

    // Status bar
    status_bar::draw(frame, app, chunks[1]);

    // Popup overlays (drawn on top)
    if app.launch_popup.is_some() {
        launch_popup::draw(frame, app);
    }
    if app.create_popup.is_some() {
        create_popup::draw(frame, app);
    }
    if app.search_popup.is_some() {
        search_popup::draw(frame, app);
    }
}

fn draw_dual_pane(frame: &mut Frame, app: &App, area: ratatui::layout::Rect) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(40), Constraint::Percentage(60)])
        .split(area);

    task_list::draw(frame, app, chunks[0]);
    detail_pane::draw(frame, app, chunks[1]);
}
