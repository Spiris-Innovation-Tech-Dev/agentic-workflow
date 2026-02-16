#!/usr/bin/env python3
"""
Remove a git worktree for a workflow task.

Usage:
    python3 scripts/cleanup-worktree.py TASK_XXX [--keep-on-disk] [--remove-branch] [--dry-run]

Main-repo guard: refuses to run from inside a worktree (.git must be a directory).

Steps (normal):
    1. Detect repo root from CWD
    2. Load .tasks/TASK_XXX/state.json, validate worktree status is active
    3. git worktree remove <path>
    4. If --remove-branch: git branch -d <branch>
    5. Update state: worktree.status = "cleaned", worktree.cleaned_at = now
    6. Print summary

--keep-on-disk: skip git worktree remove, set status to "recyclable" instead.
--dry-run: print what would happen, change nothing.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


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


def check_not_in_worktree():
    """Refuse to run from inside a worktree. .git must be a directory, not a file."""
    git_path = Path(".git")
    if git_path.is_file():
        print(
            "Error: Cannot remove worktrees from within a worktree. "
            "Run from the main repo.",
            file=sys.stderr,
        )
        sys.exit(1)


def load_state(state_file: Path) -> dict:
    """Load and return state.json contents."""
    if not state_file.exists():
        print(f"Error: State file not found: {state_file}", file=sys.stderr)
        sys.exit(1)
    with open(state_file) as f:
        return json.load(f)


def save_state(state_file: Path, state: dict):
    """Write state back to state.json."""
    state["updated_at"] = datetime.now().isoformat()
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def run_git(args: list[str], dry_run: bool) -> bool:
    """Run a git command. Returns True on success."""
    cmd_str = " ".join(args)
    if dry_run:
        print(f"  [dry-run] Would run: {cmd_str}")
        return True
    print(f"  Running: {cmd_str}")
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Warning: Command failed: {result.stderr.strip()}", file=sys.stderr)
        return False
    if result.stdout.strip():
        print(f"  {result.stdout.strip()}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Remove a git worktree for a workflow task")
    parser.add_argument("task_id", help="Task identifier (e.g., TASK_001)")
    parser.add_argument("--keep-on-disk", action="store_true",
                        help="Skip git worktree remove, mark as recyclable instead")
    parser.add_argument("--remove-branch", action="store_true",
                        help="Also delete the feature branch")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen without making changes")
    args = parser.parse_args()

    # Guard: must be in the main repo, not a worktree
    check_not_in_worktree()

    # Find repo root
    repo_root = find_repo_root()

    # Load task state
    task_dir = repo_root / ".tasks" / args.task_id
    state_file = task_dir / "state.json"
    state = load_state(state_file)

    # Validate worktree status
    worktree = state.get("worktree")
    if not worktree:
        print(f"Error: No worktree configured for {args.task_id}", file=sys.stderr)
        sys.exit(1)

    status = worktree.get("status")
    if status in ("cleaned", "recyclable"):
        print(f"Error: Worktree already {status} for {args.task_id}", file=sys.stderr)
        sys.exit(1)

    if status != "active":
        print(f"Error: Unexpected worktree status '{status}' for {args.task_id}", file=sys.stderr)
        sys.exit(1)

    worktree_path = worktree["path"]
    branch_name = worktree.get("branch", "")

    # Resolve worktree path relative to repo root
    worktree_abs = os.path.normpath(os.path.join(str(repo_root), worktree_path))

    print(f"Cleaning up worktree for {args.task_id}:")
    print(f"  Path:   {worktree_path}")
    print(f"  Branch: {branch_name}")
    print(f"  Mode:   {'keep-on-disk (recyclable)' if args.keep_on_disk else 'remove'}")
    if args.dry_run:
        print(f"  *** DRY RUN — no changes will be made ***")
    print()

    if args.keep_on_disk:
        # Mark as recyclable — skip git worktree remove
        if args.remove_branch and branch_name:
            run_git(["git", "branch", "-d", branch_name], args.dry_run)

        new_status = "recyclable"
    else:
        # Remove worktree from disk
        ok = run_git(["git", "worktree", "remove", worktree_abs], args.dry_run)
        if not ok and not args.dry_run:
            print("\nError: git worktree remove failed. State NOT updated.", file=sys.stderr)
            sys.exit(1)

        if args.remove_branch and branch_name:
            # Branch deletion failure is a warning, not fatal
            run_git(["git", "branch", "-d", branch_name], args.dry_run)

        new_status = "cleaned"

    # Update state
    if not args.dry_run:
        state["worktree"]["status"] = new_status
        state["worktree"]["cleaned_at"] = datetime.now().isoformat()
        save_state(state_file, state)
        print(f"\nState updated: worktree.status = {new_status}")
    else:
        print(f"\n  [dry-run] Would update state: worktree.status = {new_status}")

    print(f"\nDone. Worktree for {args.task_id} is now {new_status}.")


if __name__ == "__main__":
    main()
