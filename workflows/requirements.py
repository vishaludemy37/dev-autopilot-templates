#!/usr/bin/env python3
"""
Client requirements tracker -- log, link to tasks, and trace full audit trail.
Step-based for Claude Code chat integration.

Usage:
    python workflows/requirements.py --client "Client Name" --channel email --requirement "Add feature X"
    python workflows/requirements.py --requirement "Add feature X"
    python workflows/requirements.py --trace REQ-001
    python workflows/requirements.py --list
    python workflows/requirements.py --step client --response "Client Name"
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REQ_DIR = SCRIPT_DIR / "requirements"
TASKS_DIR = SCRIPT_DIR / "tasks"
TESTING_DIR = SCRIPT_DIR / "testing"
SESSION_DIR = SCRIPT_DIR / ".session"
STATE_FILE = SESSION_DIR / "requirements-state.json"
TODAY = datetime.now().strftime("%Y-%m-%d")
TIME_NOW = datetime.now().strftime("%H:%M")


PROJECT_DIR = SCRIPT_DIR.parent


def auto_commit():
    """Auto-commit and push workflow data changes."""
    workflow_dirs = [
        "workflows/tasks/", "workflows/requirements/",
        "workflows/testing/", "workflows/frd/", "workflows/reports/"
    ]
    subprocess.run(["git", "add"] + workflow_dirs,
                   cwd=str(PROJECT_DIR), capture_output=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"],
                            cwd=str(PROJECT_DIR), capture_output=True)
    if result.returncode != 0:
        subprocess.run(["git", "commit", "-m", "Auto-sync: workflow data update"],
                       cwd=str(PROJECT_DIR), capture_output=True)
        subprocess.run(["git", "push", "origin", "main"],
                       cwd=str(PROJECT_DIR), capture_output=True)


def out(text=""):
    print(text)


def save_state(state):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def clear_state():
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def write_prompt(step_name, message):
    out()
    out(f"[REQUIREMENTS:{step_name}] {message}")


def get_next_req_id():
    max_num = 0
    if REQ_DIR.exists():
        for f in REQ_DIR.glob("*_requirements.md"):
            content = f.read_text(encoding="utf-8")
            for m in re.finditer(r"REQ-(\d+)", content):
                num = int(m.group(1))
                if num > max_num:
                    max_num = num
    return f"REQ-{max_num + 1:03d}"


def parse_all_requirements():
    all_reqs = []
    if not REQ_DIR.exists():
        return all_reqs
    for f in sorted(REQ_DIR.glob("*_requirements.md")):
        content = f.read_text(encoding="utf-8")
        blocks = re.split(r"(?=### REQ-\d+)", content)
        for block in blocks:
            m = re.match(r"^### (REQ-\d+)", block)
            if not m:
                continue
            req_id = m.group(1)
            client = channel = req_text = date = time = ""
            status = "new"

            for field, attr in [("Client", "client"), ("Channel", "channel"),
                                 ("Status", "status"), ("Date", "date"), ("Time", "time")]:
                fm = re.search(rf"\*\*{field}\*\*\s*\|\s*([^|]+)", block)
                if fm:
                    val = fm.group(1).strip()
                    if attr == "client": client = val
                    elif attr == "channel": channel = val
                    elif attr == "status": status = val
                    elif attr == "date": date = val
                    elif attr == "time": time = val

            rm = re.search(r"\*\*Requirement\*\*:\s*(.+)", block)
            if rm:
                req_text = rm.group(1).strip()

            all_reqs.append({
                "id": req_id, "client": client, "channel": channel,
                "requirement": req_text, "status": status, "date": date,
                "time": time, "file": str(f), "file_name": f.name
            })
    return all_reqs


def get_linked_tasks(req_id):
    linked = []
    if not TASKS_DIR.exists():
        return linked
    for f in sorted(TASKS_DIR.glob("*_tasks.md")):
        content = f.read_text(encoding="utf-8")
        blocks = re.split(r"(?=### Task \d+:)", content)
        for block in blocks:
            m = re.match(r"^### Task (\d+):\s*(.+)", block)
            if not m:
                continue
            task_num = m.group(1)
            title = m.group(2).strip()
            if not re.search(r"Source.*" + re.escape(req_id), block):
                continue
            status = "Pending"
            hours = "0"
            files = ""
            sm = re.search(r'\*\*Status\*\*\s*\|\s*([\w\s]+)', block)
            if sm:
                status = sm.group(1).strip()
            hm = re.search(r'\*\*Estimated Hours\*\*\s*\|\s*([\d\-]+)', block)
            if hm:
                hours = hm.group(1)
            fm = re.search(r'\*\*Files to Change\*\*\s*\|\s*([^|]+)', block)
            if fm:
                files = fm.group(1).strip()
            linked.append({
                "task_num": task_num, "title": title, "status": status,
                "hours": hours, "files": files, "file_name": f.name
            })
    return linked


def get_linked_test_cases(tasks):
    test_cases = []
    if not TESTING_DIR.exists():
        return test_cases
    for f in TESTING_DIR.glob("*_testcases.md"):
        content = f.read_text(encoding="utf-8")
        blocks = re.split(r"(?=## Test:)", content)
        for block in blocks:
            m = re.match(r"^## Test:\s*(.+)", block)
            if not m:
                continue
            test_title = m.group(1).strip()
            for task in tasks:
                escaped = re.escape(task["title"][:40])
                if re.search(escaped, test_title) or re.search(escaped, block):
                    reopened = bool(re.search(r"\*\*REOPENED\*\*", block))
                    test_cases.append({
                        "title": test_title, "task_title": task["title"],
                        "reopened": reopened, "file_name": f.name
                    })
                    break
    return test_cases


def get_computed_status(tasks):
    if not tasks:
        return "new"
    all_done = all(t["status"] == "Done" for t in tasks)
    any_in_progress = any("In Progress" in t["status"] for t in tasks)
    if all_done:
        return "done"
    if any_in_progress:
        return "in-progress"
    any_done = any(t["status"] == "Done" for t in tasks)
    if any_done:
        return "in-progress"
    return "new"


def update_req_status(req_id, new_status, file_path):
    content = Path(file_path).read_text(encoding="utf-8")
    pattern = rf"(?s)(### {re.escape(req_id)}.*?\*\*Status\*\*\s*\|\s*)\S+"
    updated = re.sub(pattern, rf"\g<1>{new_status}", content)
    if updated != content:
        Path(file_path).write_text(updated, encoding="utf-8")


# =============================================
# MODES
# =============================================

def do_list():
    out()
    out("  ========================================")
    out("    REQUIREMENTS LIST")
    out("  ========================================")
    out()

    if not REQ_DIR.exists():
        out("  No requirements logged yet.")
        return

    all_reqs = parse_all_requirements()
    if not all_reqs:
        out("  No requirements found.")
        return

    for req in all_reqs:
        tasks = get_linked_tasks(req["id"])
        computed = get_computed_status(tasks)
        if computed != req["status"]:
            update_req_status(req["id"], computed, req["file"])
            req["status"] = computed

    for req in all_reqs:
        tasks = get_linked_tasks(req["id"])
        task_summary = f"{len(tasks)} tasks" if tasks else "no tasks"
        out(f"  {req['id']}  [{req['status']}]  {req['client']} ({req['channel']})")
        out(f"    {req['requirement']}")
        out(f"    {req['date']} | {task_summary}")
        out()

    out(f"  Total: {len(all_reqs)} requirement(s)")
    out()


def do_trace(trace_id):
    out()
    out("  ========================================")
    out(f"    REQUIREMENT TRACE: {trace_id}")
    out("  ========================================")
    out()

    if not REQ_DIR.exists():
        out("  No requirements directory found.")
        sys.exit(1)

    all_reqs = parse_all_requirements()
    req = next((r for r in all_reqs if r["id"] == trace_id), None)

    if not req:
        out(f"  Requirement {trace_id} not found.")
        sys.exit(1)

    out("  REQUIREMENT")
    out("  ----------------------------------------")
    out(f"  ID:       {req['id']}")
    out(f"  Client:   {req['client']}")
    out(f"  Channel:  {req['channel']}")
    out(f"  Date:     {req['date']} {req['time']}")
    out(f"  Text:     {req['requirement']}")
    out()

    tasks = get_linked_tasks(trace_id)

    out(f"  TASKS ({len(tasks)})")
    out("  ----------------------------------------")
    if not tasks:
        out("  No tasks linked to this requirement.")
    else:
        for t in tasks:
            check = "[x]" if t["status"] == "Done" else "[ ]"
            out(f"  {check} Task {t['task_num']}: {t['title']}")
            out(f"      Status: {t['status']} | Hours: {t['hours']} | Files: {t['files']}")
            out(f"      From: {t['file_name']}")
    out()

    test_cases = get_linked_test_cases(tasks)
    out(f"  TEST CASES ({len(test_cases)})")
    out("  ----------------------------------------")
    if not test_cases:
        out("  No test cases generated yet.")
    else:
        for tc in test_cases:
            reopen_tag = " [REOPENED]" if tc["reopened"] else ""
            out(f"  - {tc['title']}{reopen_tag}")
            out(f"    From: {tc['file_name']}")
    out()

    computed = get_computed_status(tasks)
    if computed != req["status"]:
        update_req_status(req["id"], computed, req["file"])
        out(f"  Status auto-updated: {req['status']} -> {computed}")
    out(f"  OVERALL STATUS: {computed}")
    out()


def do_log(state):
    req_text = state.get("requirement", "")
    client_name = state.get("client", "Unknown")
    channel_name = state.get("channel", "email")
    pri_val = state.get("priority", "Medium")

    REQ_DIR.mkdir(parents=True, exist_ok=True)
    req_id = get_next_req_id()

    out()
    out("  ========================================")
    out("    LOG REQUIREMENT")
    out("  ========================================")
    out()
    out(f"  ID:          {req_id}")
    out(f"  Client:      {client_name}")
    out(f"  Channel:     {channel_name}")
    out(f"  Requirement: {req_text}")
    out()

    req_file = REQ_DIR / f"{TODAY}_requirements.md"
    entry = f"""
