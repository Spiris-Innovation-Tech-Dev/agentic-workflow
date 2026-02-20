#!/usr/bin/env python3
"""
Add a directory to Gemini CLI trustedFolders.json.

Usage:
    python3 scripts/gemini-trust.py /path/to/directory
"""

import json
import os
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 gemini-trust.py <directory_path>", file=sys.stderr)
        sys.exit(1)

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
            f.write("\n")
        print(f"Added {worktree_abs} to Gemini trustedFolders")
    else:
        print(f"{worktree_abs} already trusted")


if __name__ == "__main__":
    main()
