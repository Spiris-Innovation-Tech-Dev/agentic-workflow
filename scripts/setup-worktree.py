#!/usr/bin/env python3
"""
Create an isolated git worktree for a crew workflow task.

Usage:
    python3 scripts/setup-worktree.py <description> [options]

Options:
    --ai-host PLATFORM       claude | copilot | gemini (default: claude)
    --base-branch BRANCH     Base branch (default: current branch)
    --base-path PATH         Worktree base dir override
    --branch-name NAME       Explicit branch name

    --pull / --no-pull       Resolve sync_before_create prompt
    --recycle / --no-recycle Resolve recycle prompt
    --launch / --no-launch   Resolve auto_launch prompt

    --json                   Machine-readable JSON output
    --dry-run                Print what would happen, no changes

Exit codes:
    0 = success
    1 = error
    2 = pending decisions needed (JSON with pending_decisions list)

Steps (deterministic):
    1. Find repo root, validate not in worktree
    2. Load config cascade (global -> project YAML)
    3. Detect current branch
    4. Check base branch freshness (fetch + rev-list)
    5. Pull if --pull and behind
    6. Generate task ID (scan .tasks/ for next TASK_XXX)
    7. Create .tasks/TASK_XXX/ with initial state.json
    8. Resolve AI host, base path, branch name, color scheme
    9. Find recyclable worktree (if --recycle)
    10. Execute git worktree add (or recycle: move + checkout)
    11. Symlink .tasks/, copy/patch host settings
    12. Run fix-worktree-paths.py (if WSL + /mnt/)
    13. Install dependencies (detect lockfile, run installer)
    14. Run post_setup_commands with placeholder substitution
    15. Detect terminal env + build launch commands
    16. Execute launch (if --launch)
    17. Output JSON result
"""

import argparse
import base64
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Constants (inlined from state_tools.py)
# ---------------------------------------------------------------------------

CREW_COLOR_SCHEMES = [
    {"name": "Crew Ocean",    "tab": "#1A6B8A", "bg": "#0C1B2A", "fg": "#C8D6E5"},
    {"name": "Crew Forest",   "tab": "#2D7D46", "bg": "#0E1F14", "fg": "#C5D1C0"},
    {"name": "Crew Sunset",   "tab": "#C75B39", "bg": "#1F120E", "fg": "#D8C8BA"},
    {"name": "Crew Amethyst", "tab": "#7B5EA7", "bg": "#16121F", "fg": "#CCC4D8"},
    {"name": "Crew Steel",    "tab": "#5C7A8A", "bg": "#141C22", "fg": "#C0CCD4"},
    {"name": "Crew Ember",    "tab": "#B85C3A", "bg": "#1A110D", "fg": "#D4C4B4"},
    {"name": "Crew Frost",    "tab": "#4BA3C7", "bg": "#0D1820", "fg": "#C4D4E0"},
    {"name": "Crew Earth",    "tab": "#8D7B4A", "bg": "#1A170E", "fg": "#D0C8B8"},
]

AI_HOST_CLI = {
    "claude": "claude",
    "gemini": "gemini",
    "copilot": "copilot",
    "opencode": "opencode",
}

HOST_SETTINGS = {
    "claude": [".claude/settings.local.json"],
    "gemini": ["gemini_trust"],
    "copilot": [],
    "opencode": [],
}
# NOTE: AI_HOST_CLI and HOST_SETTINGS are inlined from state_tools.py
# (see _AI_HOST_CLI and _HOST_SETTINGS in that module) to keep this script standalone. Keep in sync.

# NOTE: This script is also available as scripts/gemini-trust.py for standalone use.
GEMINI_TRUST_SCRIPT = """
import json, os, sys
worktree_abs = sys.argv[1]
trust_file = os.path.expanduser("~/.gemini/trustedFolders.json")
os.makedirs(os.path.dirname(trust_file), exist_ok=True)
d = {}
if os.path.isfile(trust_file):
    with open(trust_file) as f:
        d = json.load(f)
if worktree_abs not in d:
    d[worktree_abs] = "TRUST_FOLDER"
    with open(trust_file, "w") as f:
        json.dump(d, f, indent=2)
        f.write("\\n")
"""

SETTINGS_PATCH_SCRIPT = """
import json, os, sys
src, dst, tasks_dir = sys.argv[1], sys.argv[2], sys.argv[3]
perms_tpl = sys.argv[4] if len(sys.argv) > 4 else None
os.makedirs(os.path.dirname(dst), exist_ok=True)
d = {}
if os.path.isfile(src):
    with open(src) as f:
        d = json.load(f)
dirs = d.setdefault("additionalDirectories", [])
if tasks_dir not in dirs:
    dirs.append(tasks_dir)
if perms_tpl and os.path.isfile(perms_tpl):
    with open(perms_tpl) as f:
        tpl = json.load(f)
    perms = d.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])
    for entry in tpl.get("permissions", {}).get("allow", []):
        if entry not in allow:
            allow.append(entry)
with open(dst, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\\n")
"""

LOCKFILE_INSTALLERS = [
    ("package-lock.json", "npm ci"),
    ("yarn.lock", "yarn install --frozen-lockfile"),
    ("pnpm-lock.yaml", "pnpm install --frozen-lockfile"),
    ("requirements.txt", "pip install -r requirements.txt"),
    ("pyproject.toml", "pip install -e ."),
    ("Gemfile.lock", "bundle install"),
    ("go.sum", "go mod download"),
    ("Cargo.lock", "cargo fetch"),
]

