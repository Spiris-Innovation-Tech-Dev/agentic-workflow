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
    OpenCode,
}

/// Color scheme with hex strings for terminal commands.
pub struct ColorSchemeHex {
    pub name: &'static str,
    pub tab: &'static str,
    pub bg: &'static str,
    pub fg: &'static str,
}

pub const COLOR_SCHEME_HEX: &[ColorSchemeHex] = &[
    ColorSchemeHex { name: "Crew Ocean",    tab: "#1A6B8A", bg: "#0C1B2A", fg: "#C8D6E5" },
    ColorSchemeHex { name: "Crew Forest",   tab: "#2D7D46", bg: "#0E1F14", fg: "#C5D1C0" },
    ColorSchemeHex { name: "Crew Sunset",   tab: "#C75B39", bg: "#1F120E", fg: "#D8C8BA" },
    ColorSchemeHex { name: "Crew Amethyst", tab: "#7B5EA7", bg: "#16121F", fg: "#CCC4D8" },
    ColorSchemeHex { name: "Crew Steel",    tab: "#5C7A8A", bg: "#141C22", fg: "#C0CCD4" },
    ColorSchemeHex { name: "Crew Ember",    tab: "#B85C3A", bg: "#1A110D", fg: "#D4C4B4" },
    ColorSchemeHex { name: "Crew Frost",    tab: "#4BA3C7", bg: "#0D1820", fg: "#C4D4E0" },
    ColorSchemeHex { name: "Crew Earth",    tab: "#8D7B4A", bg: "#1A170E", fg: "#D0C8B8" },
];

/// Get hex color scheme by index (wraps around).
pub fn get_hex_scheme(index: usize) -> &'static ColorSchemeHex {
    &COLOR_SCHEME_HEX[index % COLOR_SCHEME_HEX.len()]
}

impl AiHost {
    pub fn label(&self) -> &'static str {
        match self {
            AiHost::Claude => "Claude Code",
            AiHost::Copilot => "GitHub Copilot",
            AiHost::Gemini => "Gemini CLI",
            AiHost::OpenCode => "OpenCode",
        }
    }

    pub fn command(&self) -> &'static str {
        match self {
            AiHost::Claude => "claude",
            AiHost::Copilot => "gh cs",
            AiHost::Gemini => "gemini",
            AiHost::OpenCode => "opencode",
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
    if command_exists("opencode") {
        hosts.push(AiHost::OpenCode);
    }

    // Always show all options even if not detected,
    // since they might be available in the launched shell
    if hosts.is_empty() {
        hosts = vec![AiHost::Claude, AiHost::Copilot, AiHost::Gemini, AiHost::OpenCode];
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
    color_scheme: Option<&ColorSchemeHex>,
) -> Result<(), String> {
    let dir = work_dir.to_string_lossy();
    let resume_prompt = format!("/crew resume {}", task_id);

    // Copilot (`gh cs`) and OpenCode don't accept a prompt argument.
    // The .crew-resume file in the worktree provides context instead.
    // Claude and Gemini accept prompt as CLI argument.
    let shell_cmd_for_host = |dir: &str| -> String {
        match host {
            AiHost::Copilot | AiHost::OpenCode => format!(
                "cd '{}' && {}",
                shell_escape(dir),
                host.command(),
            ),
            _ => format!(
                "cd '{}' && {} \"{}\"",
                shell_escape(dir),
                host.command(),
                resume_prompt,
            ),
        }
    };

    match terminal {
        TerminalEnv::WindowsTerminalWsl => {
            // wt.exe new-tab: open a new WSL tab in Windows Terminal
            // Explicit cd in the bash command since bash -l may reset cwd
            let shell_cmd = shell_cmd_for_host(&dir);
            let mut args: Vec<&str> = vec!["new-tab", "--title", task_id];
            // Storage for owned strings that args references
            let tab_color;
            let scheme_name;
            if let Some(cs) = color_scheme {
                tab_color = cs.tab.to_string();
                scheme_name = cs.name.to_string();
                args.extend(["--tabColor", &tab_color, "--colorScheme", &scheme_name]);
            }
            args.extend(["wsl.exe", "--cd", &dir, "--", "bash", "-lic", &shell_cmd]);
            Command::new("wt.exe")
                .args(&args)
                .spawn()
                .map_err(|e| format!("Failed to launch Windows Terminal: {}", e))?;
        }
        TerminalEnv::Tmux => {
            let shell_cmd = shell_cmd_for_host(&dir);
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
            // Apply color scheme to tmux window (best-effort)
            if let Some(cs) = color_scheme {
                let style = format!("bg={},fg={}", cs.bg, cs.fg);
                Command::new("tmux")
                    .args(["set-option", "-t", task_id, "-w", "window-style", &style])
                    .spawn()
                    .ok();
            }
        }
        TerminalEnv::MacOs => {
            // Use osascript to open Terminal.app
            let shell_cmd = shell_cmd_for_host(&dir);
            let script = format!(
                "tell application \"Terminal\" to do script \"{}\"",
                shell_cmd,
            );
            Command::new("osascript")
                .args(["-e", &script])
                .spawn()
                .map_err(|e| format!("Failed to launch macOS Terminal: {}", e))?;
        }
        TerminalEnv::LinuxGeneric => {
            // Try common terminal emulators
            let shell_cmd = shell_cmd_for_host(&dir);
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
