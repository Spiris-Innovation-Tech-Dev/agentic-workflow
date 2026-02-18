use crate::data::task::{self, TaskArtifact};
use crate::data::RepoData;
use crate::launcher::{self, AiHost, TerminalEnv};
use std::collections::HashSet;
use std::path::PathBuf;

/// Which view/tab is active.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ActiveView {
    Tasks,
    BeadsIssues,
    Config,
    CostSummary,
}

/// Which pane has focus in dual-pane views.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FocusPane {
    Left,
    Right,
}

/// A row in the flattened tree list.
#[derive(Debug, Clone)]
pub enum TreeRow {
    Repo(usize),            // index into repos vec
    Task(usize, usize),     // (repo_index, task_index)
}

/// What's shown in the detail (right) pane.
#[derive(Debug, Clone, PartialEq)]
pub enum DetailMode {
    /// Normal task/repo overview
    Overview,
    /// Browsing document list (cursor on a doc)
    DocList { cursor: usize },
    /// Reading a specific document
    DocReader {
        artifact_index: usize,
        content: String,
    },
    /// Viewing task history (decisions + iterations)
    History,
}

/// State for the F2 launch popup.
pub struct LaunchPopup {
    pub terminals: Vec<TerminalEnv>,
    pub hosts: Vec<AiHost>,
    pub step: LaunchStep,
    pub terminal_cursor: usize,
    pub host_cursor: usize,
    pub work_dir: PathBuf,
    pub task_id: String,
    pub task_desc: String,
    pub result_msg: Option<String>,
}

#[derive(PartialEq)]
pub enum LaunchStep {
    SelectTerminal,
    SelectHost,
    Done,
}

pub struct App {
    pub repos: Vec<RepoData>,
    pub repo_paths: Vec<PathBuf>,
    pub poll_interval_secs: u64,

    // Tree navigation state
    pub expanded_repos: HashSet<usize>,
    pub tree_rows: Vec<TreeRow>,
    pub tree_cursor: usize,

    // Issue navigation (for beads view)
    pub selected_issue: usize,

    pub active_view: ActiveView,
    pub focus_pane: FocusPane,

    // UI state
    pub should_quit: bool,
    pub last_refresh: std::time::Instant,
    pub detail_scroll: u16,

    // Detail pane state
    pub detail_mode: DetailMode,
    pub cached_artifacts: Vec<TaskArtifact>,
    pub cached_task_dir: Option<PathBuf>,

    // Launch popup
    pub launch_popup: Option<LaunchPopup>,
}

impl App {
    pub fn new(repo_paths: Vec<PathBuf>, poll_interval_secs: u64) -> Self {
        let repos: Vec<RepoData> = repo_paths.iter().map(|p| RepoData::load(p)).collect();

        // Auto-expand all repos on start
        let expanded: HashSet<usize> = (0..repos.len()).collect();

        let mut app = App {
            repos,
            repo_paths,
            poll_interval_secs,
            expanded_repos: expanded,
            tree_rows: Vec::new(),
            tree_cursor: 0,
            selected_issue: 0,
            active_view: ActiveView::Tasks,
            focus_pane: FocusPane::Left,
            should_quit: false,
            last_refresh: std::time::Instant::now(),
            detail_scroll: 0,
            detail_mode: DetailMode::Overview,
            cached_artifacts: Vec::new(),
            cached_task_dir: None,
            launch_popup: None,
        };
        app.rebuild_tree();
        app.ensure_artifacts();
        app
    }

    /// Rebuild the flattened tree from repos + expanded state.
    pub fn rebuild_tree(&mut self) {
        self.tree_rows.clear();
        for (ri, repo) in self.repos.iter().enumerate() {
            self.tree_rows.push(TreeRow::Repo(ri));
            if self.expanded_repos.contains(&ri) {
                for ti in 0..repo.tasks.len() {
                    self.tree_rows.push(TreeRow::Task(ri, ti));
                }
            }
        }
        // Clamp cursor
        if self.tree_cursor >= self.tree_rows.len() && !self.tree_rows.is_empty() {
            self.tree_cursor = self.tree_rows.len() - 1;
        }
    }

