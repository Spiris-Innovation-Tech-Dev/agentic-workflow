use std::path::{Path, PathBuf};

/// Discover repo paths from CLI arguments and config.
/// - Explicit `--repo` paths are used directly
/// - `--scan <dir>` / scan dirs search one level deep for repos with .tasks/ or .beads/
/// - If no args and no config, uses current directory
pub fn discover_repos(
    explicit_repos: &[String],
    scan_dirs: &[String],
) -> Vec<PathBuf> {
    let mut repos = Vec::new();

    // Add explicit repos
    for repo in explicit_repos {
        let path = PathBuf::from(repo);
        if is_repo(&path) {
            repos.push(path.canonicalize().unwrap_or(path));
        } else {
            eprintln!("Warning: {} has no .tasks/ or .beads/, skipping", repo);
        }
    }

    // Scan directories for repos (one level deep)
    for scan in scan_dirs {
        let scan_path = PathBuf::from(scan);
        if let Ok(entries) = std::fs::read_dir(&scan_path) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() && is_repo(&path) {
                    repos.push(path.canonicalize().unwrap_or(path));
                }
            }
        }
    }

    // Fallback: current directory
    if repos.is_empty() {
        if let Ok(cwd) = std::env::current_dir() {
            if is_repo(&cwd) {
                repos.push(cwd);
            }
        }
    }

    // Deduplicate by canonical path
    repos.sort();
    repos.dedup();
    repos
}

/// A directory counts as a repo if it has .tasks/ or .beads/ (or both).
fn is_repo(path: &Path) -> bool {
    path.join(".tasks").exists() || path.join(".beads").exists()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_is_repo_with_tasks() {
        let tmp = std::env::temp_dir().join("crew-board-test-repo-disc");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(tmp.join(".tasks")).unwrap();
        assert!(is_repo(&tmp));
        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_is_repo_with_beads() {
        let tmp = std::env::temp_dir().join("crew-board-test-repo-beads");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(tmp.join(".beads")).unwrap();
        assert!(is_repo(&tmp));
        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn test_is_not_repo() {
        let tmp = std::env::temp_dir().join("crew-board-test-norepo");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(&tmp).unwrap();
        assert!(!is_repo(&tmp));
        let _ = fs::remove_dir_all(&tmp);
    }
}
