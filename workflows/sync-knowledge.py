#!/usr/bin/env python3
"""
Syncs knowledge file with recent codebase changes.

Scans git log for recently changed files, reads their contents, and outputs
a structured report to stdout. Claude Code reads the output and updates
the knowledge file directly. NEVER removes existing sections.

Usage:
    python workflows/sync-knowledge.py
    python workflows/sync-knowledge.py --since "3 days ago"
"""

import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
KNOWLEDGE_FILE = PROJECT_DIR / "knowledge" / "{{PROJECT_NAME}}-project.md"


def sanitize_to_ascii(text):
    text = text.replace("\u2014", "--").replace("\u2013", "--")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2026", "...").replace("\u2192", "->").replace("\u2190", "<-")
    return re.sub(r'[^\x00-\x7f]', '', text)


def run_git(*args):
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(PROJECT_DIR)
    )
    return result.stdout.strip(), result.returncode


def main():
    since = "1 week ago"
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--since" and i < len(sys.argv) - 1:
            since = sys.argv[i + 1]

    print()
    print("  ========================================")
    print("    KNOWLEDGE SYNC")
    print("  ========================================")
    print(f"  Scanning changes since: {since}")
    print()

    # Check prerequisites
    if not KNOWLEDGE_FILE.exists():
        print(f"  [ERROR] Knowledge file not found: {KNOWLEDGE_FILE}")
        sys.exit(1)

    out, rc = run_git("rev-parse", "--is-inside-work-tree")
    if rc != 0:
        print(f"  [ERROR] Not a git repository: {PROJECT_DIR}")
        sys.exit(1)

    # Step 1: Get recently changed files
    print("  STEP 1: Scanning git log")
    print("  ----------------------------------------")

    out, _ = run_git("log", f"--since={since}", "--name-only", "--pretty=format:",
                     "--", "*.py", "*.js", "*.html", "*.css", "*.md")
    changed_files = sorted(set(f for f in out.splitlines() if f.strip()))

    exclude_patterns = [
        "workflows/tasks/",
        "workflows/testing/",
        "workflows/reports/",
        "knowledge/{{PROJECT_NAME}}-project.md"
    ]

    filtered = []
    for f in changed_files:
        skip = False
        for pat in exclude_patterns:
            if pat.replace("/", os.sep) in f or pat in f:
                skip = True
                break
        if not skip and (PROJECT_DIR / f).exists():
            filtered.append(f)

    if not filtered:
        print(f"  No code changes found since '{since}'.")
        print("  Knowledge file is up to date.")
        sys.exit(0)

    print(f"  Found {len(filtered)} changed file(s):")
    for f in filtered:
        print(f"    - {f}")
    print()

    # Step 2: Commit summaries
    print("  STEP 2: Reading commit history")
    print("  ----------------------------------------")

    out, _ = run_git("log", f"--since={since}", "--oneline", "--no-merges")
    commit_lines = [l for l in out.splitlines() if l.strip()]
    commit_count = len(commit_lines)

    print(f"  {commit_count} commit(s) in range:")
    for line in commit_lines[:10]:
        print(f"    {line}")
    if commit_count > 10:
        print(f"    ... and {commit_count - 10} more")
    print()

    # Step 3: Read file contents
    print("  STEP 3: Reading changed files")
    print("  ----------------------------------------")

    files_to_read = filtered[:15]
    print(f"  Reading {len(files_to_read)} file(s)...")
    print()

    current_content = KNOWLEDGE_FILE.read_text(encoding="utf-8")
    commit_summary = "\n".join(commit_lines[:15])

    # Output structured report
    print()
    print("===KNOWLEDGE_SYNC_REPORT_START===")
    print()
    print("## Recent Commits")
    print(commit_summary)
    print()
    print("## Changed Files")
    print()

    for f in files_to_read:
        full_path = PROJECT_DIR / f
        if full_path.exists():
            try:
                content = full_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            content = sanitize_to_ascii(content)
            lines = content.split("\n")
            if len(lines) > 200:
                content = "\n".join(lines[:200])
                content += f"\n... (truncated, {len(lines)} total lines)"
            print(f"### FILE: {f}")
            print("```")
            print(content)
            print("```")
            print()

    print("## Current Knowledge File")
    print("```")
    print(current_content)
    print("```")
    print()
    print("===KNOWLEDGE_SYNC_REPORT_END===")
    print()
    print("  Report generated. Claude Code will now analyze and update the knowledge file.")
    print()


if __name__ == "__main__":
    main()