    /// Reload all data from disk.
    pub fn refresh(&mut self) {
        self.repos = self.repo_paths.iter().map(|p| RepoData::load(p)).collect();
        self.last_refresh = std::time::Instant::now();
        self.rebuild_tree();
        self.clamp_issue_selection();
        // Force artifact reload on next access
        self.cached_task_dir = None;
        self.ensure_artifacts();
    }

    /// The currently selected tree row.
    pub fn current_tree_row(&self) -> Option<&TreeRow> {
        self.tree_rows.get(self.tree_cursor)
    }

    /// Get the selected repo index (from whichever row is selected).
    pub fn selected_repo_index(&self) -> Option<usize> {
        match self.current_tree_row()? {
            TreeRow::Repo(ri) => Some(*ri),
            TreeRow::Task(ri, _) => Some(*ri),
        }
    }

    pub fn current_repo(&self) -> Option<&RepoData> {
        self.selected_repo_index()
            .and_then(|ri| self.repos.get(ri))
    }

    /// Get the selected task (only if a task row is selected).
    pub fn current_task(&self) -> Option<&crate::data::task::TaskState> {
        match self.current_tree_row()? {
            TreeRow::Task(ri, ti) => self.repos.get(*ri)?.tasks.get(*ti).map(|(_, t)| t),
            TreeRow::Repo(_) => None,
        }
    }

    pub fn current_issue(&self) -> Option<&crate::data::beads::BeadsIssue> {
        self.current_repo()
            .and_then(|r| r.issues.get(self.selected_issue))
    }

    // Tree navigation
    pub fn tree_down(&mut self) {
        if !self.tree_rows.is_empty() {
            self.tree_cursor = (self.tree_cursor + 1) % self.tree_rows.len();
            self.detail_scroll = 0;
            self.detail_mode = DetailMode::Overview;
            self.ensure_artifacts();
        }
    }

    pub fn tree_up(&mut self) {
        if !self.tree_rows.is_empty() {
            self.tree_cursor = if self.tree_cursor == 0 {
                self.tree_rows.len() - 1
            } else {
                self.tree_cursor - 1
            };
            self.detail_scroll = 0;
            self.detail_mode = DetailMode::Overview;
            self.ensure_artifacts();
        }
    }

    /// Toggle expand/collapse on a repo row, or select a task row.
    pub fn tree_toggle(&mut self) {
        if let Some(row) = self.tree_rows.get(self.tree_cursor).cloned() {
            match row {
                TreeRow::Repo(ri) => {
                    if self.expanded_repos.contains(&ri) {
                        self.expanded_repos.remove(&ri);
                    } else {
                        self.expanded_repos.insert(ri);
                    }
                    self.rebuild_tree();
                }
                TreeRow::Task(_, _) => {
                    // Task row: toggle is a no-op (already selected for detail view)
                }
            }
        }
    }

    // Item navigation for beads view
    pub fn next_item(&mut self) {
        match self.active_view {
            ActiveView::Tasks => self.tree_down(),
            ActiveView::BeadsIssues => {
                if let Some(repo) = self.current_repo() {
                    if !repo.issues.is_empty() {
                        self.selected_issue = (self.selected_issue + 1) % repo.issues.len();
                        self.detail_scroll = 0;
                    }
                }
            }
            _ => {}
        }
    }

    pub fn prev_item(&mut self) {
        match self.active_view {
            ActiveView::Tasks => self.tree_up(),
            ActiveView::BeadsIssues => {
                if let Some(repo) = self.current_repo() {
                    if !repo.issues.is_empty() {
                        self.selected_issue = if self.selected_issue == 0 {
                            repo.issues.len() - 1
                        } else {
                            self.selected_issue - 1
                        };
                        self.detail_scroll = 0;
                    }
                }
            }
            _ => {}
        }
    }

    pub fn toggle_focus(&mut self) {
        self.focus_pane = match self.focus_pane {
            FocusPane::Left => FocusPane::Right,
            FocusPane::Right => FocusPane::Left,
        };
    }

