use chrono::{DateTime, Utc};
use serde::Deserialize;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Deserialize, Default)]
#[allow(dead_code)]
pub struct TaskState {
    pub task_id: String,
    #[serde(default)]
    pub phase: Option<String>,
    #[serde(default)]
    pub phases_completed: Vec<String>,
    #[serde(default)]
    pub review_issues: Vec<serde_json::Value>,
    #[serde(default)]
    pub iteration: u32,
    #[serde(default)]
    pub docs_needed: Vec<String>,
    #[serde(default)]
    pub implementation_progress: ImplementationProgress,
    #[serde(default)]
    pub human_decisions: Vec<serde_json::Value>,
    #[serde(default)]
    pub concerns: Vec<serde_json::Value>,
    #[serde(default)]
    pub worktree: Option<WorktreeInfo>,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub workflow_mode: Option<WorkflowMode>,
    #[serde(default)]
    pub cost_summary: Option<serde_json::Value>,
    #[serde(default)]
    pub created_at: String,
    #[serde(default)]
    pub updated_at: String,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct ImplementationProgress {
    #[serde(default)]
    pub total_steps: u32,
    #[serde(default)]
    pub current_step: u32,
    #[serde(default)]
    pub steps_completed: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[allow(dead_code)]
pub struct WorktreeInfo {
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub path: String,
    #[serde(default)]
    pub branch: String,
    #[serde(default)]
    pub base_branch: String,
    #[serde(default)]
    pub color_scheme_index: usize,
    #[serde(default)]
    pub created_at: String,
    #[serde(default)]
    pub launch: Option<LaunchInfo>,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[allow(dead_code)]
pub struct LaunchInfo {
    #[serde(default)]
    pub terminal_env: String,
    #[serde(default)]
    pub ai_host: String,
    #[serde(default)]
    pub launched_at: String,
    #[serde(default)]
    pub worktree_abs_path: String,
    #[serde(default)]
    pub color_scheme: String,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[allow(dead_code)]
pub struct WorkflowMode {
    #[serde(default)]
    pub requested: String,
    #[serde(default)]
    pub effective: String,
    #[serde(default)]
    pub detection_reason: String,
    #[serde(default)]
    pub confidence: f64,
    #[serde(default)]
    pub phases: Vec<String>,
    #[serde(default)]
    pub estimated_cost: String,
}

/// All phases in workflow order.
pub const PHASE_ORDER: &[&str] = &[
    "architect",
    "developer",
    "reviewer",
    "skeptic",
    "implementer",
    "technical_writer",
];

/// A workflow artifact file discovered in the task directory.
#[derive(Debug, Clone)]
pub struct TaskArtifact {
    pub name: String,         // e.g. "architect", "developer", "reviewer"
    pub label: String,        // Display label: "Architect Analysis"
    pub path: PathBuf,        // Full path to the .md file
    pub size_bytes: u64,
    pub modified: Option<DateTime<Utc>>,
}

/// A human decision recorded in state.json.
#[derive(Debug, Clone)]
pub struct HumanDecision {
    pub checkpoint: String,
    pub decision: String,
    pub notes: String,
}

/// Known artifact files and their display labels.
const KNOWN_ARTIFACTS: &[(&str, &str)] = &[
    ("architect", "Architect Analysis"),
    ("developer", "Developer Plan"),
    ("reviewer", "Reviewer Feedback"),
    ("skeptic", "Skeptic Concerns"),
    ("plan", "Implementation Plan"),
    ("implementer", "Implementer Log"),
    ("technical_writer", "Technical Writer"),
];

/// Discover all .md artifacts in a task directory.
pub fn load_artifacts(task_dir: &Path) -> Vec<TaskArtifact> {
    let mut artifacts = Vec::new();
    let entries = match std::fs::read_dir(task_dir) {
        Ok(e) => e,
        Err(_) => return artifacts,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let ext = path.extension().and_then(|e| e.to_str());
        if ext != Some("md") {
            continue;
        }
        let stem = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_string();
        // Skip non-artifact .md files
        if stem.is_empty() || stem == "README" {
            continue;
        }
        let label = KNOWN_ARTIFACTS
            .iter()
            .find(|(name, _)| *name == stem)
            .map(|(_, label)| label.to_string())
            .unwrap_or_else(|| {
                // Title-case unknown files
                let mut c = stem.chars();
                match c.next() {
                    None => stem.clone(),
                    Some(f) => f.to_uppercase().to_string() + c.as_str(),
                }
            });

        let meta = std::fs::metadata(&path).ok();
        let size_bytes = meta.as_ref().map(|m| m.len()).unwrap_or(0);
        let modified = meta
            .and_then(|m| m.modified().ok())
            .map(DateTime::<Utc>::from);

        artifacts.push(TaskArtifact {
            name: stem,
            label,
            path,
            size_bytes,
            modified,
        });
    }

    // Sort by known order, then alphabetical for unknown
    artifacts.sort_by(|a, b| {
        let a_idx = KNOWN_ARTIFACTS.iter().position(|(n, _)| *n == a.name);
        let b_idx = KNOWN_ARTIFACTS.iter().position(|(n, _)| *n == b.name);
        match (a_idx, b_idx) {
            (Some(ai), Some(bi)) => ai.cmp(&bi),
            (Some(_), None) => std::cmp::Ordering::Less,
            (None, Some(_)) => std::cmp::Ordering::Greater,
            (None, None) => a.name.cmp(&b.name),
        }
    });

    artifacts
}

/// Parse human_decisions from state JSON into structured form.
pub fn parse_decisions(decisions: &[serde_json::Value]) -> Vec<HumanDecision> {
    decisions
        .iter()
        .filter_map(|v| {
            Some(HumanDecision {
                checkpoint: v.get("checkpoint")?.as_str()?.to_string(),
                decision: v
                    .get("decision")
                    .and_then(|d| d.as_str())
                    .unwrap_or("unknown")
                    .to_string(),
                notes: v
                    .get("notes")
                    .and_then(|n| n.as_str())
                    .unwrap_or("")
                    .to_string(),
            })
        })
        .collect()
}

/// Load all tasks from a .tasks/ directory.
/// Silently skips tasks with malformed state.json.
pub fn load_tasks(tasks_dir: &Path) -> Vec<(PathBuf, TaskState)> {
    let mut tasks = Vec::new();
    let entries = match std::fs::read_dir(tasks_dir) {
        Ok(e) => e,
        Err(_) => return tasks,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let state_file = path.join("state.json");
        if !state_file.exists() {
            continue;
        }
        let content = match std::fs::read_to_string(&state_file) {
            Ok(c) => c,
            Err(_) => continue,
        };
        match serde_json::from_str::<TaskState>(&content) {
            Ok(state) => tasks.push((path, state)),
            Err(_) => continue,
        }
    }
    tasks.sort_by(|a, b| a.1.task_id.cmp(&b.1.task_id));
    tasks
}

impl TaskState {
    /// Returns true if all required phases are complete.
    pub fn is_complete(&self) -> bool {
        const REQUIRED: &[&str] = &[
            "architect",
            "developer",
            "reviewer",
            "implementer",
            "technical_writer",
        ];
        REQUIRED
            .iter()
            .all(|p| self.phases_completed.contains(&p.to_string()))
    }

    /// Progress as a fraction 0.0 to 1.0 based on phases completed.
    #[allow(dead_code)]
    pub fn phase_progress(&self) -> f64 {
        if PHASE_ORDER.is_empty() {
            return 0.0;
        }
        self.phases_completed.len() as f64 / PHASE_ORDER.len() as f64
    }

    /// Short display string for current status.
    pub fn status_label(&self) -> &str {
        if self.is_complete() {
            "done"
        } else if let Some(ref phase) = self.phase {
            phase.as_str()
        } else {
            "pending"
        }
    }

    /// Color scheme name from worktree, if any.
    #[allow(dead_code)]
    pub fn color_scheme_name(&self) -> Option<&str> {
        self.worktree
            .as_ref()
            .and_then(|wt| wt.launch.as_ref())
            .map(|l| l.color_scheme.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_minimal_state() {
        let json = r#"{"task_id": "TASK_001"}"#;
        let state: TaskState = serde_json::from_str(json).unwrap();
        assert_eq!(state.task_id, "TASK_001");
        assert!(state.phase.is_none());
        assert!(state.phases_completed.is_empty());
    }

    #[test]
    fn test_parse_full_state() {
        let json = r#"{
            "task_id": "TASK_003",
            "phase": "architect",
            "phases_completed": ["architect"],
            "iteration": 1,
            "description": "Test task",
            "worktree": {
                "status": "active",
                "path": "../worktrees/TASK_003",
                "branch": "crew/test",
                "base_branch": "main",
                "color_scheme_index": 3,
                "launch": {
                    "terminal_env": "windows_terminal",
                    "ai_host": "claude",
                    "color_scheme": "Crew Amethyst"
                }
            }
        }"#;
        let state: TaskState = serde_json::from_str(json).unwrap();
        assert_eq!(state.task_id, "TASK_003");
        assert_eq!(state.color_scheme_name(), Some("Crew Amethyst"));
        assert!(!state.is_complete());
    }

    #[test]
    fn test_is_complete() {
        let json = r#"{
            "task_id": "TASK_DONE",
            "phases_completed": ["architect", "developer", "reviewer", "skeptic", "implementer", "technical_writer"]
        }"#;
        let state: TaskState = serde_json::from_str(json).unwrap();
        assert!(state.is_complete());
    }

    #[test]
    fn test_phase_progress() {
        let json = r#"{
            "task_id": "TASK_HALF",
            "phases_completed": ["architect", "developer", "reviewer"]
        }"#;
        let state: TaskState = serde_json::from_str(json).unwrap();
        assert!((state.phase_progress() - 0.5).abs() < 0.01);
    }
}
