use serde::Deserialize;
use std::path::Path;

#[derive(Debug, Clone, Deserialize, Default)]
#[allow(dead_code)]
pub struct BeadsIssue {
    pub id: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub priority: u8,
    #[serde(default)]
    pub issue_type: String,
    #[serde(default)]
    pub created_at: String,
    #[serde(default)]
    pub created_by: String,
    #[serde(default)]
    pub updated_at: String,
    #[serde(default)]
    pub assignee: Option<String>,
    #[serde(default)]
    pub labels: Vec<String>,
    #[serde(default)]
    pub blocked_by: Vec<String>,
    #[serde(default)]
    pub blocks: Vec<String>,
}

/// Load beads issues from a .beads/issues.jsonl file.
/// Silently skips malformed lines.
pub fn load_issues(beads_dir: &Path) -> Vec<BeadsIssue> {
    let jsonl_path = beads_dir.join("issues.jsonl");
    let content = match std::fs::read_to_string(&jsonl_path) {
        Ok(c) => c,
        Err(_) => return Vec::new(),
    };
    content
        .lines()
        .filter(|line| !line.trim().is_empty())
        .filter_map(|line| serde_json::from_str::<BeadsIssue>(line).ok())
        .collect()
}

impl BeadsIssue {
    pub fn priority_label(&self) -> &str {
        match self.priority {
            0 => "P0-critical",
            1 => "P1-high",
            2 => "P2-medium",
            3 => "P3-low",
            4 => "P4-backlog",
            _ => "P?",
        }
    }

    pub fn status_symbol(&self) -> &str {
        match self.status.as_str() {
            "open" => "○",
            "in_progress" => "◉",
            "done" | "closed" => "●",
            _ => "?",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_issue_line() {
        let line = r#"{"id":"AW-4jh","title":"Add metrics","status":"open","priority":2,"issue_type":"feature","created_at":"2026-02-13","created_by":"johan","updated_at":"2026-02-13"}"#;
        let issue: BeadsIssue = serde_json::from_str(line).unwrap();
        assert_eq!(issue.id, "AW-4jh");
        assert_eq!(issue.priority_label(), "P2-medium");
        assert_eq!(issue.status_symbol(), "○");
    }

    #[test]
    fn test_parse_in_progress() {
        let line = r#"{"id":"AW-rft","title":"Extract orchestration","status":"in_progress","priority":1,"issue_type":"feature","created_at":"2026-02-13","created_by":"johan","updated_at":"2026-02-13"}"#;
        let issue: BeadsIssue = serde_json::from_str(line).unwrap();
        assert_eq!(issue.status_symbol(), "◉");
        assert_eq!(issue.priority_label(), "P1-high");
    }
}