    pub fn next_view(&mut self) {
        self.active_view = match self.active_view {
            ActiveView::Tasks => ActiveView::BeadsIssues,
            ActiveView::BeadsIssues => ActiveView::Config,
            ActiveView::Config => ActiveView::CostSummary,
            ActiveView::CostSummary => ActiveView::Tasks,
        };
        self.detail_scroll = 0;
    }

    pub fn set_view(&mut self, view: ActiveView) {
        self.active_view = view;
        self.detail_scroll = 0;
    }

    pub fn scroll_detail_down(&mut self) {
        self.detail_scroll = self.detail_scroll.saturating_add(1);
    }

    pub fn scroll_detail_up(&mut self) {
        self.detail_scroll = self.detail_scroll.saturating_sub(1);
    }

    fn clamp_issue_selection(&mut self) {
        if let Some(repo) = self.current_repo() {
            if self.selected_issue >= repo.issues.len() && !repo.issues.is_empty() {
                self.selected_issue = repo.issues.len() - 1;
            }
        }
    }

    /// Get the task directory for the currently selected task.
    pub fn current_task_dir(&self) -> Option<&PathBuf> {
        match self.current_tree_row()? {
            TreeRow::Task(ri, ti) => self.repos.get(*ri)?.tasks.get(*ti).map(|(dir, _)| dir),
            TreeRow::Repo(_) => None,
        }
    }

    /// Load/refresh artifacts for the currently selected task.
    fn ensure_artifacts(&mut self) {
        let task_dir = match self.current_task_dir() {
            Some(d) => d.clone(),
            None => {
                self.cached_artifacts.clear();
                self.cached_task_dir = None;
                return;
            }
        };
        // Only reload if task changed
        if self.cached_task_dir.as_ref() != Some(&task_dir) {
            self.cached_artifacts = task::load_artifacts(&task_dir);
            self.cached_task_dir = Some(task_dir);
        }
    }

    /// Enter document list mode (press 'd' on a task).
    pub fn enter_doc_list(&mut self) {
        if self.current_task().is_none() {
            return;
        }
        self.ensure_artifacts();
        if self.cached_artifacts.is_empty() {
            return;
        }
        self.detail_mode = DetailMode::DocList { cursor: 0 };
        self.detail_scroll = 0;
    }

    /// Enter history view (press 'h' on a task).
    pub fn enter_history(&mut self) {
        if self.current_task().is_none() {
            return;
        }
        self.detail_mode = DetailMode::History;
        self.detail_scroll = 0;
    }

    /// Go back from doc reader/list/history to overview.
    pub fn detail_back(&mut self) {
        match &self.detail_mode {
            DetailMode::DocReader { .. } => {
                // Back to doc list
                self.detail_mode = DetailMode::DocList { cursor: 0 };
                self.detail_scroll = 0;
            }
            DetailMode::DocList { .. } | DetailMode::History => {
                self.detail_mode = DetailMode::Overview;
                self.detail_scroll = 0;
            }
            DetailMode::Overview => {}
        }
    }

    /// Navigate down within the detail pane (doc list).
    pub fn detail_nav_down(&mut self) {
        if let DetailMode::DocList { cursor } = &mut self.detail_mode {
            if *cursor + 1 < self.cached_artifacts.len() {
                *cursor += 1;
            }
        }
    }

    /// Navigate up within the detail pane (doc list).
    pub fn detail_nav_up(&mut self) {
        if let DetailMode::DocList { cursor } = &mut self.detail_mode {
            if *cursor > 0 {
                *cursor -= 1;
            }
        }
    }

    /// Open the selected document for reading.
    pub fn detail_open_doc(&mut self) {
        if let DetailMode::DocList { cursor } = self.detail_mode {
            if cursor < self.cached_artifacts.len() {
                let artifact = &self.cached_artifacts[cursor];
                let content = std::fs::read_to_string(&artifact.path)
                    .unwrap_or_else(|e| format!("Error reading file: {}", e));
                self.detail_mode = DetailMode::DocReader {
                    artifact_index: cursor,
                    content,
                };
                self.detail_scroll = 0;
            }
        }
    }

