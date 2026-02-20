#!/usr/bin/env python3
"""
Install Crew color schemes into Windows Terminal settings.

Usage:
    python3 scripts/install-wt-colorschemes.py

Only runs on WSL. Exits silently with code 0 if not on WSL or if
Windows Terminal is not found.
"""

import json
import os
import subprocess
import sys


def is_wsl() -> bool:
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except (OSError, FileNotFoundError):
        return False


def find_wt_settings() -> str | None:
    """Find Windows Terminal settings.json path."""
    try:
        username = subprocess.run(
            ["cmd.exe", "/C", "echo", "%USERNAME%"],
            capture_output=True, text=True
        ).stdout.strip()
    except (FileNotFoundError, OSError):
        username = os.getenv("USER", "")

    candidates = [
        f"/mnt/c/Users/{username}/AppData/Local/Packages/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json",
        f"/mnt/c/Users/{username}/AppData/Local/Packages/Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe/LocalState/settings.json",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def main():
    if not is_wsl():
        print("Not running in WSL, skipping.")
        return

    # Find schemes file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    schemes_file = os.path.join(repo_root, "config", "terminal-colorschemes.json")

    if not os.path.isfile(schemes_file):
        print(f"Color schemes file not found: {schemes_file}")
        return

    wt_settings = find_wt_settings()
    if not wt_settings:
        print("Windows Terminal settings.json not found, skipping.")
        return

    with open(schemes_file) as f:
        crew_schemes = json.load(f)

    # Read WT settings (strip // comments)
    with open(wt_settings) as f:
        lines = f.readlines()
    clean_lines = [line for line in lines if not line.strip().startswith("//")]
    settings = json.loads("".join(clean_lines))

    if "schemes" not in settings:
        settings["schemes"] = []

    existing_names = {s.get("name") for s in settings["schemes"]}
    added = 0
    for scheme in crew_schemes:
        if scheme["name"] not in existing_names:
            settings["schemes"].append(scheme)
            added += 1

    if added > 0:
        with open(wt_settings, "w") as f:
            json.dump(settings, f, indent=4)
            f.write("\n")
        print(f"Added {added} Crew color schemes to Windows Terminal")
    else:
        print("Crew color schemes already present in Windows Terminal")


if __name__ == "__main__":
    main()
