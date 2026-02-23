use crate::cleanup;
use crate::data::task::{self, Discovery, Interaction, TaskArtifact};
use crate::data::RepoData;
use crate::launcher::{self, AiHost, TerminalEnv};
use crate::worktree;
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use tui_input::Input;

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

/// Steps in the create worktree popup flow.
#[derive(PartialEq)]
pub enum CreateStep {
    InputDescription,
    SelectHost,
    ToggleSettings,
    Confirm,
    Executing,
    Done,
}

/// State for the "new worktree" popup.
pub struct CreateWorktreePopup {
    pub step: CreateStep,
    pub description_input: Input,
    pub hosts: Vec<AiHost>,
    pub host_cursor: usize,
    pub pull: bool,
    pub launch_after: bool,
    pub settings_cursor: usize,
    pub repo_path: PathBuf,
    pub repo_name: String,
    pub preview: Option<worktree::WorktreePreview>,
    pub handle: Option<std::thread::JoinHandle<Result<worktree::WorktreeResult, String>>>,
    pub started_at: Option<std::time::Instant>,
    pub result: Option<Result<worktree::WorktreeResult, String>>,
}

/// Steps in the cleanup worktree popup flow.
#[derive(PartialEq)]
pub enum CleanupStep {
    /// Select worktrees to clean up (multi-select with checkboxes)
    SelectWorktrees,
    /// Toggle cleanup settings (remove branch, keep on disk)
    Settings,
    /// Dry-run preview showing all actions + warnings
    Preview,
    /// Executing cleanup (background thread)
    Executing,
    /// Done: show results
    Done,
}

/// State for the F6 cleanup worktree popup.
pub struct CleanupPopup {
    pub step: CleanupStep,
    pub repo_path: PathBuf,
    pub repo_name: String,
    pub candidates: Vec<cleanup::WorktreeCandidate>,
    pub selected: HashSet<usize>,
    pub cursor: usize,
    pub remove_branch: bool,
    pub keep_on_disk: bool,
    pub settings_cursor: usize,
    pub preview: Vec<cleanup::CleanupAction>,
    pub handle: Option<std::thread::JoinHandle<Vec<cleanup::CleanupResult>>>,
    pub started_at: Option<std::time::Instant>,
    pub results: Option<Vec<cleanup::CleanupResult>>,
    pub scroll: u16,
}

/// A single search hit linking back to a specific task.
pub struct SearchResult {
    pub repo_index: usize,
    pub task_index: usize,
    pub task_id: String,
    pub description: String,
    pub match_source: String, // "description", "architect.md", "linked_issue", etc.
}

/// State for the `/` search popup.
pub struct SearchPopup {
    pub input: Input,
    pub results: Vec<SearchResult>,
    pub cursor: usize,
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
    pub show_help: bool,
    pub last_refresh: std::time::Instant,
    pub detail_scroll: u16,

    // Detail pane state
    pub detail_mode: DetailMode,
    pub cached_artifacts: Vec<TaskArtifact>,
    pub cached_task_dir: Option<PathBuf>,
    pub cached_interactions: Vec<Interaction>,
    pub cached_discoveries: Vec<Discovery>,
    pub cached_history_task_dir: Option<PathBuf>,

    // Launch popup
    pub launch_popup: Option<LaunchPopup>,

    // Create worktree popup
    pub create_popup: Option<CreateWorktreePopup>,

    // Search popup
    pub search_popup: Option<SearchPopup>,

    // Cleanup worktree popup
    pub cleanup_popup: Option<CleanupPopup>,
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
            show_help: false,
            last_refresh: std::time::Instant::now(),
            detail_scroll: 0,
            detail_mode: DetailMode::Overview,
            cached_artifacts: Vec::new(),
            cached_task_dir: None,
            cached_interactions: Vec::new(),
            cached_discoveries: Vec::new(),
            cached_history_task_dir: None,
            launch_popup: None,
            create_popup: None,
            search_popup: None,
            cleanup_popup: None,
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
        self.cached_history_task_dir = None;
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