    /// Open the launch popup for the currently selected task/repo.
    pub fn open_launch_popup(&mut self) {
        // Determine work directory, task_id, task_desc
        let (work_dir, task_id, task_desc) = match self.current_tree_row() {
            Some(TreeRow::Task(ri, ti)) => {
                let repo = &self.repos[*ri];
                let (id, task) = &repo.tasks[*ti];
                // Use worktree abs path from launch info, then relative path, then repo root
                let dir = task
                    .worktree
                    .as_ref()
                    .and_then(|wt| {
                        // Prefer absolute path from launch info
                        if let Some(ref launch) = wt.launch {
                            if !launch.worktree_abs_path.is_empty() {
                                return Some(PathBuf::from(&launch.worktree_abs_path));
                            }
                        }
                        // Fall back to relative path resolved against repo root
                        if !wt.path.is_empty() {
                            let p = PathBuf::from(&wt.path);
                            if p.is_absolute() {
                                Some(p)
                            } else {
                                Some(repo.path.join(&p))
                            }
                        } else {
                            None
                        }
                    })
                    .unwrap_or_else(|| repo.path.clone());
                (dir, id.to_string_lossy().to_string(), task.description.clone())
            }
            Some(TreeRow::Repo(ri)) => {
                let repo = &self.repos[*ri];
                (repo.path.clone(), repo.name.clone(), String::new())
            }
            None => return,
        };

        let terminals = launcher::detect_terminals();
        let hosts = launcher::detect_ai_hosts();

        self.launch_popup = Some(LaunchPopup {
            terminals,
            hosts,
            step: LaunchStep::SelectTerminal,
            terminal_cursor: 0,
            host_cursor: 0,
            work_dir,
            task_id,
            task_desc,
            result_msg: None,
        });
    }

    /// Navigate up in the popup.
    pub fn popup_up(&mut self) {
        if let Some(popup) = &mut self.launch_popup {
            match popup.step {
                LaunchStep::SelectTerminal => {
                    if popup.terminal_cursor > 0 {
                        popup.terminal_cursor -= 1;
                    }
                }
                LaunchStep::SelectHost => {
                    if popup.host_cursor > 0 {
                        popup.host_cursor -= 1;
                    }
                }
                LaunchStep::Done => {}
            }
        }
    }

    /// Navigate down in the popup.
    pub fn popup_down(&mut self) {
        if let Some(popup) = &mut self.launch_popup {
            match popup.step {
                LaunchStep::SelectTerminal => {
                    if popup.terminal_cursor + 1 < popup.terminals.len() {
                        popup.terminal_cursor += 1;
                    }
                }
                LaunchStep::SelectHost => {
                    if popup.host_cursor + 1 < popup.hosts.len() {
                        popup.host_cursor += 1;
                    }
                }
                LaunchStep::Done => {}
            }
        }
    }

    /// Confirm current popup selection.
    pub fn popup_confirm(&mut self) {
        let popup = match &mut self.launch_popup {
            Some(p) => p,
            None => return,
        };
        match popup.step {
            LaunchStep::SelectTerminal => {
                popup.step = LaunchStep::SelectHost;
            }
            LaunchStep::SelectHost => {
                let terminal = popup.terminals[popup.terminal_cursor];
                let host = popup.hosts[popup.host_cursor];
                let result = launcher::launch(
                    terminal,
                    host,
                    &popup.work_dir,
                    &popup.task_id,
                    &popup.task_desc,
                );
                popup.result_msg = Some(match result {
                    Ok(()) => format!("Launched {} in {}", host.label(), terminal.label()),
                    Err(e) => format!("Error: {}", e),
                });
                popup.step = LaunchStep::Done;
            }
            LaunchStep::Done => {
                self.launch_popup = None;
            }
        }
    }

    /// Close the launch popup.
    pub fn close_launch_popup(&mut self) {
        self.launch_popup = None;
    }
}
