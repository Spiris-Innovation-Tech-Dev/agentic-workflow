use std::path::{Path, PathBuf};

/// Represents a loaded config file at one cascade level.
#[derive(Debug, Clone)]
pub struct ConfigLevel {
    pub label: String,
    pub path: PathBuf,
    pub data: serde_yaml::Value,
}

/// Load the config cascade for a repo.
/// Returns levels in precedence order (first = lowest priority).
pub fn load_config_cascade(repo_path: &Path) -> Vec<ConfigLevel> {
    let mut levels = Vec::new();

    // 1. Global configs (check Claude, then Copilot, then Gemini)
    if let Some(home) = dirs::home_dir() {
        let global_paths = [
            (home.join(".claude/workflow-config.yaml"), "Global (Claude)"),
            (
                home.join(".copilot/workflow-config.yaml"),
                "Global (Copilot)",
            ),
            (
                home.join(".gemini/workflow-config.yaml"),
                "Global (Gemini)",
            ),
        ];
        for (path, label) in global_paths {
            if let Some(level) = try_load_yaml(&path, label) {
                levels.push(level);
                break; // First found wins at global level
            }
        }
    }

    // 2. Project config
    let project_paths = [
        (repo_path.join("config/workflow-config.yaml"), "Project"),
        (
            repo_path.join(".claude/workflow-config.yaml"),
            "Project (.claude)",
        ),
    ];
    for (path, label) in project_paths {
        if let Some(level) = try_load_yaml(&path, label) {
            levels.push(level);
            break;
        }
    }

    levels
}

/// Load task-specific config override.
#[allow(dead_code)]
pub fn load_task_config(task_dir: &Path) -> Option<ConfigLevel> {
    let path = task_dir.join("config.yaml");
    try_load_yaml(&path, "Task Override")
}

fn try_load_yaml(path: &Path, label: &str) -> Option<ConfigLevel> {
    let content = std::fs::read_to_string(path).ok()?;
    let data: serde_yaml::Value = serde_yaml::from_str(&content).ok()?;
    Some(ConfigLevel {
        label: label.to_string(),
        path: path.to_path_buf(),
        data,
    })
}
