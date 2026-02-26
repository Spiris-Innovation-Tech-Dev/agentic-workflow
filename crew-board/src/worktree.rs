use regex::Regex;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::launcher::{AiHost, COLOR_SCHEME_HEX};

/// Preview of what will be created (shown before executing).
#[derive(Clone)]
pub struct WorktreePreview {
    pub task_id: String,
    pub branch_name: String,
    pub worktree_dir: String,
    pub base_branch: String,
    pub color_scheme_name: &'static str,
}

/// Result of a successful worktree creation.
#[allow(dead_code)]
pub struct WorktreeResult {
    pub task_id: String,
    pub branch_name: String,
    pub worktree_abs: PathBuf,
    pub base_branch: String,
    pub color_scheme_index: usize,
}

/// Scan `.tasks/` for `TASK_\d+` directories, return the next task ID.
fn get_next_task_id(tasks_dir: &Path) -> String {
    let re = Regex::new(r"^TASK_(\d+)$").unwrap();
    let mut max_num = 0u32;
    if let Ok(entries) = std::fs::read_dir(tasks_dir) {
        for entry in entries.flatten() {
            if !entry.path().is_dir() {
                continue;
            }
            if let Some(name) = entry.file_name().to_str() {
                if let Some(caps) = re.captures(name) {
                    if let Ok(num) = caps[1].parse::<u32>() {
                        max_num = max_num.max(num);
                    }
                }
            }
        }
    }
    format!("TASK_{:03}", max_num + 1)
}

/// Convert text to a git-branch-safe slug.
fn slugify(text: &str) -> String {
    let text = text.to_lowercase();
    let re_non_alnum = Regex::new(r"[^a-z0-9\s_-]").unwrap();
    let re_spaces = Regex::new(r"[\s_]+").unwrap();
    let re_dashes = Regex::new(r"-+").unwrap();

    let text = re_non_alnum.replace_all(&text, "");
    let text = re_spaces.replace_all(&text, "-");
    let text = re_dashes.replace_all(&text, "-");
    text.trim_matches('-').to_string()
}

/// Generate a branch name from the task description.
fn generate_branch_name(description: &str) -> String {
    let slug = slugify(description);
    if slug.is_empty() {
        return "crew/new-task".to_string();
    }
    // Truncate to 50 chars, trim trailing dash
    let truncated = if slug.len() > 50 { &slug[..50] } else { &slug };
    let truncated = truncated.trim_end_matches('-');
    format!("crew/{}", truncated)
}