    /// Get the selected loaded task (only if a task row is selected).
    pub fn current_loaded_task(&self) -> Option<&crate::data::task::LoadedTask> {
        match self.current_tree_row()? {
            TreeRow::Task(ri, ti) => self.repos.get(*ri)?.tasks.get(*ti),
            TreeRow::Repo(_) => None,
        }
    }

    /// Get the selected task state (only if a task row is selected).
    pub fn current_task(&self) -> Option<&crate::data::task::TaskState> {
        self.current_loaded_task().map(|lt| &lt.state)
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
        self.current_loaded_task().map(|lt| &lt.dir)
    }

    /// Load/refresh artifacts for the currently selected task.
    fn ensure_artifacts(&mut self) {
        let loaded = match self.current_loaded_task() {
            Some(lt) => lt,
            None => {
                self.cached_artifacts.clear();
                self.cached_task_dir = None;
                return;
            }
        };
        // Archived tasks have no artifacts on disk
        if loaded.archived {
            self.cached_artifacts.clear();
            self.cached_task_dir = None;
            return;
        }
        let task_dir = loaded.dir.clone();
        // Only reload if task changed
        if self.cached_task_dir.as_ref() != Some(&task_dir) {
            self.cached_artifacts = task::load_artifacts(&task_dir);
            self.cached_task_dir = Some(task_dir);
        }
    }

