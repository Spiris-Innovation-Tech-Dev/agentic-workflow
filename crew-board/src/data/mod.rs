pub mod beads;
pub mod config;
pub mod task;

use std::path::{Path, PathBuf};

/// All data loaded from a single repository.
#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct RepoData {
    pub name: String,
    pub path: PathBuf,
    pub tasks: Vec<(PathBuf, task::TaskState)>,
    pub issues: Vec<beads::BeadsIssue>,
    pub config_cascade: Vec<config::ConfigLevel>,
}

impl RepoData {
    /// Load all data from a repo directory.
    pub fn load(repo_path: &Path) -> Self {
        let name = repo_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| "unknown".to_string());

        let tasks_dir = repo_path.join(".tasks");
        let beads_dir = repo_path.join(".beads");

        // Resolve symlinks for .tasks/ (worktrees use symlinks)
        let resolved_tasks = if tasks_dir.is_symlink() {
            match std::fs::read_link(&tasks_dir) {
                Ok(target) => {
                    let resolved = if target.is_absolute() {
                        target
                    } else {
                        repo_path.join(target)
                    };
                    resolved.canonicalize().unwrap_or(resolved)
                }
                Err(_) => tasks_dir.clone(),
            }
        } else {
            tasks_dir.clone()
        };

        RepoData {
            name,
            path: repo_path.to_path_buf(),
            tasks: task::load_tasks(&resolved_tasks),
            issues: beads::load_issues(&beads_dir),
            config_cascade: config::load_config_cascade(repo_path),
        }
    }

    pub fn open_issue_count(&self) -> usize {
        self.issues.iter().filter(|i| i.status == "open").count()
    }

    #[allow(dead_code)]
    pub fn in_progress_issue_count(&self) -> usize {
        self.issues
            .iter()
            .filter(|i| i.status == "in_progress")
            .count()
    }

    pub fn active_task_count(&self) -> usize {
        self.tasks.iter().filter(|(_, t)| !t.is_complete()).count()
    }
}
