use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// A loaded task that may be live (on disk) or archived (deleted from disk).
#[derive(Debug, Clone)]
pub struct LoadedTask {
    pub dir: PathBuf,
    pub state: TaskState,
    /// true if this task was reconstructed from the registry, gap detection,
    /// or metadata.json fallback (no full workflow state)
    pub archived: bool,
    /// Jira key from metadata.json (external setup scripts)
    pub jira_key: Option<String>,
}

/// Lightweight metadata written by external setup scripts.
/// Different schema from state.json — used as fallback when state.json is missing.
#[derive(Debug, Clone, Deserialize)]
pub struct TaskMetadata {
    #[serde(default)]
    pub task_id: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub jira_key: String,
    #[serde(default)]
    pub branch_name: String,
    #[serde(default)]
    pub base_branch: String,
    #[serde(default)]
    pub worktree_path: String,
    #[serde(default)]
    pub created_at: String,
}

/// An entry in the append-only .tasks/.registry.jsonl file.
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RegistryEntry {
    pub task_id: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub branch: String,
    #[serde(default)]
    pub created_at: String,
}

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
    pub knowledge_base_inventory: Option<KnowledgeBaseInventory>,
    #[serde(default)]
    pub worktree: Option<WorktreeInfo>,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub workflow_mode: Option<WorkflowMode>,
    #[serde(default)]
    pub cost_summary: Option<serde_json::Value>,
    #[serde(default)]
    pub status: Option<String>,
    #[serde(default)]
    pub completed_at: Option<String>,
    #[serde(default)]
    pub files_changed: Vec<String>,
    #[serde(default)]
    pub optional_phases: Vec<String>,
    #[serde(default)]
    pub optional_phase_reasons: Option<serde_json::Value>,
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
pub struct KnowledgeBaseInventory {
    #[serde(default)]
    pub path: Option<String>,
    #[serde(default)]
    pub files: Vec<String>,
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
    pub timestamp: String,
}

/// A single interaction entry from interactions.jsonl.
#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
pub struct Interaction {
    #[serde(default)]
    pub timestamp: String,
    #[serde(default)]
    pub role: String,
    #[serde(default)]
    pub content: String,
    #[serde(default, rename = "type")]
    pub type_: String,
    #[serde(default)]
    pub agent: String,
    #[serde(default)]
    pub phase: String,
}

/// A discovery entry from memory/discoveries.jsonl.
#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
pub struct Discovery {
    #[serde(default)]
    pub timestamp: String,
    #[serde(default)]
    pub category: String,
    #[serde(default)]
    pub content: String,
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

/// Load interactions from a task's interactions.jsonl file.
/// Returns empty vec if file doesn't exist or can't be parsed.
pub fn load_interactions(task_dir: &Path) -> Vec<Interaction> {
    let path = task_dir.join("interactions.jsonl");
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return Vec::new(),
    };
    content
        .lines()
        .filter(|line| !line.trim().is_empty())
        .filter_map(|line| serde_json::from_str::<Interaction>(line).ok())
        .collect()
}

/// Load discoveries from a task's memory/discoveries.jsonl file.
/// Returns empty vec if file doesn't exist or can't be parsed.
pub fn load_discoveries(task_dir: &Path) -> Vec<Discovery> {
    let path = task_dir.join("memory").join("discoveries.jsonl");
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return Vec::new(),
    };
    content
        .lines()
        .filter(|line| !line.trim().is_empty())
        .filter_map(|line| serde_json::from_str::<Discovery>(line).ok())
        .collect()
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
                timestamp: v
                    .get("timestamp")
                    .and_then(|t| t.as_str())
                    .unwrap_or("")
                    .to_string(),
            })
        })
        .collect()
}

/// Load the append-only registry file (.tasks/.registry.jsonl).
/// Returns a map from task_id to registry entry.
pub fn load_registry(tasks_dir: &Path) -> HashMap<String, RegistryEntry> {
    let registry_path = tasks_dir.join(".registry.jsonl");
    let content = match std::fs::read_to_string(&registry_path) {
        Ok(c) => c,
        Err(_) => return HashMap::new(),
    };
    let mut map = HashMap::new();
    for line in content.lines() {
        if line.trim().is_empty() {
            continue;
        }
        if let Ok(entry) = serde_json::from_str::<RegistryEntry>(line) {
            map.insert(entry.task_id.clone(), entry);
        }
    }
    map
}

/// Append a registry entry when a new task is created.
pub fn append_to_registry(tasks_dir: &Path, task_id: &str, description: &str, branch: &str) {
    use std::io::Write;
    let registry_path = tasks_dir.join(".registry.jsonl");
    let entry = RegistryEntry {
        task_id: task_id.to_string(),
        description: description.to_string(),
        branch: branch.to_string(),
        created_at: chrono::Utc::now().to_rfc3339(),
    };
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(registry_path)
    {
        if let Ok(json) = serde_json::to_string(&entry) {
            let _ = writeln!(file, "{}", json);
        }
    }
}