    /// Enter document list mode (press 'd' on a task).
    pub fn enter_doc_list(&mut self) {
        match self.current_loaded_task() {
            Some(lt) if !lt.archived => {}
            _ => return,
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
        match self.current_loaded_task() {
            Some(lt) if !lt.archived => {}
            _ => return,
        }
        self.ensure_history_data();
        self.detail_mode = DetailMode::History;
        self.detail_scroll = 0;
    }

    /// Load interactions and discoveries for the current task (lazy, cached).
    fn ensure_history_data(&mut self) {
        let task_dir = match self.current_task_dir() {
            Some(d) => d.clone(),
            None => {
                self.cached_interactions.clear();
                self.cached_discoveries.clear();
                self.cached_history_task_dir = None;
                return;
            }
        };
        if self.cached_history_task_dir.as_ref() != Some(&task_dir) {
            self.cached_interactions = task::load_interactions(&task_dir);
            self.cached_discoveries = task::load_discoveries(&task_dir);
            self.cached_history_task_dir = Some(task_dir);
        }
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
                let loaded = &repo.tasks[*ti];
                // Skip launch for archived tasks
                if loaded.archived {
                    return;
                }
                let task = &loaded.state;
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
                (dir, loaded.dir.to_string_lossy().to_string(), task.description.clone())
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
                    None,
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

    // ── Create Worktree Popup ──────────────────────────────────────────

    /// Open the create worktree popup (only on Repo rows).
    pub fn open_create_popup(&mut self) {
        let (repo_path, repo_name) = match self.current_tree_row() {
            Some(TreeRow::Repo(ri)) => {
                let repo = &self.repos[*ri];
                (repo.path.clone(), repo.name.clone())
            }
            _ => return, // Only on repo rows
        };

        let hosts = launcher::detect_ai_hosts();

        self.create_popup = Some(CreateWorktreePopup {
            step: CreateStep::InputDescription,
            description_input: Input::default(),
            hosts,
            host_cursor: 0,
            pull: true,
            launch_after: true,
            settings_cursor: 0,
            repo_path,
            repo_name,
            preview: None,
            handle: None,
            started_at: None,
            result: None,
        });
    }

    /// Handle a key event for the create popup. Returns true if the key was consumed.
    pub fn create_popup_handle_key(&mut self, key: crossterm::event::KeyEvent) -> bool {
        use crossterm::event::KeyCode;

        let popup = match &mut self.create_popup {
            Some(p) => p,
            None => return false,
        };

        match popup.step {
            CreateStep::InputDescription => match key.code {
                KeyCode::Esc => {
                    self.create_popup = None;
                }
                KeyCode::Enter => {
                    let desc = popup.description_input.value().trim().to_string();
                    if !desc.is_empty() {
                        popup.step = CreateStep::SelectHost;
                    }
                }
                _ => {
                    use tui_input::backend::crossterm::EventHandler;
                    popup.description_input.handle_event(
                        &crossterm::event::Event::Key(key),
                    );
                }
            },
            CreateStep::SelectHost => match key.code {
                KeyCode::Esc => {
                    self.create_popup = None;
                }
                KeyCode::Up | KeyCode::Char('k') => {
                    if let Some(p) = &mut self.create_popup {
                        if p.host_cursor > 0 {
                            p.host_cursor -= 1;
                        }
                    }
                }
                KeyCode::Down | KeyCode::Char('j') => {
                    if let Some(p) = &mut self.create_popup {
                        if p.host_cursor + 1 < p.hosts.len() {
                            p.host_cursor += 1;
                        }
                    }
                }
                KeyCode::Enter => {
                    popup.step = CreateStep::ToggleSettings;
                }
                _ => {}
            },
            CreateStep::ToggleSettings => match key.code {
                KeyCode::Esc => {
                    self.create_popup = None;
                }
                KeyCode::Up | KeyCode::Char('k') => {
                    if let Some(p) = &mut self.create_popup {
                        if p.settings_cursor > 0 {
                            p.settings_cursor -= 1;
                        }
                    }
                }
                KeyCode::Down | KeyCode::Char('j') => {
                    if let Some(p) = &mut self.create_popup {
                        if p.settings_cursor < 1 {
                            p.settings_cursor += 1;
                        }
                    }
                }
                KeyCode::Char(' ') => {
                    if let Some(p) = &mut self.create_popup {
                        match p.settings_cursor {
                            0 => p.pull = !p.pull,
                            1 => p.launch_after = !p.launch_after,
                            _ => {}
                        }
                    }
                }
                KeyCode::Enter => {
                    self.compute_preview();
                }
                _ => {}
            },
            CreateStep::Confirm => match key.code {
                KeyCode::Esc => {
                    self.create_popup = None;
                }
                KeyCode::Enter => {
                    self.start_create_worktree();
                }
                _ => {}
            },
            CreateStep::Executing => {
                // No keys during execution
            }
            CreateStep::Done => match key.code {
                KeyCode::Esc => {
                    self.close_create_popup();
                }
                KeyCode::Enter => {
                    self.create_popup_launch_and_close();
                }
                _ => {}
            },
        }
        true
    }

    /// Compute and display the preview before executing.
    fn compute_preview(&mut self) {
        let popup = match &mut self.create_popup {
            Some(p) => p,
            None => return,
        };
        let desc = popup.description_input.value().trim().to_string();
        match worktree::preview(&popup.repo_path, &desc) {
            Ok(pv) => {
                popup.preview = Some(pv);
                popup.step = CreateStep::Confirm;
            }
            Err(e) => {
                // Show error in Done step
                popup.result = Some(Err(e));
                popup.step = CreateStep::Done;
            }
        }
    }

    /// Start the background worktree creation.
    fn start_create_worktree(&mut self) {
        let popup = match &mut self.create_popup {
            Some(p) => p,
            None => return,
        };

        let description = popup.description_input.value().trim().to_string();
        let repo_path = popup.repo_path.clone();
        let ai_host = popup.hosts[popup.host_cursor];
        let pull = popup.pull;

        popup.step = CreateStep::Executing;
        popup.started_at = Some(std::time::Instant::now());

        popup.handle = Some(std::thread::spawn(move || {
            worktree::create_worktree(&repo_path, &description, ai_host, pull)
        }));
    }

    /// Poll for background worktree creation completion (call each tick).
    pub fn create_popup_check_completion(&mut self) {
        let popup = match &mut self.create_popup {
            Some(p) if p.step == CreateStep::Executing => p,
            _ => return,
        };

        let handle = match popup.handle.take() {
            Some(h) => h,
            None => return,
        };

        if handle.is_finished() {
            popup.result = Some(
                handle
                    .join()
                    .unwrap_or_else(|_| Err("Thread panicked".to_string())),
            );
            popup.step = CreateStep::Done;
        } else {
            // Put it back
            popup.handle = Some(handle);
        }
    }

    /// On Enter in Done step: launch terminal if configured, then close.
    fn create_popup_launch_and_close(&mut self) {
        let popup = match &self.create_popup {
            Some(p) => p,
            None => return,
        };

        if popup.launch_after {
            if let Some(Ok(ref result)) = popup.result {
                let terminals = launcher::detect_terminals();
                if let Some(&terminal) = terminals.first() {
                    let host = popup.hosts[popup.host_cursor];
                    let cs = launcher::get_hex_scheme(result.color_scheme_index);
                    let _ = launcher::launch(
                        terminal,
                        host,
                        &result.worktree_abs,
                        &result.task_id,
                        "",
                        Some(cs),
                    );
                }
            }
        }
        self.create_popup = None;
        self.refresh(); // Reload to show new task
    }

    /// Close the create popup without launching.
    pub fn close_create_popup(&mut self) {
        let should_refresh = self
            .create_popup
            .as_ref()
            .is_some_and(|p| p.result.as_ref().is_some_and(|r| r.is_ok()));
        self.create_popup = None;
        if should_refresh {
            self.refresh();
        }
    }

    // ── Search Popup ─────────────────────────────────────────────────────

    /// Open the search popup.
    pub fn open_search(&mut self) {
        self.search_popup = Some(SearchPopup {
            input: Input::default(),
            results: Vec::new(),
            cursor: 0,
        });
    }

    /// Handle a key event for the search popup. Returns true if consumed.
    pub fn search_handle_key(&mut self, key: crossterm::event::KeyEvent) -> bool {
        use crossterm::event::KeyCode;

        let popup = match &mut self.search_popup {
            Some(p) => p,
            None => return false,
        };

        match key.code {
            KeyCode::Esc => {
                self.search_popup = None;
            }
            KeyCode::Enter => {
                self.search_navigate();
            }
            KeyCode::Up => {
                if popup.cursor > 0 {
                    popup.cursor -= 1;
                }
            }
            KeyCode::Down => {
                if !popup.results.is_empty() && popup.cursor + 1 < popup.results.len() {
                    popup.cursor += 1;
                }
            }
            _ => {
                // Forward to tui_input for text editing
                use tui_input::backend::crossterm::EventHandler;
                popup
                    .input
                    .handle_event(&crossterm::event::Event::Key(key));
                self.run_search();
            }
        }
        true
    }

    /// Run search across all tasks using the current query.
    fn run_search(&mut self) {
        let query = match &self.search_popup {
            Some(p) => p.input.value().to_lowercase(),
            None => return,
        };

        if query.is_empty() {
            if let Some(p) = &mut self.search_popup {
                p.results.clear();
                p.cursor = 0;
            }
            return;
        }

        const MAX_RESULTS: usize = 50;
        let mut results = Vec::new();

        for (repo_index, repo) in self.repos.iter().enumerate() {
            for (task_index, loaded) in repo.tasks.iter().enumerate() {
                if results.len() >= MAX_RESULTS {
                    break;
                }

                let task = &loaded.state;
                let task_dir = &loaded.dir;

                // Check structured fields first
                if let Some(source) = Self::match_task_fields(task, &query) {
                    results.push(SearchResult {
                        repo_index,
                        task_index,
                        task_id: task.task_id.clone(),
                        description: task.description.clone(),
                        match_source: source,
                    });
                    continue;
                }

                // Archived tasks have no files on disk to search
                if loaded.archived {
                    continue;
                }

                // Fall back: read raw state.json for extra fields
                let state_path = task_dir.join("state.json");
                if let Ok(raw) = std::fs::read_to_string(&state_path) {
                    if raw.to_lowercase().contains(&query) {
                        results.push(SearchResult {
                            repo_index,
                            task_index,
                            task_id: task.task_id.clone(),
                            description: task.description.clone(),
                            match_source: "state.json".to_string(),
                        });
                        continue;
                    }
                }

                // Fall back: scan .md artifact files (first 4KB each)
                if let Some(source) = Self::match_task_artifacts(task_dir, &query) {
                    results.push(SearchResult {
                        repo_index,
                        task_index,
                        task_id: task.task_id.clone(),
                        description: task.description.clone(),
                        match_source: source,
                    });
                }
            }
            if results.len() >= MAX_RESULTS {
                break;
            }
        }

        if let Some(p) = &mut self.search_popup {
            p.results = results;
            p.cursor = 0;
        }
    }

    /// Check structured task fields against query. Returns match source if found.
    fn match_task_fields(
        task: &crate::data::task::TaskState,
        query: &str,
    ) -> Option<String> {
        if task.task_id.to_lowercase().contains(query) {
            return Some("task_id".to_string());
        }
        if task.description.to_lowercase().contains(query) {
            return Some("description".to_string());
        }
        if let Some(ref wt) = task.worktree {
            if wt.branch.to_lowercase().contains(query) {
                return Some("branch".to_string());
            }
        }
        if let Some(ref phase) = task.phase {
            if phase.to_lowercase().contains(query) {
                return Some("phase".to_string());
            }
        }
        None
    }

    /// Scan .md files in task_dir for query match. Returns source filename if found.
    fn match_task_artifacts(task_dir: &Path, query: &str) -> Option<String> {
        let entries = std::fs::read_dir(task_dir).ok()?;
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("md") {
                continue;
            }
            // Read first 4KB
            if let Ok(file) = std::fs::File::open(&path) {
                use std::io::Read;
                let mut buf = vec![0u8; 4096];
                let mut reader = std::io::BufReader::new(file);
                let n = reader.read(&mut buf).unwrap_or(0);
                let text = String::from_utf8_lossy(&buf[..n]).to_lowercase();
                if text.contains(query) {
                    let fname = path
                        .file_name()
                        .and_then(|f| f.to_str())
                        .unwrap_or("artifact");
                    return Some(fname.to_string());
                }
            }
        }
        None
    }

    // ── Cleanup Worktree Popup ─────────────────────────────────────────

    /// Open the cleanup popup (F6). Works on repo rows and task rows (resolves to parent repo).
    pub fn open_cleanup_popup(&mut self) {
        let ri = match self.current_tree_row() {
            Some(TreeRow::Repo(ri)) => *ri,
            Some(TreeRow::Task(ri, _)) => *ri,
            None => return,
        };
        let repo = &self.repos[ri];
        let (repo_path, repo_name) = (repo.path.clone(), repo.name.clone());

        let candidates = cleanup::list_cleanup_candidates(&repo_path);

        // Pre-select completed tasks by default
        let mut selected = HashSet::new();
        for (i, c) in candidates.iter().enumerate() {
            if c.is_complete {
                selected.insert(i);
            }
        }

        self.cleanup_popup = Some(CleanupPopup {
            step: CleanupStep::SelectWorktrees,
            repo_path,
            repo_name,
            candidates,
            selected,
            cursor: 0,
            remove_branch: false,
            keep_on_disk: false,
            settings_cursor: 0,
            preview: Vec::new(),
            handle: None,
            started_at: None,
            results: None,
            scroll: 0,
        });
    }

    /// Handle a key event for the cleanup popup. Returns true if consumed.
    pub fn cleanup_popup_handle_key(&mut self, key: crossterm::event::KeyEvent) -> bool {
        use crossterm::event::KeyCode;

        if self.cleanup_popup.is_none() {
            return false;
        }

        // Get the current step to route
        let step_is = |s: &CleanupStep| -> bool {
            self.cleanup_popup.as_ref().is_some_and(|p| p.step == *s)
        };

        if step_is(&CleanupStep::SelectWorktrees) {
            match key.code {
                KeyCode::Esc => {
                    self.cleanup_popup = None;
                }
                KeyCode::Up | KeyCode::Char('k') => {
                    if let Some(p) = &mut self.cleanup_popup {
                        if p.cursor > 0 {
                            p.cursor -= 1;
                        }
                    }
                }
                KeyCode::Down | KeyCode::Char('j') => {
                    if let Some(p) = &mut self.cleanup_popup {
                        if p.cursor + 1 < p.candidates.len() {
                            p.cursor += 1;
                        }
                    }
                }
                KeyCode::Char(' ') => {
                    if let Some(p) = &mut self.cleanup_popup {
                        let idx = p.cursor;
                        if p.selected.contains(&idx) {
                            p.selected.remove(&idx);
                        } else {
                            p.selected.insert(idx);
                        }
                    }
                }
                KeyCode::Char('a') => {
                    if let Some(p) = &mut self.cleanup_popup {
                        if p.selected.len() == p.candidates.len() {
                            p.selected.clear();
                        } else {
                            p.selected = (0..p.candidates.len()).collect();
                        }
                    }
                }
                KeyCode::Enter => {
                    if let Some(p) = &mut self.cleanup_popup {
                        if !p.selected.is_empty() {
                            p.step = CleanupStep::Settings;
                        }
                    }
                }
                _ => {}
            }
        } else if step_is(&CleanupStep::Settings) {
            match key.code {
                KeyCode::Esc => {
                    self.cleanup_popup = None;
                }
                KeyCode::Up | KeyCode::Char('k') => {
                    if let Some(p) = &mut self.cleanup_popup {
                        if p.settings_cursor > 0 {
                            p.settings_cursor -= 1;
                        }
                    }
                }
                KeyCode::Down | KeyCode::Char('j') => {
                    if let Some(p) = &mut self.cleanup_popup {
                        if p.settings_cursor < 1 {
                            p.settings_cursor += 1;
                        }
                    }
                }
                KeyCode::Char(' ') => {
                    if let Some(p) = &mut self.cleanup_popup {
                        match p.settings_cursor {
                            0 => p.remove_branch = !p.remove_branch,
                            1 => p.keep_on_disk = !p.keep_on_disk,
                            _ => {}
                        }
                    }
                }
                KeyCode::Enter => {
                    self.compute_cleanup_preview();
                }
                _ => {}
            }
        } else if step_is(&CleanupStep::Preview) {
            match key.code {
                KeyCode::Esc => {
                    self.cleanup_popup = None;
                }
                KeyCode::Up | KeyCode::Char('k') => {
                    if let Some(p) = &mut self.cleanup_popup {
                        p.scroll = p.scroll.saturating_sub(1);
                    }
                }
                KeyCode::Down | KeyCode::Char('j') => {
                    if let Some(p) = &mut self.cleanup_popup {
                        p.scroll = p.scroll.saturating_add(1);
                    }
                }
                KeyCode::Enter => {
                    self.start_cleanup();
                }
                _ => {}
            }
        } else if step_is(&CleanupStep::Executing) {
            // No keys during execution
        } else if step_is(&CleanupStep::Done) {
            match key.code {
                KeyCode::Esc | KeyCode::Enter => {
                    self.close_cleanup_popup();
                }
                KeyCode::Up | KeyCode::Char('k') => {
                    if let Some(p) = &mut self.cleanup_popup {
                        p.scroll = p.scroll.saturating_sub(1);
                    }
                }
                KeyCode::Down | KeyCode::Char('j') => {
                    if let Some(p) = &mut self.cleanup_popup {
                        p.scroll = p.scroll.saturating_add(1);
                    }
                }
                _ => {}
            }
        }
        true
    }

    /// Compute the dry-run preview.
    fn compute_cleanup_preview(&mut self) {
        let popup = match &mut self.cleanup_popup {
            Some(p) => p,
            None => return,
        };

        let selected_candidates: Vec<&cleanup::WorktreeCandidate> = popup
            .selected
            .iter()
            .filter_map(|&i| popup.candidates.get(i))
            .collect();

        popup.preview = cleanup::preview_cleanup(
            &popup.repo_path,
            &selected_candidates,
            popup.remove_branch,
            popup.keep_on_disk,
        );
        popup.scroll = 0;
        popup.step = CleanupStep::Preview;
    }

    /// Start the background cleanup execution.
    fn start_cleanup(&mut self) {
        let popup = match &mut self.cleanup_popup {
            Some(p) => p,
            None => return,
        };

        let task_ids: Vec<String> = popup
            .selected
            .iter()
            .filter_map(|&i| popup.candidates.get(i))
            .map(|c| c.task_id.clone())
            .collect();

        let repo_path = popup.repo_path.clone();
        let remove_branch = popup.remove_branch;
        let keep_on_disk = popup.keep_on_disk;

        popup.step = CleanupStep::Executing;
        popup.started_at = Some(std::time::Instant::now());

        popup.handle = Some(std::thread::spawn(move || {
            cleanup::execute_cleanup(&repo_path, &task_ids, remove_branch, keep_on_disk)
        }));
    }

    /// Poll for background cleanup completion (call each tick).
    pub fn cleanup_popup_check_completion(&mut self) {
        let popup = match &mut self.cleanup_popup {
            Some(p) if p.step == CleanupStep::Executing => p,
            _ => return,
        };

        let handle = match popup.handle.take() {
            Some(h) => h,
            None => return,
        };

        if handle.is_finished() {
            popup.results = Some(
                handle
                    .join()
                    .unwrap_or_else(|_| {
                        vec![cleanup::CleanupResult {
                            task_id: "?".to_string(),
                            success: false,
                            message: "Thread panicked".to_string(),
                        }]
                    }),
            );
            popup.step = CleanupStep::Done;
            popup.scroll = 0;
        } else {
            popup.handle = Some(handle);
        }
    }

    /// Close the cleanup popup and refresh data.
    pub fn close_cleanup_popup(&mut self) {
        let should_refresh = self
            .cleanup_popup
            .as_ref()
            .is_some_and(|p| p.results.is_some());
        self.cleanup_popup = None;
        if should_refresh {
            self.refresh();
        }
    }

    /// Navigate to the selected search result and close the popup.
    fn search_navigate(&mut self) {
        let (repo_index, task_index) = match &self.search_popup {
            Some(popup) if !popup.results.is_empty() => {
                let r = &popup.results[popup.cursor];
                (r.repo_index, r.task_index)
            }
            _ => return,
        };

        // Close popup first
        self.search_popup = None;

        // Switch to Tasks view
        self.active_view = ActiveView::Tasks;

        // Expand the target repo
        self.expanded_repos.insert(repo_index);
        self.rebuild_tree();

        // Find the matching TreeRow::Task position
        for (i, row) in self.tree_rows.iter().enumerate() {
            if let TreeRow::Task(ri, ti) = row {
                if *ri == repo_index && *ti == task_index {
                    self.tree_cursor = i;
                    break;
                }
            }
        }

        // Reset detail state
        self.detail_mode = DetailMode::Overview;
        self.detail_scroll = 0;
        self.focus_pane = FocusPane::Left;
        self.ensure_artifacts();
    }
}
