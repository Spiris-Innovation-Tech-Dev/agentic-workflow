use std::path::{Path, PathBuf};
use std::process::Command;

/// Information about a single worktree candidate for cleanup.
/// NOTE: Cleanup only removes the git worktree directory and optionally the branch.
/// It NEVER deletes anything in the .tasks/ directory — all task artifacts are preserved.
#[derive(Clone, Debug)]
#[allow(dead_code)]
pub struct WorktreeCandidate {
    pub task_id: String,
    pub description: String,
    pub branch: String,
    pub base_branch: String,
    pub worktree_path: String,
    pub worktree_abs: Option<String>,
    pub status: String,
    pub color_scheme_index: usize,
    pub is_complete: bool,
    pub has_unmerged: bool,
    pub disk_size: Option<u64>,
    pub phase: Option<String>,
}

/// What the cleanup will do for one worktree.
#[derive(Clone, Debug)]
pub struct CleanupAction {
    pub task_id: String,
    pub commands: Vec<String>,
    pub warnings: Vec<String>,
}

/// Result of a single cleanup execution.
#[derive(Clone, Debug)]
pub struct CleanupResult {
    pub task_id: String,
    pub success: bool,
    pub message: String,
}

/// List all worktrees that are candidates for cleanup.
/// Candidates have worktree.status == "active" (exclude "cleaned" and "recyclable").
pub fn list_cleanup_candidates(repo_path: &Path) -> Vec<WorktreeCandidate> {
    let tasks_dir = repo_path.join(".tasks");
    let resolved = if tasks_dir.is_symlink() {
        std::fs::read_link(&tasks_dir)
            .ok()
            .map(|t| if t.is_absolute() { t } else { repo_path.join(t) })
            .and_then(|p| p.canonicalize().ok())
            .unwrap_or_else(|| tasks_dir.clone())
    } else {
        tasks_dir.clone()
    };

    let tasks = crate::data::task::load_tasks(&resolved);
    let mut candidates = Vec::new();

    for loaded in &tasks {
        if loaded.archived {
            continue;
        }
        let task = &loaded.state;
        let wt = match &task.worktree {
            Some(wt) if wt.status == "active" => wt,
            _ => continue,
        };

        let wt_abs = resolve_worktree_abs(repo_path, wt);
        let disk_size = wt_abs.as_ref().and_then(|p| dir_size(Path::new(p)));
        let has_unmerged =
            !wt.branch.is_empty() && check_unmerged(repo_path, &wt.branch, &wt.base_branch);

        candidates.push(WorktreeCandidate {
            task_id: task.task_id.clone(),
            description: task.description.clone(),
            branch: wt.branch.clone(),
            base_branch: wt.base_branch.clone(),
            worktree_path: wt.path.clone(),
            worktree_abs: wt_abs,
            status: wt.status.clone(),
            color_scheme_index: wt.color_scheme_index,
            is_complete: task.is_complete(),
            has_unmerged,
            disk_size,
            phase: task.phase.clone(),
        });
    }

    candidates.sort_by(|a, b| a.task_id.cmp(&b.task_id));
    candidates
}

fn resolve_worktree_abs(
    repo_path: &Path,
    wt: &crate::data::task::WorktreeInfo,
) -> Option<String> {
    if let Some(ref launch) = wt.launch {
        if !launch.worktree_abs_path.is_empty() {
            return Some(launch.worktree_abs_path.clone());
        }
    }
    if !wt.path.is_empty() {
        let p = PathBuf::from(&wt.path);
        let abs = if p.is_absolute() { p } else { repo_path.join(&p) };
        return abs
            .canonicalize()
            .ok()
            .map(|p| p.to_string_lossy().to_string());
    }
    None
}

/// Check if branch has commits not in base_branch.
fn check_unmerged(repo_path: &Path, branch: &str, base: &str) -> bool {
    if base.is_empty() {
        return false;
    }
    let output = Command::new("git")
        .args(["log", "--oneline", &format!("{}..{}", base, branch)])
        .current_dir(repo_path)
        .output();
    match output {
        Ok(o) if o.status.success() => {
            let text = String::from_utf8_lossy(&o.stdout);
            !text.trim().is_empty()
        }
        _ => false,
    }
}

/// Get total size of directory in bytes (best-effort).
fn dir_size(path: &Path) -> Option<u64> {
    let output = Command::new("du")
        .args(["-sb", &path.to_string_lossy()])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let text = String::from_utf8_lossy(&output.stdout);
    text.split_whitespace().next()?.parse().ok()
}

/// Generate a dry-run preview of what cleanup will do for selected worktrees.
pub fn preview_cleanup(
    _repo_path: &Path,
    candidates: &[&WorktreeCandidate],
    remove_branch: bool,
    keep_on_disk: bool,
) -> Vec<CleanupAction> {
    candidates
        .iter()
        .map(|c| {
            let mut commands = Vec::new();
            let mut warnings = Vec::new();

            if !keep_on_disk {
                let abs = c.worktree_abs.as_deref().unwrap_or(&c.worktree_path);
                commands.push(format!("git worktree remove {}", abs));
            }
            if remove_branch && !c.branch.is_empty() {
                commands.push(format!("git branch -d {}", c.branch));
            }
            if keep_on_disk {
                commands.push("state.json: worktree.status = \"recyclable\"".to_string());
            } else {
                commands.push("state.json: worktree.status = \"cleaned\"".to_string());
            }

            if c.has_unmerged {
                warnings.push(format!(
                    "Branch '{}' has unmerged commits into '{}'",
                    c.branch, c.base_branch
                ));
            }
            if !c.is_complete {
                let phase = c.phase.as_deref().unwrap_or("unknown");
                warnings.push(format!("Workflow not complete (current phase: {})", phase));
            }

            CleanupAction {
                task_id: c.task_id.clone(),
                commands,
                warnings,
            }
        })
        .collect()
}

/// Execute cleanup for multiple worktrees. Runs synchronously.
/// Shells out to scripts/cleanup-worktree.py for each task.
/// IMPORTANT: This only removes the git worktree and branch. It NEVER deletes .tasks/ data.
pub fn execute_cleanup(
    repo_path: &Path,
    task_ids: &[String],
    remove_branch: bool,
    keep_on_disk: bool,
) -> Vec<CleanupResult> {
    let script = repo_path
        .join("scripts")
        .join("cleanup-worktree.py");
    let script_path = if script.exists() {
        script.to_string_lossy().to_string()
    } else {
        "scripts/cleanup-worktree.py".to_string()
    };

    task_ids
        .iter()
        .map(|task_id| {
            let mut args = vec![
                "python3".to_string(),
                script_path.clone(),
                task_id.clone(),
            ];
            if keep_on_disk {
                args.push("--keep-on-disk".to_string());
            }
            if remove_branch {
                args.push("--remove-branch".to_string());
            }

            let result = Command::new(&args[0])
                .args(&args[1..])
                .current_dir(repo_path)
                .output();

            match result {
                Ok(output) => {
                    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
                    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
                    if output.status.success() {
                        CleanupResult {
                            task_id: task_id.clone(),
                            success: true,
                            message: stdout.trim().to_string(),
                        }
                    } else {
                        CleanupResult {
                            task_id: task_id.clone(),
                            success: false,
                            message: format!("Failed: {}", stderr.trim()),
                        }
                    }
                }
                Err(e) => CleanupResult {
                    task_id: task_id.clone(),
                    success: false,
                    message: format!("Failed to run cleanup script: {}", e),
                },
            }
        })
        .collect()
}
