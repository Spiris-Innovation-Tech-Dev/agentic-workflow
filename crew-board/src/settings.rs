use serde::Deserialize;
use std::path::PathBuf;

/// Persistent user settings loaded from ~/.config/crew-board.toml
#[derive(Debug, Deserialize, Default)]
pub struct Settings {
    /// Explicit repo paths
    #[serde(default)]
    pub repos: Vec<String>,

    /// Directories to scan one level deep for repos
    #[serde(default)]
    pub scan: Vec<String>,

    /// Poll interval in seconds
    pub poll_interval: Option<u64>,
}

impl Settings {
    /// Load from the default config path. Returns Default if missing or malformed.
    pub fn load() -> Self {
        if let Some(path) = config_path() {
            Self::load_from(&path)
        } else {
            Self::default()
        }
    }

    fn load_from(path: &PathBuf) -> Self {
        let content = match std::fs::read_to_string(path) {
            Ok(c) => c,
            Err(_) => return Self::default(),
        };
        match toml::from_str::<Settings>(&content) {
            Ok(s) => s,
            Err(e) => {
                eprintln!(
                    "Warning: failed to parse {}: {}",
                    path.display(),
                    e
                );
                Self::default()
            }
        }
    }
}

/// Returns ~/.config/crew-board.toml (XDG-style).
pub fn config_path() -> Option<PathBuf> {
    dirs::config_dir().map(|d| d.join("crew-board.toml"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_load_missing_file() {
        let settings = Settings::load_from(&PathBuf::from("/tmp/nonexistent-crew-board.toml"));
        assert!(settings.repos.is_empty());
        assert!(settings.scan.is_empty());
        assert!(settings.poll_interval.is_none());
    }

    #[test]
    fn test_load_valid_config() {
        let tmp = std::env::temp_dir().join("crew-board-test-config.toml");
        fs::write(
            &tmp,
            r#"
repos = ["/mnt/c/git/project-a"]
scan = ["/mnt/c/git"]
poll_interval = 5
"#,
        )
        .unwrap();
        let settings = Settings::load_from(&tmp);
        assert_eq!(settings.repos, vec!["/mnt/c/git/project-a"]);
        assert_eq!(settings.scan, vec!["/mnt/c/git"]);
        assert_eq!(settings.poll_interval, Some(5));
        let _ = fs::remove_file(&tmp);
    }

    #[test]
    fn test_load_partial_config() {
        let tmp = std::env::temp_dir().join("crew-board-test-partial.toml");
        fs::write(&tmp, "scan = [\"/mnt/c/git\"]\n").unwrap();
        let settings = Settings::load_from(&tmp);
        assert!(settings.repos.is_empty());
        assert_eq!(settings.scan, vec!["/mnt/c/git"]);
        assert!(settings.poll_interval.is_none());
        let _ = fs::remove_file(&tmp);
    }
}