LOCKFILE_INSTALLERS_WIN = [
    ("package-lock.json", "npm ci"),
    ("yarn.lock", "yarn install --frozen-lockfile"),
    ("pnpm-lock.yaml", "pnpm install --frozen-lockfile"),
    ("requirements.txt", "python -m pip install -r requirements.txt"),
    ("pyproject.toml", "python -m pip install -e ."),
]

DEFAULT_WORKTREE_CONFIG = {
    "base_path": "../{repo_name}-worktrees",
    "branch_prefix": "crew/",
    "cleanup_on_complete": "prompt",
    "auto_launch": "prompt",
    "ai_host": "auto",
    "copy_settings": True,
    "recycle": "prompt",
    "sync_before_create": "prompt",
    "wsl_native_path": "",
    "install_deps": "auto",
    "jira": {
        "auto_assign": "never",
        "transitions": {
            "on_create": {"to": "", "mode": "auto", "only_from": []},
            "on_complete": {"to": "", "mode": "auto", "only_from": []},
            "on_cleanup": {"to": "", "mode": "prompt", "only_from": []},
        },
    },
    "post_setup_commands": [],
}


# ---------------------------------------------------------------------------
# Helpers (inlined from cleanup-worktree.py / config_tools.py / state_tools.py)
# ---------------------------------------------------------------------------

def find_repo_root() -> Path:
    """Walk up from CWD looking for a directory with .git/ as a directory (main repo)."""
    current = Path.cwd().resolve()
    while True:
        git_path = current / ".git"
        if git_path.is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    fatal("Could not find repo root (no .git/ directory found).")


def check_not_in_worktree():
    """Refuse to run from inside a worktree. .git must be a directory, not a file."""
    git_path = Path(".git")
    if git_path.is_file():
        fatal("Cannot create worktrees from within a worktree. Run from the main repo.")


