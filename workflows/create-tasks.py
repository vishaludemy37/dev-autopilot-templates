#!/usr/bin/env python3
"""
Breaks client requirements into actionable development tasks.

Usage:
    python workflows/create-tasks.py --requirement "Add user authentication"
    python workflows/create-tasks.py --requirement "Fix column detection" --priority High
"""

import math
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
KNOWLEDGE_FILE = PROJECT_ROOT / "knowledge" / "{{PROJECT_NAME}}-project.md"
TASKS_DIR = SCRIPT_DIR / "tasks"
TODAY = datetime.now().strftime("%Y-%m-%d")
TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# File mapping: keyword -> likely files to change
# Customize this for your project's file structure
FILE_MAPPING = {
    "frontend": ["src/"],
    "backend": ["src/"],
    "api": ["src/"],
    "config": ["config/"],
    "deploy": ["Dockerfile", "docker-compose.yml"],
    "test": ["tests/"],
    "style": ["src/"],
    "database": ["src/"],
    "auth": ["src/"],
    "ui": ["src/"],
    "fix": ["src/"],
    "bug": ["src/"],
    "feature": ["src/"],
    "refactor": ["src/"],
}


def get_files_for_task(task_text):
    lower = task_text.lower()
    files = []
    for key, vals in FILE_MAPPING.items():
        if key in lower:
            files.extend(vals)
    files = list(dict.fromkeys(files))  # dedupe preserving order
    if not files:
        files = ["src/ (review)"]
    return files


def get_estimated_hours(task_text):
    lower = task_text.lower()
    if re.search(r"fix|bug|tweak|adjust", lower):
        return "1-2"
    if re.search(r"refactor|rewrite|overhaul", lower):
        return "3-5"
    if re.search(r"add|create|implement|build|new", lower):
        return "2-4"
    if re.search(r"deploy|setup|configure", lower):
        return "2-3"
    if re.search(r"test|validate", lower):
        return "1-2"
    if re.search(r"design|plan|research", lower):
        return "1-2"
    return "2-3"


def get_task_priority(task_text, default):
    lower = task_text.lower()
    if re.search(r"critical|urgent|blocker|security|crash", lower):
        return "High"
    if re.search(r"nice to have|optional|cosmetic|minor", lower):
        return "Low"
    return default


def main():
    requirement = None
    priority = "Medium"

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--requirement" and i + 1 < len(sys.argv):
            requirement = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--priority" and i + 1 < len(sys.argv):
            priority = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    if not requirement:
        print("Usage: python create-tasks.py --requirement \"text\" [--priority High|Medium|Low]")
        sys.exit(1)

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = TASKS_DIR / f"{TODAY}_tasks.md"

    # Load project knowledge
    if KNOWLEDGE_FILE.exists():
        print(f"[OK] Loaded project knowledge from {KNOWLEDGE_FILE}")
    else:
        print(f"[WARN] Knowledge file not found at {KNOWLEDGE_FILE}")

    # Parse requirement into tasks
    print(f"\n--- Breaking down requirement ---")
    print(f"Input: {requirement}\n")

    # Split by common delimiters
    raw_tasks = [t.strip() for t in re.split(r'[.;]|\band\b', requirement) if len(t.strip()) > 5]

    # If only one chunk, try commas
    if len(raw_tasks) <= 1:
        raw_tasks = [t.strip() for t in requirement.split(',') if len(t.strip()) > 5]

    # If still one chunk, treat whole thing as single task
    if not raw_tasks:
        raw_tasks = [requirement]

    # Build task list
    tasks = []
    for num, raw in enumerate(raw_tasks, 1):
        files = get_files_for_task(raw)
        hours = get_estimated_hours(raw)
        prio = get_task_priority(raw, priority)
        tasks.append({
            "number": num,
            "title": raw[:80],
            "description": raw,
            "files": ", ".join(files),
            "hours": hours,
            "priority": prio,
            "status": "Pending"
        })

    # Calculate total hours
    total_hours = sum(int(t["hours"].split("-")[-1]) for t in tasks)

    # Generate markdown
    markdown = f"""# Task Breakdown - {TODAY}

## Client Requirement
> {requirement}

## Summary
- **Total tasks**: {len(tasks)}
- **Estimated total hours**: {total_hours} hrs (upper bound)
- **Default priority**: {priority}
- **Generated**: {TIMESTAMP}

---

## Tasks
"""

    for task in tasks:
        markdown += f"""
### Task {task['number']}: {task['title']}

| Field | Value |
|---|---|
| **Priority** | {task['priority']} |
| **Status** | {task['status']} |
| **Estimated Hours** | {task['hours']} |
| **Files to Change** | {task['files']} |

**Description**: {task['description']}

---
"""

    markdown += f"""
## Notes
- Estimates are rough -- adjust based on actual complexity
- Check the project knowledge file for project context and known issues
- Update task status as you work: Pending -> In Progress -> Done
"""

    # Write output
    if output_file.exists():
        existing = output_file.read_text(encoding="utf-8")
        markdown = existing + "\n\n---\n\n" + markdown
        output_file.write_text(markdown, encoding="utf-8")
        print(f"[OK] Appended tasks to {output_file}")
    else:
        output_file.write_text(markdown, encoding="utf-8")
        print(f"[OK] Saved tasks to {output_file}")

    # Console summary
    print(f"\n--- Task Summary ---")
    for task in tasks:
        print(f"  [{task['priority']}] Task {task['number']}: {task['title']}")
        print(f"         Files: {task['files']}")
        print(f"         Hours: {task['hours']}")
    print(f"\nTotal: {len(tasks)} tasks, ~{total_hours} hrs")
    print(f"Output: {output_file}\n")


if __name__ == "__main__":
    main()
