#!/usr/bin/env python3
"""
Generate a Functional Requirement Document (FRD) for a given REQ ID.
Outputs structured data for Claude Code to generate the full document.

Usage:
    python workflows/generate-frd.py --req-id REQ-001
"""

import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
REQS_DIR = SCRIPT_DIR / "requirements"
TASKS_DIR = SCRIPT_DIR / "tasks"
FRD_DIR = SCRIPT_DIR / "frd"
KNOWLEDGE_FILE = PROJECT_DIR / "knowledge" / "{{PROJECT_NAME}}-project.md"


def sanitize_to_ascii(text):
    text = text.replace("\u2014", "--").replace("\u2013", "--")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2026", "...").replace("\u2192", "->").replace("\u2190", "<-")
    return re.sub(r'[^\x00-\x7f]', '', text)


def read_file(path):
    return Path(path).read_text(encoding="utf-8")


def main():
    # Parse args
    req_id = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--req-id" and i < len(sys.argv) - 1:
            req_id = sys.argv[i + 1]

    if not req_id:
        print("  Usage: python workflows/generate-frd.py --req-id REQ-001")
        sys.exit(1)

    # Ensure FRD directory exists
    FRD_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Find and read the requirement
    req_found = False
    req_client = req_channel = req_date = req_status = req_text = ""
    req_file = ""

    if REQS_DIR.exists():
        for rf in sorted(REQS_DIR.glob("*_requirements.md"), reverse=True):
            content = read_file(rf)
            pattern = rf"(?s)### {re.escape(req_id)}\s*\n(.*?)(?=\n---|\Z)"
            m = re.search(pattern, content)
            if m:
                block = m.group(1)
                req_found = True
                req_file = str(rf)

                for field, var_name in [("Client", "client"), ("Channel", "channel"),
                                         ("Date", "date"), ("Status", "status")]:
                    fm = re.search(rf'\*\*{field}\*\*\s*\|\s*([^|]+)', block)
                    if fm:
                        if var_name == "client":
                            req_client = fm.group(1).strip()
                        elif var_name == "channel":
                            req_channel = fm.group(1).strip()
                        elif var_name == "date":
                            req_date = fm.group(1).strip()
                        elif var_name == "status":
                            req_status = fm.group(1).strip()

                rm = re.search(r'\*\*Requirement\*\*:\s*(.+)', block)
                if rm:
                    req_text = rm.group(1).strip()
                break

    if not req_found:
        print(f"  ERROR: {req_id} not found in any requirements file.")
        sys.exit(1)

    print(f"  ========================================")
    print(f"  GENERATING FRD: {req_id}")
    print(f"  ========================================")
    print()
    print(f"  Requirement: {req_text}")
    print(f"  Client: {req_client}")
    print(f"  Status: {req_status}")

    # Step 2: Find linked tasks
    linked_tasks = []

    if TASKS_DIR.exists():
        for tf in sorted(TASKS_DIR.glob("*_tasks.md"), reverse=True):
            tf_content = read_file(tf)
            task_matches = re.finditer(
                r"(?s)### Task (\d+):\s*(.+?)\n(.*?)(?=\n### Task|\n---\s*\n## |\n---\s*$|\Z)",
                tf_content
            )
            for tm in task_matches:
                task_num = tm.group(1)
                task_title = tm.group(2).strip()
                task_block = tm.group(3)

                is_linked = bool(re.search(r'\*\*Source\*\*\s*\|\s*' + re.escape(req_id), task_block))
                if not is_linked:
                    pat2 = rf"(?s)### {re.escape(req_id)}.*?Tasks:.*?Task {task_num}"
                    if re.search(pat2, tf_content):
                        is_linked = True

                if is_linked:
                    files2change = ""
                    fm = re.search(r'\*\*Files to Change\*\*\s*\|\s*([^|]+)', task_block)
                    if fm:
                        files2change = fm.group(1).strip()
                    task_status = "Pending"
                    sm = re.search(r'\*\*Status\*\*\s*\|\s*([^|]+)', task_block)
                    if sm:
                        task_status = sm.group(1).strip()
                    linked_tasks.append(f"{task_title} -- {files2change} ({task_status})")

    # Fallback: search by requirement text
    if not linked_tasks and TASKS_DIR.exists():
        for tf in TASKS_DIR.glob("*_tasks.md"):
            tf_content = read_file(tf)
            if re.search(r"## Client Requirement\s*\n>\s*" + re.escape(req_text), tf_content):
                task_matches = re.finditer(
                    r"(?s)### Task (\d+):\s*(.+?)\n(.*?)(?=\n### Task|\n---\s*\n## |\n---\s*$|\Z)",
                    tf_content
                )
                for tm in task_matches:
                    task_title = tm.group(2).strip()
                    task_block = tm.group(3)
                    files2change = ""
                    fm = re.search(r'\*\*Files to Change\*\*\s*\|\s*([^|]+)', task_block)
                    if fm:
                        files2change = fm.group(1).strip()
                    task_status = "Pending"
                    sm = re.search(r'\*\*Status\*\*\s*\|\s*([^|]+)', task_block)
                    if sm:
                        task_status = sm.group(1).strip()
                    linked_tasks.append(f"{task_title} -- {files2change} ({task_status})")

    print(f"  Linked tasks: {len(linked_tasks)}")

    # Step 3: Read knowledge file context
    context_text = ""
    if KNOWLEDGE_FILE.exists():
        knowledge_content = read_file(KNOWLEDGE_FILE)
        sections = ["## Project Overview", "## Tech Stack", "## Known Issues"]
        for sec in sections:
            m = re.search(rf"(?s)({re.escape(sec)}.*?)(?=\n## |\Z)", knowledge_content)
            if m:
                context_text += m.group(1).strip() + "\n\n"
        if not context_text:
            lines = knowledge_content.split("\n")
            context_text = "\n".join(lines[:100])

    context_text = sanitize_to_ascii(context_text)

    # Step 4: Output structured data
    print()
    print("===FRD_GENERATE_START===")
    print(f"REQ_ID: {req_id}")
    print(f"CLIENT: {req_client}")
    print(f"CHANNEL: {req_channel}")
    print(f"DATE: {req_date}")
    print(f"STATUS: {req_status}")
    print(f"REQUIREMENT: {req_text}")
    print("TASKS:")
    if linked_tasks:
        for t in linked_tasks:
            print(f"  - {t}")
    else:
        print("  (no linked tasks)")
    print("CONTEXT:")
    for line in context_text.split("\n"):
        print(f"  {line}")
    print("===FRD_GENERATE_END===")
    print()
    print("  Output directory: workflows/frd/")
    print("  Claude Code will now generate the FRD document.")


if __name__ == "__main__":
    main()
