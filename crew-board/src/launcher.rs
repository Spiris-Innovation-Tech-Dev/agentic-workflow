use std::path::Path;
use std::process::Command;

/// Detected terminal environment.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TerminalEnv {
    WindowsTerminalWsl,
    Tmux,
    MacOs,
    LinuxGeneric,
}

/// AI host to launch.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum AiHost {
    Claude,
    Copilot,
    Gemini,
}

impl AiHost {
    pub fn label(&self) -> &'static str {
        match self {
            AiHost::Claude => "Claude Code",
            AiHost::Copilot => "GitHub Copilot",
            AiHost::Gemini => "Gemini CLI",
        }
    }

    pub fn command(&self) -> &'static str {
        match self {
            AiHost::Claude => "claude",
            AiHost::Copilot => "gh cs",
            AiHost::Gemini => "gemini",
        }
    }
}

impl TerminalEnv {
    pub fn label(&self) -> &'static str {
        match self {
            TerminalEnv::WindowsTerminalWsl => "Windows Terminal (WSL tab)",
            TerminalEnv::Tmux => "tmux (new window)",
            TerminalEnv::MacOs => "macOS Terminal",
            TerminalEnv::LinuxGeneric => "Terminal",
        }
    }
}

/// Detect available terminal environments for the current OS.
pub fn detect_terminals() -> Vec<TerminalEnv> {
    let mut terminals = Vec::new();

    // Check tmux first (available on any platform)
    if std::env::var("TMUX").is_ok() {
        terminals.push(TerminalEnv::Tmux);
    }

    // WSL2 detection
    if is_wsl() {
        terminals.push(TerminalEnv::WindowsTerminalWsl);
    }

    // macOS
    if cfg!(target_os = "macos") {
        terminals.push(TerminalEnv::MacOs);
    }

    // Generic Linux fallback
    if cfg!(target_os = "linux") && !terminals.is_empty() {
        // Already have better options
    } else if cfg!(target_os = "linux") {
        terminals.push(TerminalEnv::LinuxGeneric);
    }

    // Always have at least one option
    if terminals.is_empty() {
        terminals.push(TerminalEnv::LinuxGeneric);
    }

    terminals
}

/// Detect available AI hosts by checking if commands exist on PATH.
pub fn detect_ai_hosts() -> Vec<AiHost> {
    let mut hosts = Vec::new();

    if command_exists("claude") {
        hosts.push(AiHost::Claude);
    }
    if command_exists("gh") {
        hosts.push(AiHost::Copilot);
    }
    if command_exists("gemini") {
        hosts.push(AiHost::Gemini);
    }

    // Always show all three as options even if not detected,
    // since they might be available in the launched shell
    if hosts.is_empty() {
        hosts = vec![AiHost::Claude, AiHost::Copilot, AiHost::Gemini];
    }

    hosts
}

/// Launch a terminal with the given AI host in the specified directory.
pub fn launch(
    terminal: TerminalEnv,
    host: AiHost,
    work_dir: &Path,
    task_id: &str,
    _task_description: &str,
) -> Result<(), String> {
    let dir = work_dir.to_string_lossy();
    let resume_prompt = format!("/crew resume {}", task_id);

    match terminal {
        TerminalEnv::WindowsTerminalWsl => {
            // wt.exe new-tab: open a new WSL tab in Windows Terminal
            // Explicit cd in the bash command since bash -l may reset cwd
            let shell_cmd = format!(
                "cd '{}' && {} \"{}\"",
                shell_escape(&dir),
                host.command(),
                resume_prompt,
            );
            Command::new("wt.exe")
                .args([
                    "new-tab",
                    "--title",
                    task_id,
                    "wsl.exe",
                    "--cd",
                    &dir,
                    "--",
                    "bash",
                    "-lic",
                    &shell_cmd,
                ])
                .spawn()
                .map_err(|e| format!("Failed to launch Windows Terminal: {}", e))?;
        }
        TerminalEnv::Tmux => {
            let shell_cmd = format!(
                "{} \"{}\"",
                host.command(),
                resume_prompt,
            );
            Command::new("tmux")
                .args([
                    "new-window",
                    "-n",
                    task_id,
                    "-c",
                    &dir,
                    &shell_cmd,
                ])
                .spawn()
                .map_err(|e| format!("Failed to launch tmux window: {}", e))?;
        }
        TerminalEnv::MacOs => {
            // Use osascript to open Terminal.app
            let script = format!(
                "tell application \"Terminal\" to do script \"cd {} && {} '{}'\"",
                shell_escape(&dir),
                host.command(),
                resume_prompt,
            );
            Command::new("osascript")
                .args(["-e", &script])
                .spawn()
                .map_err(|e| format!("Failed to launch macOS Terminal: {}", e))?;
        }
        TerminalEnv::LinuxGeneric => {
            // Try common terminal emulators
            let shell_cmd = format!(
                "cd {} && {} \"{}\"",
                shell_escape(&dir),
                host.command(),
                resume_prompt,
            );
            let terminals_to_try = [
                ("gnome-terminal", vec!["--", "bash", "-c", &shell_cmd]),
                ("xterm", vec!["-e", "bash", "-c", &shell_cmd]),
                ("konsole", vec!["-e", "bash", "-c", &shell_cmd]),
            ];
            let mut launched = false;
            for (cmd, args) in &terminals_to_try {
                if command_exists(cmd) {
                    Command::new(cmd)
                        .args(args)
                        .spawn()
                        .map_err(|e| format!("Failed to launch {}: {}", cmd, e))?;
                    launched = true;
                    break;
                }
            }
            if !launched {
                return Err("No supported terminal emulator found".to_string());
            }
        }
    }

    Ok(())
}

fn is_wsl() -> bool {
    std::fs::read_to_string("/proc/version")
        .map(|v| v.to_lowercase().contains("microsoft"))
        .unwrap_or(false)
}

fn command_exists(cmd: &str) -> bool {
    Command::new("which")
        .arg(cmd)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn shell_escape(s: &str) -> String {
    s.replace('\'', "'\\''")
}
