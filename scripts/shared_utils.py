#!/usr/bin/env python3
"""
Shared utilities for agentic-workflow scripts.

NOTE: setup-worktree.py inlines its own copies of these functions to remain
standalone. Keep the inlined versions in sync with these.
"""

import os
import sys
from pathlib import Path


def is_wsl() -> bool:
    """Detect if running under WSL."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except (OSError, FileNotFoundError, PermissionError):
        return False


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
    print("Error: Could not find repo root (no .git/ directory found).", file=sys.stderr)
    sys.exit(1)