### {req_id}

| Field | Value |
|---|---|
| **Client** | {client_name} |
| **Channel** | {channel_name} |
| **Date** | {TODAY} |
| **Time** | {TIME_NOW} |
| **Status** | new |

**Requirement**: {req_text}

---"""

    if req_file.exists():
        existing = req_file.read_text(encoding="utf-8")
        req_file.write_text(existing + "\n" + entry, encoding="utf-8")
    else:
        header = f"# Client Requirements - {TODAY}\n\n---{entry}"
        req_file.write_text(header, encoding="utf-8")

    out(f"  Saved to: workflows/requirements/{TODAY}_requirements.md")
    out()

    task_file = TASKS_DIR / f"{TODAY}_tasks.md"
    existing_length = 0
    if task_file.exists():
        existing_length = len(task_file.read_text(encoding="utf-8"))

    out("  GENERATING TASKS")
    out("  ----------------------------------------")

    create_tasks_script = SCRIPT_DIR / "create-tasks.py"
    if create_tasks_script.exists():
        subprocess.run(
            [sys.executable, str(create_tasks_script),
             "--requirement", req_text, "--priority", pri_val],
            cwd=str(SCRIPT_DIR.parent)
        )
    else:
        out("  [WARN] create-tasks.py not found.")

    out()
    out("  LINKING TASKS")
    out("  ----------------------------------------")

    if task_file.exists():
        task_content = task_file.read_text(encoding="utf-8")
        linked_count = 0
        for block_match in re.finditer(r"(?s)(### Task (\d+):.+?)(?=### Task \d+:|$)", task_content):
            if block_match.start() < existing_length:
                continue
            block_text = block_match.group(0)
            if "**Source**" in block_text:
                continue
            replacement = re.sub(
                r"(\| \*\*Files to Change\*\* \|[^|]+\|)",
                rf"\1\n| **Source** | {req_id} |",
                block_text
            )
            task_content = task_content.replace(block_text, replacement)
            linked_count += 1

        task_file.write_text(task_content, encoding="utf-8")
        out(f"  Linked {linked_count} task(s) to {req_id}")

    out()
    out("  ========================================")
    out(f"  Requirement {req_id} logged and tasks created.")
    out(f"  Trace with: python workflows/requirements.py --trace {req_id}")
    out()
    auto_commit()
    clear_state()


# =============================================
# STATE MACHINE
# =============================================

def process_step(step, response):
    state = load_state()

    if step == "client":
        client_val = response.strip() if response.strip() else "Unknown"
        state["client"] = client_val

        if "channel" not in state or not state["channel"]:
            state["step"] = "channel"
            save_state(state)
            write_prompt("channel", "Channel? Reply: email / whatsapp / call / slack / meeting")
            return

        do_log(state)
        return

    elif step == "channel":
        channel_val = response.strip().lower()
        valid_channels = ["email", "whatsapp", "call", "slack", "meeting"]
        if channel_val not in valid_channels:
            channel_val = "email"
        state["channel"] = channel_val
        save_state(state)
        do_log(state)
        return

    elif step == "do_log":
        do_log(state)
        return

    else:
        out(f"  Unknown step: {step}")
        clear_state()
        sys.exit(1)


def main():
    client = channel = requirement = trace_id = step = response = None
    priority = "Medium"
    list_mode = False

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--client" and i + 1 < len(sys.argv):
            client = sys.argv[i + 1]; i += 2
        elif arg == "--channel" and i + 1 < len(sys.argv):
            channel = sys.argv[i + 1]; i += 2
        elif arg == "--requirement" and i + 1 < len(sys.argv):
            requirement = sys.argv[i + 1]; i += 2
        elif arg == "--priority" and i + 1 < len(sys.argv):
            priority = sys.argv[i + 1]; i += 2
        elif arg == "--trace" and i + 1 < len(sys.argv):
            trace_id = sys.argv[i + 1]; i += 2
        elif arg == "--list":
            list_mode = True; i += 1
        elif arg == "--step" and i + 1 < len(sys.argv):
            step = sys.argv[i + 1]; i += 2
        elif arg == "--response" and i + 1 < len(sys.argv):
            response = sys.argv[i + 1]; i += 2
        else:
            i += 1

    if list_mode:
        do_list()
        return

    if trace_id:
        do_trace(trace_id)
        return

    if step:
        process_step(step, response or "")
        return

    if not requirement:
        out()
        out("  Usage:")
        out('  python requirements.py --client "Name" --channel "email" --requirement "text"')
        out('  python requirements.py --requirement "text"     (prompts for client/channel)')
        out('  python requirements.py --trace REQ-001')
        out('  python requirements.py --list')
        out()
        return

    if not client and not channel:
        save_state({"step": "client", "requirement": requirement, "priority": priority})
        write_prompt("client", "Client name? (or press enter for 'Unknown')")
        return

    if not client:
        save_state({"step": "client", "requirement": requirement, "channel": channel, "priority": priority})
        write_prompt("client", "Client name? (or press enter for 'Unknown')")
        return

    if not channel:
        save_state({"step": "channel", "requirement": requirement, "client": client, "priority": priority})
        write_prompt("channel", "Channel? Reply: email / whatsapp / call / slack / meeting")
        return

    state = {
        "step": "do_log",
        "requirement": requirement,
        "client": client,
        "channel": channel,
        "priority": priority
    }
    save_state(state)
    do_log(state)


if __name__ == "__main__":
    main()