# NOTE: is_wsl() and find_repo_root() are inlined here to keep setup-worktree.py standalone.
# Canonical versions are in scripts/shared_utils.py. Keep in sync.
def is_wsl() -> bool:
    """Detect if running under WSL."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except (OSError, FileNotFoundError, PermissionError):
        return False


_CMD_UNSAFE_CHARS = set('&|<>^%"')


def _validate_path_for_cmd(path: str) -> None:
    """Raise ValueError if path contains cmd.exe metacharacters."""
    bad = _CMD_UNSAFE_CHARS.intersection(path)
    if bad:
        raise ValueError(f"Path contains unsafe characters for cmd.exe: {bad!r} in {path!r}")


def _symlink_or_junction(target: str, link: str) -> None:
    """Create a symlink, falling back to NTFS junction on native Windows.

    On non-Windows platforms, always uses os.symlink().
    On Windows, tries os.symlink() first (needs admin/dev mode),
    then falls back to 'cmd /c mklink /J' for NTFS junctions.
    """
    if platform.system() != "Windows":
        os.symlink(target, link)
        return
    try:
        os.symlink(target, link)
    except OSError:
        # Symlink failed (no admin/dev-mode privilege) — fall back to junction
        _validate_path_for_cmd(target)
        _validate_path_for_cmd(link)
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link, target],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise OSError(
                f"Failed to create junction {link} -> {target}: {result.stderr.strip()}"
            )


def _remove_symlink_or_junction(path: str) -> None:
    """Remove a symlink or NTFS junction at *path*."""
    if os.path.islink(path):
        os.remove(path)
    elif platform.system() == "Windows" and os.path.isdir(path):
        # Junction (directory reparse point) — os.rmdir removes the
        # reparse point without touching the target's contents.
        os.rmdir(path)
    elif os.path.exists(path):
        os.remove(path)


def slugify(text: str) -> str:
    """Convert text to git-branch-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s_-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def extract_jira_key(text: str) -> Optional[str]:
    """Extract a Jira issue key (e.g., SAD-123) from text."""
    m = re.search(r'\b([A-Z][A-Z0-9]+-\d+)\b', text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Config loading (inlined from config_tools.py)
# ---------------------------------------------------------------------------

PLATFORM_DIRS = [".claude", ".copilot", ".gemini", ".config/opencode", ".opencode"]
# NOTE: PLATFORM_DIRS is inlined from config_tools.py to keep this script standalone. Keep in sync.

# Full default config — only worktree section needed but we merge the whole thing
# to support overrides at any level.
DEFAULT_CONFIG = {
    "checkpoints": {},
    "knowledge_base": "docs/ai-context/",
    "task_directory": ".tasks/",
    "max_iterations": {},
    "models": {},
    "worktree": DEFAULT_WORKTREE_CONFIG,
    "auto_actions": {},
    "loop_mode": {},
}

try:
    import yaml as _yaml
except ImportError:
    _yaml = None


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    if _yaml is None:
        # Fallback: simple key: value parser
        with open(path) as f:
            content = f.read()
        config = {}
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                match = re.match(r'^(\w+):\s*(.+)$', line)
                if match:
                    key, value = match.groups()
                    if value.lower() == 'true':
                        config[key] = True
                    elif value.lower() == 'false':
                        config[key] = False
                    elif value.isdigit():
                        config[key] = int(value)
                    else:
                        config[key] = value
        return config if config else None
    try:
        with open(path) as f:
            return _yaml.safe_load(f)
    except Exception:
        return None


def load_effective_config(project_dir: Optional[str] = None) -> dict:
    """Load merged config cascade: global -> project. Returns worktree section."""
    config = dict(DEFAULT_CONFIG)

    # Global config
    for platform_dir in PLATFORM_DIRS:
        global_path = Path.home() / platform_dir / "workflow-config.yaml"
        if global_path.exists():
            global_config = _load_yaml(global_path)
            if global_config:
                config = _deep_merge(config, global_config)
            break

    # Project config
    base = Path(project_dir) if project_dir else Path.cwd()
    for platform_dir in PLATFORM_DIRS:
        project_path = base / platform_dir / "workflow-config.yaml"
        if project_path.exists():
            project_config = _load_yaml(project_path)
            if project_config:
                config = _deep_merge(config, project_config)
            break

    return config


# ---------------------------------------------------------------------------
# Task ID / state management
# ---------------------------------------------------------------------------

def get_tasks_dir(repo_root: Path) -> Path:
    return repo_root / ".tasks"


def get_next_task_id(tasks_dir: Path) -> str:
    if not tasks_dir.exists():
        return "TASK_001"
    existing = []
    for d in tasks_dir.iterdir():
        if d.is_dir():
            match = re.match(r"TASK_(\d+)", d.name)
            if match:
                existing.append(int(match.group(1)))
    next_num = max(existing, default=0) + 1
    return f"TASK_{next_num:03d}"


def create_initial_state(task_id: str, description: str) -> dict:
    """Create initial state.json contents (equivalent to workflow_initialize)."""
    now = datetime.now().isoformat()
    return {
        "task_id": task_id,
        "phase": "architect",
        "phases_completed": [],
        "review_issues": [],
        "iteration": 1,
        "docs_needed": [],
        "implementation_progress": {
            "total_steps": 0,
            "current_step": 0,
            "steps_completed": [],
        },
        "human_decisions": [],
        "knowledge_base_inventory": {"path": None, "files": []},
        "concerns": [],
        "worktree": None,
        "description": description,
        "created_at": now,
        "updated_at": now,
    }


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {}


def save_state(state_file: Path, state: dict):
    state["updated_at"] = datetime.now().isoformat()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Branch / worktree helpers
# ---------------------------------------------------------------------------

def generate_branch_name(task_id: str, state: dict) -> str:
    """Generate unique branch name from linked issue or task description."""
    linked = state.get("linked_issue") or state.get("beads_issue")
    if linked:
        return f"crew/{slugify(linked)}"
    desc = state.get("description", "")
    if desc:
        slug = slugify(desc)[:50].rstrip("-")
        if slug:
            return f"crew/{slug}"
    return f"crew/{task_id.lower().replace('_', '-')}"


def find_recyclable_worktree(tasks_dir: Path, repo_root: Path) -> Optional[tuple[Path, dict]]:
    """Find a worktree with status 'recyclable' whose directory still exists."""
    if not tasks_dir.exists():
        return None
    for task_dir in sorted(tasks_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        state_file = task_dir / "state.json"
        if not state_file.exists():
            continue
        state = load_state(state_file)
        worktree = state.get("worktree")
        if not worktree or worktree.get("status") != "recyclable":
            continue
        wt_path = worktree.get("path")
        if not wt_path:
            continue
        abs_path = os.path.normpath(os.path.join(str(repo_root), wt_path))
        if os.path.isdir(abs_path):
            return (task_dir, state)
    return None


def build_resume_prompt(task_id: str, main_tasks_path: str, ai_host: str = "claude") -> str:
    """Build the resume prompt string for a worktree session."""
    if ai_host in ("gemini", "copilot"):
        resume_cmd = f"@crew-resume {task_id}"
    elif ai_host == "opencode":
        resume_cmd = f"/crew-resume {task_id}"
    else:
        resume_cmd = f"/crew resume {task_id}"
    return (
        f"Resume crew workflow {task_id}. "
        f"This is a git worktree — DO NOT create a new .tasks/ directory here. "
        f"The task state lives in the main repo at: {main_tasks_path} "
        f"Read and write all task state using that absolute path. "
        f"A .tasks/ symlink exists in this worktree for convenience, but always "
        f"prefer the absolute path above for reliability. "
        f"{resume_cmd}"
    )


# ---------------------------------------------------------------------------
# Shell / subprocess helpers
# ---------------------------------------------------------------------------

def fatal(msg: str):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def run_cmd(args: list[str], dry_run: bool, cwd: Optional[str] = None,
            capture: bool = False, warn_only: bool = False) -> subprocess.CompletedProcess:
    """Run a command. On failure, either fatal or warn based on warn_only."""
    cmd_str = " ".join(args)
    if dry_run:
        print(f"  [dry-run] Would run: {cmd_str}", file=sys.stderr)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
    result = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0 and not warn_only:
        fatal(f"Command failed: {cmd_str}\n  {result.stderr.strip()}")
    return result


def run_cmd_shell(cmd: str, dry_run: bool, cwd: Optional[str] = None,
                  warn_only: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command string."""
    if dry_run:
        print(f"  [dry-run] Would run: {cmd}", file=sys.stderr)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0 and not warn_only:
        fatal(f"Command failed: {cmd}\n  {result.stderr.strip()}")
    return result


def wslpath_w(path: str) -> str:
    """Convert a WSL path to a Windows path using wslpath -w."""
    result = subprocess.run(["wslpath", "-w", path], capture_output=True, text=True)
    if result.returncode != 0:
        return path
    return result.stdout.strip()


def run_native_or_wsl(cmd: str, cwd: str, wsl_native: bool, dry_run: bool,
                      warn_only: bool = False) -> subprocess.CompletedProcess:
    """Run a command natively or via PowerShell depending on WSL mode."""
    if wsl_native:
        win_cwd = wslpath_w(cwd)
        ps_cmd = f"powershell.exe -Command \"cd '{win_cwd}'; {cmd}\""
        return run_cmd_shell(ps_cmd, dry_run, warn_only=warn_only)
    else:
        return run_cmd_shell(cmd, dry_run, cwd=cwd, warn_only=warn_only)


def _shell_quote(s: str, use_powershell: bool = False) -> str:
    """Quote a string for shell use.

    For PowerShell: wraps in single quotes with doubled internal single quotes.
    This is safe ONLY when the result is used inside a PowerShell script passed
    via -EncodedCommand (not inside a double-quoted -Command string).
    """
    if use_powershell:
        return "'" + s.replace("'", "''") + "'"
    return shlex.quote(s)


def _powershell_encoded_command(script: str) -> str:
    """Encode a PowerShell script as a -EncodedCommand argument fragment.

    Returns an argument fragment (e.g. '-EncodedCommand <base64>'), NOT a
    runnable command. Callers must prepend 'powershell.exe' or embed it in
    a larger command string. Prefer run_native_or_wsl() for general use;
    this function is for launch commands where encoding avoids shell escaping.

    Uses Base64-encoded UTF-16LE as recommended by Microsoft.
    """
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    return f'-EncodedCommand {encoded}'


# ---------------------------------------------------------------------------
# Terminal detection
# ---------------------------------------------------------------------------

def detect_terminal_env() -> str:
    """Detect terminal environment for launch commands."""
    if os.environ.get("TMUX"):
        return "tmux"
    # Native Windows (not WSL) — check BEFORE WT detection so that
    # native Windows with WT installed doesn't fall into the WSL-only
    # windows_terminal path which generates wsl.exe commands.
    if platform.system() == "Windows":
        return "windows_native"
    # Windows Terminal under WSL — wt.exe on PATH means WSL with WT
    if shutil.which("wt.exe") or shutil.which("wt"):
        return "windows_terminal"
    if platform.system() == "Darwin":
        return "macos"
    return "linux_generic"


def build_launch_commands(
    task_id: str, worktree_abs: str, ai_host: str, terminal_env: str,
    resume_prompt: str, color_scheme: dict,
) -> tuple[list[str], list[str]]:
    """Build terminal launch commands. Returns (commands, warnings)."""
    cli = AI_HOST_CLI.get(ai_host, "claude")
    warnings = []
    launch_commands = []

    use_ps = terminal_env == "windows_native"
    safe_path = _shell_quote(worktree_abs, use_powershell=use_ps)
    safe_prompt = _shell_quote(resume_prompt, use_powershell=use_ps)
    safe_task_id = _shell_quote(task_id, use_powershell=use_ps)

    if ai_host == "copilot":
        cli_with_prompt = cli
        warnings.append(
            "Copilot CLI does not support auto-sending prompts. "
            "After the terminal opens, paste the resume prompt manually."
        )
    elif ai_host == "gemini":
        cli_with_prompt = f"{cli} -i {safe_prompt}"
    elif ai_host == "opencode":
        cli_with_prompt = f"{cli} run {safe_prompt}"
    else:
        cli_with_prompt = f"{cli} {safe_prompt}"

    if terminal_env == "tmux":
        launch_commands.append(
            f"tmux new-window -n {safe_task_id} -c {safe_path} "
            f"{shlex.quote(cli_with_prompt)}"
        )
        launch_commands.append(
            f"tmux set-option -t {safe_task_id} -w window-style "
            f"'bg={color_scheme['bg']},fg={color_scheme['fg']}'"
        )
    elif terminal_env == "windows_terminal":
        launch_commands.append(
            f"wt.exe new-tab "
            f"--title {safe_task_id} "
            f"--tabColor \"{color_scheme['tab']}\" "
            f"--colorScheme \"{color_scheme['name']}\" "
            f"wsl.exe --cd {safe_path} "
            f"-- bash -lic {shlex.quote(cli_with_prompt)}"
        )
    elif terminal_env == "macos":
        inner_script = f"cd {safe_path} && {cli_with_prompt}"
        launch_commands.append(
            f'osascript -e \'tell app "Terminal" to do script {shlex.quote(inner_script)}\''
        )
    elif terminal_env == "windows_native":
        # PowerShell: build the inner script, then encode it to avoid all escaping issues.
        # safe_path and cli_with_prompt already use PowerShell single-quote escaping.
        ps_script = f"Set-Location {safe_path}; {cli_with_prompt}"
        encoded_arg = _powershell_encoded_command(ps_script)
        launch_commands.append(f'start powershell -NoExit {encoded_arg}')
    else:
        warnings.append(
            "Cannot reliably open a new terminal on this platform. "
            "Please open a terminal manually, navigate to the worktree, and run the resume prompt."
        )

    return launch_commands, warnings


# ---------------------------------------------------------------------------
# Decision resolution
# ---------------------------------------------------------------------------

def resolve_prompt_setting(
    config_value: str, cli_flag: Optional[bool], setting_name: str,
    default_when_auto: bool = True,
) -> tuple[bool, Optional[dict]]:
    """Resolve a prompt/auto/never config setting.

    Returns (resolved_value, pending_decision_or_None).
    """
    if config_value == "never":
        return False, None
    if config_value == "auto":
        return default_when_auto, None
    # config_value == "prompt"
    if cli_flag is not None:
        return cli_flag, None
    # No CLI flag provided — this is a pending decision
    return False, {
        "setting": setting_name,
        "config_value": config_value,
        "description": f"Config '{setting_name}' is set to 'prompt' but no CLI flag was provided.",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an isolated git worktree for a crew workflow task"
    )
    parser.add_argument("description", help="Task description (free text or Jira key)")

    parser.add_argument("--ai-host", default=None, choices=["claude", "copilot", "gemini", "opencode"],
                        help="AI host platform (default: auto-detect from config)")
    parser.add_argument("--base-branch", default=None,
                        help="Base branch (default: current branch)")
    parser.add_argument("--base-path", default=None,
                        help="Worktree base directory override")
    parser.add_argument("--branch-name", default=None,
                        help="Explicit branch name")

    pull_group = parser.add_mutually_exclusive_group()
    pull_group.add_argument("--pull", action="store_true", default=None,
                            dest="pull", help="Pull latest changes before creating worktree")
    pull_group.add_argument("--no-pull", action="store_false", dest="pull")

    recycle_group = parser.add_mutually_exclusive_group()
    recycle_group.add_argument("--recycle", action="store_true", default=None,
                               dest="recycle", help="Reuse an existing finished worktree")
    recycle_group.add_argument("--no-recycle", action="store_false", dest="recycle")

    launch_group = parser.add_mutually_exclusive_group()
    launch_group.add_argument("--launch", action="store_true", default=None,
                              dest="launch", help="Launch a new terminal session")
    launch_group.add_argument("--no-launch", action="store_false", dest="launch")

    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen, no changes")

    return parser.parse_args()


def main():
    args = parse_args()
    json_mode = args.json
    dry_run = args.dry_run

    # -----------------------------------------------------------------------
    # Step 1: Find repo root, validate not in worktree
    # -----------------------------------------------------------------------
    check_not_in_worktree()
    repo_root = find_repo_root()
    repo_name = repo_root.name
    main_repo_abs = str(repo_root)

    # -----------------------------------------------------------------------
    # Step 2: Load config cascade
    # -----------------------------------------------------------------------
    config = load_effective_config(main_repo_abs)
    wt_config = _deep_merge(dict(DEFAULT_WORKTREE_CONFIG), config.get("worktree", {}))

    # -----------------------------------------------------------------------
    # Step 3: Detect current branch
    # -----------------------------------------------------------------------
    if args.base_branch:
        base_branch = args.base_branch
    else:
        result = run_cmd(["git", "branch", "--show-current"], dry_run=False, cwd=main_repo_abs, capture=True)
        base_branch = result.stdout.strip() or "main"

    # -----------------------------------------------------------------------
    # Step 4-5: Check base branch freshness + pull
    # -----------------------------------------------------------------------
    sync_setting = wt_config.get("sync_before_create", "prompt")
    sync_summary = "skipped"
    pending_decisions = []

    if sync_setting != "never":
        # Fetch
        fetch_result = run_cmd(
            ["git", "fetch", "origin"], dry_run=dry_run, cwd=main_repo_abs, warn_only=True
        )
        fetch_ok = fetch_result.returncode == 0

        commits_behind = 0
        if fetch_ok and not dry_run:
            rev_result = subprocess.run(
                ["git", "rev-list", "--count", f"{base_branch}..origin/{base_branch}"],
                capture_output=True, text=True, cwd=main_repo_abs,
            )
            if rev_result.returncode == 0:
                try:
                    commits_behind = int(rev_result.stdout.strip())
                except ValueError:
                    commits_behind = 0

        if commits_behind == 0:
            sync_summary = "up to date"
        else:
            # Need to decide whether to pull
            resolved_pull, pending = resolve_prompt_setting(
                sync_setting, args.pull, "sync_before_create",
                default_when_auto=False,
            )
            if pending:
                pending["description"] = (
                    f"Local '{base_branch}' is {commits_behind} commits behind "
                    f"'origin/{base_branch}'. Pull latest changes?"
                )
                pending_decisions.append(pending)
            elif resolved_pull:
                run_cmd(
                    ["git", "pull", "origin", base_branch],
                    dry_run=dry_run, cwd=main_repo_abs, warn_only=True,
                )
                sync_summary = f"pulled {commits_behind} commits"
            else:
                sync_summary = f"{commits_behind} commits behind (skipped)"
    elif not dry_run:
        sync_summary = "skipped (never)"

    # -----------------------------------------------------------------------
    # Step 6: Generate task ID
    # -----------------------------------------------------------------------
    tasks_dir = get_tasks_dir(repo_root)
    task_id = get_next_task_id(tasks_dir)

    # -----------------------------------------------------------------------
    # Step 7: Create task directory + initial state
    # -----------------------------------------------------------------------
    task_dir = tasks_dir / task_id
    state = create_initial_state(task_id, args.description)

    # Link Jira issue if detected
    jira_key = extract_jira_key(args.description)
    if jira_key:
        state["linked_issue"] = jira_key

    if not dry_run:
        save_state(task_dir / "state.json", state)
    else:
        print(f"  [dry-run] Would create {task_dir}/state.json", file=sys.stderr)

    # -----------------------------------------------------------------------
    # Step 8: Resolve AI host, base path, branch name, color scheme
    # -----------------------------------------------------------------------
    # AI host
    ai_host = args.ai_host
    if not ai_host:
        cfg_host = wt_config.get("ai_host", "auto")
        if cfg_host == "auto":
            ai_host = "claude"  # default; agent overrides via --ai-host
        else:
            ai_host = cfg_host

    # WSL detection
    wsl = is_wsl()
    wsl_use_native = False
    warnings: list[str] = []

    # Base path
    base_path = args.base_path
    if not base_path:
        if wsl:
            wsl_native_path = wt_config.get("wsl_native_path", "")
            if wsl_native_path:
                wsl_native_path = wsl_native_path.replace("{user}", os.getenv("USER", ""))
                wsl_native_path = wsl_native_path.replace("{repo_name}", repo_name)
                base_path = wsl_native_path
        if not base_path:
            bp_template = wt_config.get("base_path", "../{repo_name}-worktrees")
            base_path = bp_template.replace("{repo_name}", repo_name)

    worktree_path = f"{base_path}/{task_id}"
    worktree_abs = os.path.normpath(os.path.join(main_repo_abs, worktree_path))

    if wsl and worktree_abs.startswith("/mnt/"):
        wsl_use_native = True
        warnings.append(
            "WSL performance warning: Worktree is on /mnt/ (NTFS via 9P bridge). "
            "Git and dependency commands will run via PowerShell (native Windows) to bypass 9P."
        )

    # Branch name
    if not args.branch_name:
        branch_name = generate_branch_name(task_id, state)
    else:
        branch_name = args.branch_name

    # Color scheme
    task_num_match = re.search(r'\d+', task_id)
    task_num = int(task_num_match.group()) if task_num_match else 0
    color_scheme_idx = task_num % len(CREW_COLOR_SCHEMES)
    color_scheme = CREW_COLOR_SCHEMES[color_scheme_idx]

    # -----------------------------------------------------------------------
    # Step 9: Resolve recycle setting + find recyclable worktree
    # -----------------------------------------------------------------------
    recycle_setting = wt_config.get("recycle", "prompt")
    resolved_recycle, recycle_pending = resolve_prompt_setting(
        recycle_setting, args.recycle, "recycle", default_when_auto=True,
    )
    if recycle_pending:
        pending_decisions.append(recycle_pending)

    donor = None
    recycled_from = None
    if resolved_recycle and not recycle_pending:
        donor = find_recyclable_worktree(tasks_dir, repo_root)

    # -----------------------------------------------------------------------
    # Resolve launch setting early (before exit-code-2 check)
    # -----------------------------------------------------------------------
    launch_setting = wt_config.get("auto_launch", "prompt")
    resolved_launch, launch_pending = resolve_prompt_setting(
        launch_setting, args.launch, "auto_launch", default_when_auto=True,
    )
    if launch_pending:
        pending_decisions.append(launch_pending)

    # -----------------------------------------------------------------------
    # Exit code 2: pending decisions
    # -----------------------------------------------------------------------
    if pending_decisions:
        if not dry_run:
            # Clean up the task dir we just created since we can't proceed
            state_file = task_dir / "state.json"
            if state_file.exists():
                state_file.unlink()
            if task_dir.exists():
                try:
                    task_dir.rmdir()
                except OSError:
                    pass
        output = {
            "success": False,
            "exit_code": 2,
            "pending_decisions": pending_decisions,
            "message": "Pending decisions need to be resolved. Re-run with the appropriate flags.",
        }
        if json_mode:
            print(json.dumps(output, indent=2))
        else:
            print("Pending decisions:", file=sys.stderr)
            for pd in pending_decisions:
                print(f"  - {pd['setting']}: {pd['description']}", file=sys.stderr)
            print("\nRe-run with the appropriate flags (e.g., --pull/--no-pull).", file=sys.stderr)
        sys.exit(2)

    # -----------------------------------------------------------------------
    # Step 10: Execute git worktree add (or recycle)
    # -----------------------------------------------------------------------
    setup_summary = ""

    if donor:
        donor_dir, donor_state = donor
        donor_worktree = donor_state["worktree"]
        donor_path = donor_worktree["path"]
        donor_branch = donor_worktree["branch"]
        donor_task_id = donor_state.get("task_id", donor_dir.name)
        recycled_from = donor_task_id

        # Update new task state
        state["worktree"] = {
            "status": "active",
            "path": worktree_path,
            "branch": branch_name,
            "base_branch": base_branch,
            "color_scheme_index": color_scheme_idx,
            "created_at": datetime.now().isoformat(),
            "recycled_from": donor_task_id,
        }
        if not dry_run:
            save_state(task_dir / "state.json", state)

        # Mark donor as recycled
        donor_state["worktree"]["status"] = "recycled"
        donor_state["worktree"]["recycled_to"] = task_id
        donor_state["worktree"]["recycled_at"] = datetime.now().isoformat()
        if not dry_run:
            save_state(donor_dir / "state.json", donor_state)

        # Git commands for recycling (use lists to handle paths with spaces)
        git_cmds = [
            (["git", "worktree", "move", donor_path, worktree_path], False),
            (["git", "-C", worktree_path, "checkout", base_branch], False),
            (["git", "-C", worktree_path, "checkout", "-b", branch_name], False),
            (["git", "branch", "-d", donor_branch], True),  # warn_only
        ]
        for cmd_parts, warn_only in git_cmds:
            if wsl_use_native:
                cmd_str = " ".join(f'"{p}"' if " " in p else p for p in cmd_parts)
                run_native_or_wsl(cmd_str, main_repo_abs, wsl_native=True,
                                  dry_run=dry_run, warn_only=warn_only)
            else:
                run_cmd(cmd_parts, dry_run, cwd=main_repo_abs, warn_only=warn_only)
    else:
        # Fresh worktree
        state["worktree"] = {
            "status": "active",
            "path": worktree_path,
            "branch": branch_name,
            "base_branch": base_branch,
            "color_scheme_index": color_scheme_idx,
            "created_at": datetime.now().isoformat(),
        }
        if not dry_run:
            save_state(task_dir / "state.json", state)

        git_parts = ["git", "worktree", "add", "-b", branch_name, worktree_path, base_branch]
        if wsl_use_native:
            cmd_str = " ".join(f'"{p}"' if " " in p else p for p in git_parts)
            run_native_or_wsl(cmd_str, main_repo_abs, wsl_native=True, dry_run=dry_run)
        else:
            run_cmd(git_parts, dry_run, cwd=main_repo_abs)

    # -----------------------------------------------------------------------
    # Step 11: Symlink .tasks/ + copy/patch host settings
    # -----------------------------------------------------------------------
    main_tasks_abs = os.path.join(main_repo_abs, ".tasks")

    # Symlink .tasks/ (falls back to NTFS junction on native Windows)
    symlink_target = os.path.join(worktree_abs, ".tasks")
    if not dry_run:
        if os.path.islink(symlink_target) or os.path.exists(symlink_target):
            _remove_symlink_or_junction(symlink_target)
        _symlink_or_junction(main_tasks_abs, symlink_target)
    else:
        print(f"  [dry-run] Would symlink {symlink_target} -> {main_tasks_abs}", file=sys.stderr)

    # Copy/patch host settings
    copy_settings = wt_config.get("copy_settings", True)
    if copy_settings:
        # Locate permissions template (check repo config/ and ~/.claude/config/)
        perms_tpl = ""
        for candidate in [
            os.path.join(main_repo_abs, "config", "worktree-permissions.json"),
            os.path.expanduser("~/.claude/config/worktree-permissions.json"),
        ]:
            if os.path.isfile(candidate):
                perms_tpl = candidate
                break

        for settings_file in HOST_SETTINGS.get(ai_host, []):
            if settings_file == "gemini_trust":
                # Special: add worktree to Gemini trustedFolders.json
                trust_cmd = (
                    f"python3 -c {shlex.quote(GEMINI_TRUST_SCRIPT)} "
                    f"{shlex.quote(worktree_abs)}"
                )
                run_cmd_shell(trust_cmd, dry_run, warn_only=True)
                continue
            src = os.path.join(main_repo_abs, settings_file)
            dest = os.path.join(worktree_abs, settings_file)
            patch_cmd = (
                f"python3 -c {shlex.quote(SETTINGS_PATCH_SCRIPT)} "
                f"{shlex.quote(src)} {shlex.quote(dest)} {shlex.quote(main_tasks_abs)}"
            )
            if perms_tpl:
                patch_cmd += f" {shlex.quote(perms_tpl)}"
            run_cmd_shell(patch_cmd, dry_run, warn_only=True)
        setup_summary = ".tasks/ symlinked, settings copied"
    else:
        setup_summary = ".tasks/ symlinked, settings copy skipped"

    # Copy workflow config if it exists (untracked project-level overrides)
    WORKFLOW_CONFIG_PATHS = [
        ".claude/workflow-config.yaml",
        ".copilot/workflow-config.yaml",
        ".gemini/workflow-config.yaml",
        ".config/opencode/workflow-config.yaml",
        ".opencode/workflow-config.yaml",
    ]
    configs_copied = 0
    for wf_config in WORKFLOW_CONFIG_PATHS:
        src = os.path.join(main_repo_abs, wf_config)
        dest = os.path.join(worktree_abs, wf_config)
        if os.path.isfile(src) and not os.path.isfile(dest):
            if not dry_run:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)
                configs_copied += 1
            else:
                print(f"  [dry-run] Would copy {src} -> {dest}", file=sys.stderr)
                configs_copied += 1
    if configs_copied:
        setup_summary += f", {configs_copied} workflow config(s) copied"

    # -----------------------------------------------------------------------
    # Step 12: Fix paths for WSL/Windows compatibility
    # -----------------------------------------------------------------------
    paths_fixed = False
    if wsl and worktree_abs.startswith("/mnt/"):
        fix_script = os.path.join(main_repo_abs, "scripts", "fix-worktree-paths.py")
        if os.path.isfile(fix_script):
            run_cmd(["python3", fix_script, task_id], dry_run, cwd=main_repo_abs, warn_only=True)
            paths_fixed = True

    # -----------------------------------------------------------------------
    # Step 13: Install dependencies
    # -----------------------------------------------------------------------
    install_setting = wt_config.get("install_deps", "auto")
    deps_summary = "skipped"

    if install_setting == "never":
        deps_summary = "skipped (config)"
    elif recycled_from:
        deps_summary = "skipped (recycled)"
    else:
        # Detect lockfile in worktree
        installers = LOCKFILE_INSTALLERS_WIN if wsl_use_native else LOCKFILE_INSTALLERS
        for lockfile, install_cmd in installers:
            lockfile_path = os.path.join(worktree_abs, lockfile)
            if dry_run or os.path.isfile(lockfile_path):
                if dry_run:
                    print(f"  [dry-run] Would check for {lockfile_path}", file=sys.stderr)
                result = run_native_or_wsl(
                    install_cmd, worktree_abs, wsl_use_native, dry_run, warn_only=True
                )
                if dry_run or result.returncode == 0:
                    deps_summary = install_cmd.split()[0]  # e.g., "npm"
                else:
                    deps_summary = f"failed ({install_cmd.split()[0]})"
                break

    # -----------------------------------------------------------------------
    # Step 14: Run post_setup_commands
    # -----------------------------------------------------------------------
    post_setup_cmds = wt_config.get("post_setup_commands", [])
    post_setup_summary = "skipped (none configured)"

    if post_setup_cmds:
        ran = 0
        failed = 0
        for cmd_template in post_setup_cmds:
            cmd = cmd_template
            cmd = cmd.replace("{worktree_path}", worktree_abs)
            cmd = cmd.replace("{task_id}", task_id)
            cmd = cmd.replace("{branch_name}", branch_name)
            cmd = cmd.replace("{main_repo_path}", main_repo_abs)
            cmd = cmd.replace("{jira_issue}", jira_key or "")

            # Always run in bash — these are user-written bash commands with
            # WSL paths.  Routing through PowerShell (wsl_use_native) would
            # silently fail because PS doesn't understand mkdir -p, /mnt/
            # paths, etc.
            result = run_cmd_shell(cmd, dry_run, cwd=worktree_abs, warn_only=True)
            if not dry_run and result.returncode != 0:
                failed += 1
                print(f"  ⚠ post_setup command failed (exit {result.returncode}): {cmd_template}", file=sys.stderr)
                if result.stderr:
                    print(f"    {result.stderr.strip()}", file=sys.stderr)
            ran += 1
        if failed:
            post_setup_summary = f"{ran} commands ran, {failed} failed"
        else:
            post_setup_summary = f"{ran} commands ran"

    # -----------------------------------------------------------------------
    # Step 15-16: Detect terminal env + build launch commands + execute
    # -----------------------------------------------------------------------
    main_tasks_path = os.path.join(main_repo_abs, ".tasks", task_id)
    resume_prompt = build_resume_prompt(task_id, main_tasks_path, ai_host)

    terminal_env = detect_terminal_env()
    launch_commands, launch_warnings = build_launch_commands(
        task_id, worktree_abs, ai_host, terminal_env, resume_prompt, color_scheme
    )
    warnings.extend(launch_warnings)

    launched = False
    if resolved_launch and launch_commands:
        for cmd in launch_commands:
            run_cmd_shell(cmd, dry_run, warn_only=True)
        launched = True

        # Record launch in state
        if not dry_run:
            state["worktree"]["launch"] = {
                "terminal_env": terminal_env,
                "ai_host": ai_host,
                "launched_at": datetime.now().isoformat(),
                "worktree_abs_path": worktree_abs,
                "color_scheme": color_scheme["name"],
            }
            save_state(task_dir / "state.json", state)

    # -----------------------------------------------------------------------
    # Step 17: Output result
    # -----------------------------------------------------------------------
    # Build Jira section for output
    jira_output = None
    if jira_key:
        jira_config = wt_config.get("jira", {})
        jira_output = {
            "issue_key": jira_key,
            "config": {
                "auto_assign": jira_config.get("auto_assign", "never"),
                "transitions": jira_config.get("transitions", {}),
            },
        }

    result = {
        "success": True,
        "task_id": task_id,
        "worktree_path": worktree_abs,
        "branch_name": branch_name,
        "base_branch": base_branch,
        "recycled_from": recycled_from,
        "main_repo_path": main_repo_abs,
        "summary": {
            "sync": sync_summary,
            "setup": setup_summary,
            "deps": deps_summary,
            "post_setup": post_setup_summary,
            "paths_fixed": paths_fixed,
        },
        "jira": jira_output,
        "launch": {
            "terminal_env": terminal_env,
            "commands": launch_commands,
            "resume_prompt": resume_prompt,
            "color_scheme": color_scheme["name"],
            "launched": launched,
            "warnings": launch_warnings,
        },
        "resume_prompt": resume_prompt,
        "warnings": warnings,
    }

    if json_mode:
        print(json.dumps(result, indent=2))
    else:
        # Human-readable output
        print(f"\nWorktree ready:")
        print(f"  Task:       {task_id}")
        print(f"  Directory:  {worktree_abs}")
        print(f"  Branch:     {branch_name} (based on {base_branch})")
        if recycled_from:
            print(f"  Recycled:   yes, from {recycled_from}")
        else:
            print(f"  Recycled:   no (fresh)")
        print(f"  Task state: {main_repo_abs}/.tasks/{task_id}/")
        print(f"  Setup:      {setup_summary}")
        if jira_key:
            print(f"  Jira:       {jira_key} (agent handles assign/transition)")
        else:
            print(f"  Jira:       skipped (no Jira key)")
        print(f"  Deps:       {deps_summary}")
        print(f"  Post-setup: {post_setup_summary}")
        if paths_fixed:
            print(f"  Paths:      fixed for WSL/Windows")
        if launched:
            print(f"  Launch:     {terminal_env} session launched")
        print()

        if not launched:
            print("To start the workflow, open a new terminal and run:")
            print()
            print(f"  cd {worktree_abs}")
            print()
            print(f"Then start your AI assistant ({ai_host}) and give it this prompt:")
            print()
            print(f"  {resume_prompt}")
        print()


if __name__ == "__main__":
    main()
