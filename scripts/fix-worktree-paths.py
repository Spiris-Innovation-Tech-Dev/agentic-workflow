#!/usr/bin/env python3
"""
Convert absolute WSL paths to relative paths in git worktree files.

Usage:
    python3 scripts/fix-worktree-paths.py TASK_XXX [--dry-run]

After `git worktree add`, the worktree's .git file and the main repo's
.git/worktrees/TASK_XXX/gitdir contain absolute WSL paths (e.g.,
/mnt/c/git/repo-worktrees/TASK_XXX). Windows tools (Visual Studio,
PowerShell git, etc.) cannot read these paths. This script converts both
to relative paths with LF line endings.

Guard: Only runs on WSL + /mnt/ paths. On native Linux or /home/ paths,
prints "No fix needed" and exits 0.
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from shared_utils import is_wsl, find_repo_root
except ImportError:
    def is_wsl() -> bool:
        """Detect if running under WSL."""
        try:
            with open("/proc/version") as f:
                return "microsoft" in f.read().lower()
        except OSError:
            return False

    def find_repo_root() -> Path:
        """Walk up from CWD looking for .git/ directory (main repo)."""
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


def load_state(state_file: Path) -> dict:
    """Load and return state.json contents."""
    if not state_file.exists():
        print(f"Error: State file not found: {state_file}", file=sys.stderr)
        sys.exit(1)
    with open(state_file) as f:
        return json.load(f)


def write_file_lf(path: str, content: str, dry_run: bool) -> bool:
    """Write content with LF line endings (no CRLF). Returns True on success."""
    if dry_run:
        print(f"  [dry-run] Would write to {path}:")
        print(f"            {content.strip()}")
        return True
    try:
        with open(path, "w", newline="\n") as f:
            f.write(content)
        return True
    except OSError as e:
        print(f"  Error writing {path}: {e}", file=sys.stderr)
        return False


def verify_file(path: str, expected_content: str) -> bool:
    """Read back a file and verify its content matches."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        # Check no CRLF
        if b"\r\n" in data:
            print(f"  Warning: {path} contains CRLF line endings!", file=sys.stderr)
            return False
        actual = data.decode("utf-8").strip()
        expected = expected_content.strip()
        if actual != expected:
            print(f"  Warning: {path} content mismatch!", file=sys.stderr)
            print(f"    Expected: {expected}", file=sys.stderr)
            print(f"    Actual:   {actual}", file=sys.stderr)
            return False
        return True
    except OSError as e:
        print(f"  Warning: Could not verify {path}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Convert absolute WSL paths to relative in git worktree files"
    )
    parser.add_argument("task_id", help="Task identifier (e.g., TASK_001)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen without making changes")
    args = parser.parse_args()

    # Guard: only on WSL
    if not is_wsl():
        print("No fix needed: not running under WSL.")
        sys.exit(0)

    # Find repo root
    repo_root = find_repo_root()
    repo_root_str = str(repo_root)

    # Load task state to get worktree path
    task_dir = repo_root / ".tasks" / args.task_id
    state_file = task_dir / "state.json"
    state = load_state(state_file)

    worktree = state.get("worktree")
    if not worktree:
        print(f"Error: No worktree configured for {args.task_id}", file=sys.stderr)
        sys.exit(1)

    worktree_path = worktree.get("path", "")
    if not worktree_path:
        print(f"Error: No worktree path in state for {args.task_id}", file=sys.stderr)
        sys.exit(1)

    # Resolve absolute worktree path
    worktree_abs = os.path.normpath(os.path.join(repo_root_str, worktree_path))

    # Guard: only fix /mnt/ paths (NTFS via 9P)
    if not worktree_abs.startswith("/mnt/"):
        print(f"No fix needed: worktree path is not on /mnt/ ({worktree_abs}).")
        sys.exit(0)

    # Paths to fix:
    # 1. <worktree>/.git — should contain "gitdir: <relative path to .git/worktrees/TASK_XXX>"
    # 2. <repo>/.git/worktrees/TASK_XXX/gitdir — should contain relative path to worktree/.git
    worktree_git_file = os.path.join(worktree_abs, ".git")
    git_worktrees_entry = os.path.join(repo_root_str, ".git", "worktrees", args.task_id)
    gitdir_file = os.path.join(git_worktrees_entry, "gitdir")

    print(f"Fixing worktree paths for {args.task_id}:")
    print(f"  Repo root:      {repo_root_str}")
    print(f"  Worktree:       {worktree_abs}")
    print(f"  .git file:      {worktree_git_file}")
    print(f"  gitdir file:    {gitdir_file}")
    if args.dry_run:
        print(f"  *** DRY RUN — no changes will be made ***")
    print()

    # Check that the worktree directory and git entries exist
    if not os.path.isdir(worktree_abs):
        print(f"Error: Worktree directory does not exist: {worktree_abs}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(git_worktrees_entry):
        print(f"Error: Git worktrees entry does not exist: {git_worktrees_entry}", file=sys.stderr)
        sys.exit(1)

    # Compute relative paths
    # From worktree dir → .git/worktrees/TASK_XXX
    rel_wt_to_git = os.path.relpath(git_worktrees_entry, worktree_abs)
    # From .git/worktrees/TASK_XXX → worktree/.git
    rel_git_to_wt = os.path.relpath(
        os.path.join(worktree_abs, ".git"), git_worktrees_entry
    )

    print(f"  Relative paths:")
    print(f"    .git file content:  gitdir: {rel_wt_to_git}")
    print(f"    gitdir content:     {rel_git_to_wt}")
    print()

    # Write the .git file (worktree → main repo)
    git_file_content = f"gitdir: {rel_wt_to_git}\n"
    ok1 = write_file_lf(worktree_git_file, git_file_content, args.dry_run)

    # Write the gitdir file (main repo → worktree)
    gitdir_content = f"{rel_git_to_wt}\n"
    ok2 = write_file_lf(gitdir_file, gitdir_content, args.dry_run)

    if not ok1 or not ok2:
        print("\nError: Failed to write one or more files.", file=sys.stderr)
        sys.exit(1)

    # Verify
    if not args.dry_run:
        print("Verifying...")
        v1 = verify_file(worktree_git_file, git_file_content)
        v2 = verify_file(gitdir_file, gitdir_content)
        if v1 and v2:
            print("  Both files verified OK.")
        else:
            print("\nWarning: Verification failed for one or more files.", file=sys.stderr)
            sys.exit(1)

    print(f"\nDone. Worktree paths for {args.task_id} are now relative.")


if __name__ == "__main__":
    main()