/// Get the current git branch name.
fn get_current_branch(repo_path: &Path) -> Result<String, String> {
    let output = Command::new("git")
        .args(["branch", "--show-current"])
        .current_dir(repo_path)
        .output()
        .map_err(|e| format!("Failed to run git: {}", e))?;
    if !output.status.success() {
        return Err("Failed to detect current branch".to_string());
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

/// Fetch and pull latest from origin.
fn fetch_and_pull(repo_path: &Path, branch: &str) -> Result<(), String> {
    let fetch = Command::new("git")
        .args(["fetch", "origin"])
        .current_dir(repo_path)
        .output()
        .map_err(|e| format!("git fetch failed: {}", e))?;
    if !fetch.status.success() {
        return Err(format!(
            "git fetch failed: {}",
            String::from_utf8_lossy(&fetch.stderr)
        ));
    }
    let pull = Command::new("git")
        .args(["pull", "origin", branch])
        .current_dir(repo_path)
        .output()
        .map_err(|e| format!("git pull failed: {}", e))?;
    if !pull.status.success() {
        return Err(format!(
            "git pull failed: {}",
            String::from_utf8_lossy(&pull.stderr)
        ));
    }
    Ok(())
}

/// Create the initial state.json content.
fn create_initial_state(
    task_id: &str,
    description: &str,
    branch_name: &str,
    base_branch: &str,
    worktree_path: &str,
    color_scheme_index: usize,
    ai_host: AiHost,
) -> serde_json::Value {
    let now = chrono::Utc::now().to_rfc3339();
    let scheme = &COLOR_SCHEME_HEX[color_scheme_index % COLOR_SCHEME_HEX.len()];
    serde_json::json!({
        "task_id": task_id,
        "phase": "architect",
        "phases_completed": [],
        "review_issues": [],
        "iteration": 1,
        "docs_needed": [],
        "implementation_progress": {
            "total_steps": 0,
            "current_step": 0,
            "steps_completed": []
        },
        "human_decisions": [],
        "concerns": [],
        "description": description,
        "worktree": {
            "status": "active",
            "path": worktree_path,
            "branch": branch_name,
            "base_branch": base_branch,
            "color_scheme_index": color_scheme_index,
            "created_at": now,
            "launch": {
                "ai_host": ai_host.label(),
                "color_scheme": scheme.name
            }
        },
        "created_at": now,
        "updated_at": now
    })
}

/// Compute a preview of what will be created, without touching disk.
pub fn preview(repo_path: &Path, description: &str) -> Result<WorktreePreview, String> {
    let git_dir = repo_path.join(".git");
    if !git_dir.is_dir() {
        if git_dir.is_file() {
            return Err("Already inside a worktree".to_string());
        }
        return Err("Not a git repository".to_string());
    }

    let tasks_dir = repo_path.join(".tasks");
    let tasks_canonical = if tasks_dir.exists() {
        tasks_dir.canonicalize().unwrap_or_else(|_| tasks_dir.clone())
    } else {
        tasks_dir
    };

    let task_id = get_next_task_id(&tasks_canonical);
    let branch_name = generate_branch_name(description);
    let base_branch = get_current_branch(repo_path).unwrap_or_else(|_| "main".to_string());

    let repo_name = repo_path
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "repo".to_string());
    let worktree_dir = format!("../{}-worktrees/{}", repo_name, task_id);

    let task_num: usize = task_id
        .strip_prefix("TASK_")
        .and_then(|s| s.parse().ok())
        .unwrap_or(0);
    let scheme_idx = task_num % COLOR_SCHEME_HEX.len();
    let color_scheme_name = COLOR_SCHEME_HEX[scheme_idx].name;

    Ok(WorktreePreview {
        task_id,
        branch_name,
        worktree_dir,
        base_branch,
        color_scheme_name,
    })
}

/// Create a worktree for the given repository.
///
/// This runs git operations synchronously — call from a background thread.
pub fn create_worktree(
    repo_path: &Path,
    description: &str,
    ai_host: AiHost,
    pull: bool,
) -> Result<WorktreeResult, String> {
    // Validate this is a main repo (not already a worktree)
    let git_dir = repo_path.join(".git");
    if !git_dir.is_dir() {
        if git_dir.is_file() {
            return Err("Already inside a worktree. Create from the main repo.".to_string());
        }
        return Err("Not a git repository".to_string());
    }

    // Detect base branch
    let base_branch = get_current_branch(repo_path)?;
    if base_branch.is_empty() {
        return Err("Could not detect current branch".to_string());
    }

    // Fetch + pull if requested
    if pull {
        fetch_and_pull(repo_path, &base_branch)?;
    }

    // Find .tasks directory
    let tasks_dir = repo_path.join(".tasks");
    if !tasks_dir.exists() {
        std::fs::create_dir_all(&tasks_dir)
            .map_err(|e| format!("Failed to create .tasks/: {}", e))?;
    }

    // Resolve tasks_dir to canonical path (follows symlinks)
    let tasks_canonical = tasks_dir.canonicalize().unwrap_or_else(|_| tasks_dir.clone());

    // Generate task ID
    let task_id = get_next_task_id(&tasks_canonical);

    // Generate branch name
    let branch_name = generate_branch_name(description);

    // Determine worktree path: ../{repo_name}-worktrees/{task_id}
    let repo_name = repo_path
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "repo".to_string());
    let worktrees_parent = repo_path
        .parent()
        .ok_or("Cannot determine parent directory")?;
    let worktree_base = worktrees_parent.join(format!("{}-worktrees", repo_name));
    let worktree_path = worktree_base.join(&task_id);

    // Assign color scheme based on task number
    let task_num: usize = task_id
        .strip_prefix("TASK_")
        .and_then(|s| s.parse().ok())
        .unwrap_or(0);
    let color_scheme_index = task_num % COLOR_SCHEME_HEX.len();

    // Create task directory + state.json
    let task_dir = tasks_canonical.join(&task_id);
    std::fs::create_dir_all(&task_dir)
        .map_err(|e| format!("Failed to create task directory: {}", e))?;

    // Relative worktree path for state.json (relative to repo root)
    let worktree_rel = format!("../{}-worktrees/{}", repo_name, task_id);
    let state = create_initial_state(
        &task_id,
        description,
        &branch_name,
        &base_branch,
        &worktree_rel,
        color_scheme_index,
        ai_host,
    );
    let state_file = task_dir.join("state.json");
    let state_json = serde_json::to_string_pretty(&state)
        .map_err(|e| format!("Failed to serialize state: {}", e))?;
    std::fs::write(&state_file, state_json)
        .map_err(|e| format!("Failed to write state.json: {}", e))?;

    // Append to registry for history tracking (survives directory deletion)
    crate::data::task::append_to_registry(&tasks_canonical, &task_id, description, &branch_name);

    // Ensure worktrees parent directory exists
    std::fs::create_dir_all(&worktree_base)
        .map_err(|e| format!("Failed to create worktrees directory: {}", e))?;

    // Git worktree add
    let worktree_str = worktree_path.to_string_lossy();
    let git_add = Command::new("git")
        .args([
            "worktree",
            "add",
            "-b",
            &branch_name,
            &worktree_str,
            &base_branch,
        ])
        .current_dir(repo_path)
        .output()
        .map_err(|e| format!("git worktree add failed: {}", e))?;
    if !git_add.status.success() {
        // Clean up task dir on failure
        let _ = std::fs::remove_dir_all(&task_dir);
        return Err(format!(
            "git worktree add failed: {}",
            String::from_utf8_lossy(&git_add.stderr).trim()
        ));
    }

    // Symlink .tasks/ into the worktree
    let wt_tasks = worktree_path.join(".tasks");
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(&tasks_canonical, &wt_tasks)
            .map_err(|e| format!("Failed to create .tasks symlink: {}", e))?;
    }
    #[cfg(windows)]
    {
        std::os::windows::fs::symlink_dir(&tasks_canonical, &wt_tasks)
            .map_err(|e| format!("Failed to create .tasks symlink: {}", e))?;
    }

    // Write .crew-resume for AI hosts that don't accept prompt arguments (Copilot, etc.)
    let repo_abs = repo_path
        .canonicalize()
        .unwrap_or_else(|_| repo_path.to_path_buf());
    let tasks_abs = tasks_canonical.join(&task_id);
    let resume_cmd = match ai_host {
        AiHost::Copilot | AiHost::Gemini => format!("@crew-resume {}", task_id),
        AiHost::OpenCode => format!("/crew-resume {}", task_id),
        AiHost::Claude => format!("/crew resume {}", task_id),
    };
    let now = chrono::Utc::now().to_rfc3339();
    let resume_content = format!(
        "# Crew Worktree Context\n\
         # Auto-generated by crew-board. Do not commit.\n\
         \n\
         task_id: {task_id}\n\
         description: {description}\n\
         main_repo: {main_repo}\n\
         tasks_path: {tasks_path}\n\
         base_branch: {base_branch}\n\
         ai_host: {ai_host_label}\n\
         created_at: {created_at}\n\
         \n\
         # Instructions for AI agents:\n\
         # This is a git worktree. DO NOT create a new .tasks/ directory here.\n\
         # The .tasks/ symlink in this directory points to the main repo.\n\
         # Resume the workflow by running: {resume_cmd}\n",
        task_id = task_id,
        description = description,
        main_repo = repo_abs.display(),
        tasks_path = tasks_abs.display(),
        base_branch = base_branch,
        ai_host_label = ai_host.label(),
        created_at = now,
        resume_cmd = resume_cmd,
    );
    let resume_file = worktree_path.join(".crew-resume");
    // Best-effort: don't fail worktree creation if this write fails
    let _ = std::fs::write(&resume_file, resume_content);

    let worktree_abs = worktree_path
        .canonicalize()
        .unwrap_or_else(|_| worktree_path.clone());

    Ok(WorktreeResult {
        task_id,
        branch_name,
        worktree_abs,
        base_branch,
        color_scheme_index,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_slugify_basic() {
        assert_eq!(slugify("Hello World"), "hello-world");
        assert_eq!(slugify("Add user auth with JWT!"), "add-user-auth-with-jwt");
        assert_eq!(slugify("  spaces  "), "spaces");
        assert_eq!(slugify("under_scores"), "under-scores");
        assert_eq!(slugify("multi---dashes"), "multi-dashes");
    }

    #[test]
    fn test_slugify_special_chars() {
        assert_eq!(slugify("JIRA-123: Fix the bug"), "jira-123-fix-the-bug");
        assert_eq!(slugify(""), "");
        assert_eq!(slugify("!!!"), "");
    }

    #[test]
    fn test_generate_branch_name() {
        assert_eq!(
            generate_branch_name("Add user authentication with JWT"),
            "crew/add-user-authentication-with-jwt"
        );
        assert_eq!(generate_branch_name(""), "crew/new-task");
    }

    #[test]
    fn test_generate_branch_name_truncation() {
        let long = "This is a very long description that exceeds fifty characters in total length";
        let branch = generate_branch_name(long);
        // "crew/" prefix + slug truncated to 50 chars
        assert!(branch.len() <= 55); // "crew/" + 50
        assert!(branch.starts_with("crew/"));
        assert!(!branch.ends_with('-'));
    }
}