/// Load all tasks from a .tasks/ directory, including archived (deleted) tasks.
/// Silently skips tasks with malformed state.json.
/// Returns tasks sorted by task_id, including placeholder entries for
/// task IDs that existed in the registry but whose directories are gone.
pub fn load_tasks(tasks_dir: &Path) -> Vec<LoadedTask> {
    let re = regex::Regex::new(r"^TASK_(\d+)$").unwrap();
    let mut tasks = Vec::new();
    let mut on_disk_nums: std::collections::HashSet<u32> = std::collections::HashSet::new();

    // 1. Load all on-disk tasks (existing logic)
    let entries = match std::fs::read_dir(tasks_dir) {
        Ok(e) => e,
        Err(_) => return tasks,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        // Track task number
        if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
            if let Some(caps) = re.captures(name) {
                if let Ok(num) = caps[1].parse::<u32>() {
                    on_disk_nums.insert(num);
                }
            }
        }
        let state_file = path.join("state.json");
        if !state_file.exists() {
            // Fallback: try metadata.json (written by external setup scripts)
            let meta_file = path.join("metadata.json");
            if meta_file.exists() {
                if let Ok(content) = std::fs::read_to_string(&meta_file) {
                    if let Ok(meta) = serde_json::from_str::<TaskMetadata>(&content) {
                        let jira_key = if meta.jira_key.is_empty() {
                            None
                        } else {
                            Some(meta.jira_key.clone())
                        };
                        let state = TaskState::from_metadata(&meta);
                        tasks.push(LoadedTask {
                            dir: path,
                            state,
                            archived: true,
                            jira_key,
                        });
                    }
                }
            }
            continue;
        }
        let content = match std::fs::read_to_string(&state_file) {
            Ok(c) => c,
            Err(_) => continue,
        };
        match serde_json::from_str::<TaskState>(&content) {
            Ok(state) => tasks.push(LoadedTask {
                dir: path,
                state,
                archived: false,
                jira_key: None,
            }),
            Err(_) => continue,
        }
    }

    // 2. Load registry
    let registry = load_registry(tasks_dir);

    // 3. Find max task number from both sources
    let max_from_disk = on_disk_nums.iter().copied().max().unwrap_or(0);
    let max_from_registry = registry
        .keys()
        .filter_map(|id| id.strip_prefix("TASK_"))
        .filter_map(|s| s.parse::<u32>().ok())
        .max()
        .unwrap_or(0);
    let max_num = max_from_disk.max(max_from_registry);

    // 4. Fill gaps with archived entries
    let on_disk_task_ids: std::collections::HashSet<String> =
        tasks.iter().map(|t| t.state.task_id.clone()).collect();

    for num in 1..=max_num {
        let task_id = format!("TASK_{:03}", num);
        if on_disk_task_ids.contains(&task_id) {
            continue;
        }

        // Create archived placeholder
        let mut state = TaskState {
            task_id: task_id.clone(),
            ..Default::default()
        };

        if let Some(reg) = registry.get(&task_id) {
            state.description = reg.description.clone();
            state.created_at = reg.created_at.clone();
            if !reg.branch.is_empty() {
                state.worktree = Some(WorktreeInfo {
                    branch: reg.branch.clone(),
                    ..Default::default()
                });
            }
        } else {
            state.description = "(deleted)".to_string();
        }

        tasks.push(LoadedTask {
            dir: tasks_dir.join(&task_id),
            state,
            archived: true,
            jira_key: None,
        });
    }

    // 5. Sort all by task_id
    tasks.sort_by(|a, b| a.state.task_id.cmp(&b.state.task_id));
    tasks
}

impl TaskState {
    /// Create a minimal TaskState from a metadata.json file.
    pub fn from_metadata(meta: &TaskMetadata) -> Self {
        let worktree = if !meta.branch_name.is_empty() || !meta.worktree_path.is_empty() {
            Some(WorktreeInfo {
                branch: meta.branch_name.clone(),
                base_branch: meta.base_branch.clone(),
                path: meta.worktree_path.clone(),
                ..Default::default()
            })
        } else {
            None
        };

        TaskState {
            task_id: meta.task_id.clone(),
            description: meta.description.clone(),
            created_at: meta.created_at.clone(),
            worktree,
            ..Default::default()
        }
    }

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
        // Use explicit status field if present
        if let Some(ref status) = self.status {
            if status == "completed" {
                return "done";
            }
        }
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
