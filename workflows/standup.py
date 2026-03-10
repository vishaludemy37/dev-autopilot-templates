#!/usr/bin/env python3
"""
Daily standup script -- step-based for Claude Code chat integration.

Usage:
    python workflows/standup.py
    python workflows/standup.py --step action_choice --response y
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
TASKS_DIR = SCRIPT_DIR / "tasks"
TESTING_DIR = SCRIPT_DIR / "testing"
FRD_DIR = SCRIPT_DIR / "frd"
SESSION_DIR = SCRIPT_DIR / ".session"
STATE_FILE = SESSION_DIR / "standup-state.json"
TODAY = datetime.now()
TODAY_STR = TODAY.strftime("%Y-%m-%d")
GITHUB_REPO = "{{GITHUB_REPO}}"


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


def sanitize_to_ascii(text):
    text = text.replace("\u2014", "--").replace("\u2013", "--")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2026", "...").replace("\u2192", "->").replace("\u2190", "<-")
    return re.sub(r'[^\x00-\x7f]', '', text)


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
    out(f"[STANDUP:{step_name}] {message}")


def get_max_hours(range_str):
    parts = range_str.split("-")
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0


def priority_weight(p):
    return {"High": 0, "Medium": 1, "Low": 2}.get(p, 3)


# --- GitHub commits ---
def get_today_commits():
    env_file = PROJECT_DIR / ".env"
    token = None
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            m = re.match(r'^\s*GITHUB_TOKEN\s*=\s*(.+)$', line)
            if m:
                token = m.group(1).strip().strip('"').strip("'")
                break
    if not token:
        return {"error": "GITHUB_TOKEN not found in .env"}

    from datetime import timezone
    since_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/commits?since={since_date}&per_page=20"

    try:
        import urllib.request
        req = urllib.request.Request(api_url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "{{PROJECT_NAME}}-standup"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {"commits": data, "error": None}
    except Exception as e:
        return {"error": str(e)}


# --- Parse all task files ---
def parse_task_files():
    all_tasks = []
    if not TASKS_DIR.exists():
        return all_tasks

    for f in sorted(TASKS_DIR.glob("*_tasks.md")):
        date_str = f.stem.replace("_tasks", "")
        try:
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue

        content = f.read_text(encoding="utf-8")
        blocks = re.split(r"(?=### Task \d+:)", content)

        for block in blocks:
            m = re.match(r"^### Task (\d+):\s*(.+)", block)
            if not m:
                continue
            task_num = int(m.group(1))
            title = m.group(2).strip()
            priority = "Medium"
            status = "Pending"
            hours = "0"
            files = ""
            description = ""

            pm = re.search(r"\*\*Priority\*\*\s*\|\s*(\w+)", block)
            if pm: priority = pm.group(1)
            sm = re.search(r'\*\*Status\*\*\s*\|\s*([\w\s]+)', block)
            if sm: status = sm.group(1).strip()
            hm = re.search(r'\*\*Estimated Hours\*\*\s*\|\s*([\d\-]+)', block)
            if hm: hours = hm.group(1)
            fm = re.search(r'\*\*Files to Change\*\*\s*\|\s*([^|]+)', block)
            if fm: files = fm.group(1).strip()
            dm = re.search(r"\*\*Description\*\*:\s*(.+)", block)
            if dm: description = dm.group(1).strip()

            days_since = (TODAY - file_date).days
            all_tasks.append({
                "file": str(f), "file_name": f.name, "file_date": file_date.isoformat(),
                "days_since": days_since, "task_num": task_num, "title": title,
                "priority": priority, "status": status, "hours": hours,
                "files": files, "description": description,
                "overdue": days_since > 3 and status != "Done"
            })
    return all_tasks


# --- Parse test cases ---
def parse_test_cases():
    tests = []
    if not TESTING_DIR.exists():
        return tests
    for f in sorted(TESTING_DIR.glob("*_testcases.md"), reverse=True):
        content = f.read_text(encoding="utf-8")
        blocks = re.split(r"(?=## Test:)", content)
        for block in blocks:
            m = re.match(r"^## Test:\s*(.+)", block)
            if not m:
                continue
            test_title = m.group(1).strip()
            reopened = bool(re.search(r"\*\*REOPENED\*\*", block))
            tests.append({
                "file": str(f), "file_name": f.name, "title": test_title,
                "reopened": reopened
            })
    return tests


# --- Output structured Done pipeline data ---
def output_done_pipeline_data(task_title, task_description, files_to_change,
                               req_id="", priority="Medium", known_issues=""):
    if not req_id and TASKS_DIR.exists():
        for tf in TASKS_DIR.glob("*_tasks.md"):
            tf_content = tf.read_text(encoding="utf-8")
            pattern = rf"(?s)### Task \d+:\s*{re.escape(task_title)}.*?\*\*Source\*\*\s*\|\s*(REQ-\d+)"
            m = re.search(pattern, tf_content)
            if m:
                req_id = m.group(1)
                break

    if priority == "Medium" and TASKS_DIR.exists():
        for tf in TASKS_DIR.glob("*_tasks.md"):
            tf_content = tf.read_text(encoding="utf-8")
            pattern = rf"(?s)### Task \d+:\s*{re.escape(task_title)}.*?\*\*Priority\*\*\s*\|\s*(\w+)"
            m = re.search(pattern, tf_content)
            if m:
                priority = m.group(1)
                break

    has_frd = (FRD_DIR / f"{req_id}-FRD.md").exists() if req_id else False

    out()
    out("===DONE_PIPELINE_START===")
    out(f"TASK: {task_title}")
    out(f"DESCRIPTION: {task_description}")
    out(f"FILES: {files_to_change}")
    out(f"REQ: {req_id}")
    out(f"PRIORITY: {priority}")
    if has_frd:
        out(f"FRD_FILE: workflows/frd/{req_id}-FRD.md")
    if known_issues:
        out(f"KNOWN_ISSUES: {known_issues}")
    out("===DONE_PIPELINE_END===")
    out()


# --- Display helpers ---
def show_active_task_list():
    all_tasks = parse_task_files()
    active = sorted(
        [t for t in all_tasks if t["status"] != "Done"],
        key=lambda x: (priority_weight(x["priority"]), x["days_since"])
    )
    if not active:
        out("  All tasks are done!")
        return None
    out()
    for i, t in enumerate(active, 1):
        overdue_tag = " [OVERDUE]" if t["overdue"] else ""
        out(f"    {i}. [{t['priority']}] {t['title']} -- {t['status']}{overdue_tag}")
    return active


def show_focus():
    all_tasks = parse_task_files()
    active = [t for t in all_tasks if t["status"] != "Done"]
    focus = sorted(active, key=lambda x: (priority_weight(x["priority"]), -x["days_since"]))[:3]

    out()
    out("  FOCUS FOR TODAY")
    out("  ========================================")
    if not focus:
        out("  All tasks done! Time to create new ones.")
    else:
        for rank, t in enumerate(focus, 1):
            overdue_tag = " [OVERDUE]" if t["overdue"] else ""
            out(f"  {rank}. [{t['priority']}] {t['title']}{overdue_tag}")
            out(f"     Hours: {t['hours']} | Files: {t['files']}")
    out()
    out("  ========================================")
    out("  Have a productive day!")
    out()


def show_test_case_list():
    test_cases = parse_test_cases()
    open_tests = [tc for tc in test_cases if not tc["reopened"]]
    if not open_tests:
        out("  No test cases available to reopen.")
        return None
    out()
    out("  TEST CASES:")
    for i, tc in enumerate(open_tests, 1):
        out(f"    {i}. {tc['title']}")
        out(f"       From: {tc['file_name']}")
    return open_tests


# =============================================
# STATE MACHINE
# =============================================

def fresh_start():
    clear_state()
    out()
    out("  ========================================")
    out(f"    DAILY STANDUP - {TODAY.strftime('%Y-%m-%d (%A)')}")
    out("  ========================================")
    out()

    # Commits
    try:
        commit_data = get_today_commits()
        out("  RECENT COMMITS TODAY")
        out("  ----------------------------------------")
        if commit_data.get("error"):
            out(f"  [WARN] {commit_data['error']}")
        elif not commit_data.get("commits"):
            out("  No commits today.")
        else:
            for c in commit_data["commits"]:
                short_hash = c["sha"][:7]
                msg = c["commit"]["message"].split("\n")[0]
                author = c["commit"]["author"].get("name", "unknown")
                out(f"  {short_hash} {msg} ({author})")
        out()
    except Exception as e:
        out("  RECENT COMMITS TODAY")
        out("  ----------------------------------------")
        out(f"  [WARN] Failed to fetch commits: {e}")
        out()

    # Tasks
    if not TASKS_DIR.exists():
        out("  No tasks directory found.")
        return

    all_tasks = parse_task_files()
    if not all_tasks:
        out("  No tasks found.")
        return

    pending = [t for t in all_tasks if t["status"] == "Pending"]
    in_progress = [t for t in all_tasks if "In Progress" in t["status"]]
    done = [t for t in all_tasks if t["status"] == "Done"]
    active = [t for t in all_tasks if t["status"] != "Done"]

    if in_progress:
        out(f"  IN PROGRESS ({len(in_progress)})")
        out("  ----------------------------------------")
        for t in sorted(in_progress, key=lambda x: priority_weight(x["priority"])):
            overdue_tag = f" [OVERDUE {t['days_since']}d]" if t["overdue"] else ""
            out(f"  [{t['priority']}] {t['title']}{overdue_tag}")
            out(f"         Hours: {t['hours']} | Files: {t['files']}")
            out(f"         From: {t['file_name']} ({t['days_since']}d ago)")
            out()

    if pending:
        out(f"  PENDING ({len(pending)})")
        out("  ----------------------------------------")
        for prio in ["High", "Medium", "Low"]:
            group = [t for t in pending if t["priority"] == prio]
            if not group:
                continue
            out(f"    {prio} Priority:")
            for t in sorted(group, key=lambda x: -x["days_since"]):
                overdue_tag = f" [OVERDUE {t['days_since']}d]" if t["overdue"] else ""
                out(f"    - {t['title']}{overdue_tag}")
                out(f"      Hours: {t['hours']} | Files: {t['files']}")
                out(f"      From: {t['file_name']} ({t['days_since']}d ago)")
            out()

    overdue_list = [t for t in active if t["overdue"]]
    if overdue_list:
        out(f"  OVERDUE ({len(overdue_list)} tasks older than 3 days)")
        out("  ----------------------------------------")
        for t in overdue_list:
            out(f"  ! {t['title']} -- {t['days_since']} days old ({t['file_name']})")
        out()

    total_hrs = sum(get_max_hours(t["hours"]) for t in active)
    out("  SUMMARY")
    out("  ----------------------------------------")
    out(f"  Total tasks:      {len(all_tasks)}")
    out(f"  Done:             {len(done)}")
    out(f"  In Progress:      {len(in_progress)}")
    out(f"  Pending:          {len(pending)}")
    out(f"  Overdue:          {len(overdue_list)}")
    out(f"  Hours remaining:  ~{total_hrs} hrs (upper bound)")

    save_state({"step": "action_choice"})
    write_prompt("action_choice", "Update task status? Reply: y / r (reopen test) / n (skip)")


def process_step(step, response):
    state = load_state()

    if step == "action_choice":
        val = response.strip().lower()
        if val in ("n", ""):
            show_focus()
            clear_state()
            return
        if val == "r":
            tests = show_test_case_list()
            if not tests:
                save_state({"step": "pick_task"})
                show_active_task_list()
                write_prompt("pick_task", "Enter task # to update, 'r' to reopen test, or 'q' to finish")
            else:
                save_state({"step": "reopen_pick"})
                write_prompt("reopen_pick", "Select test case # to reopen (or 'q' to cancel)")
            return
        # "y"
        active = show_active_task_list()
        if not active:
            show_focus()
            clear_state()
            return
        save_state({"step": "pick_task"})
        write_prompt("pick_task", "Enter task # to update, 'r' to reopen test, or 'q' to finish")

    elif step == "pick_task":
        val = response.strip().lower()
        if val in ("q", ""):
            show_focus()
            clear_state()
            return
        if val == "r":
            tests = show_test_case_list()
            if not tests:
                show_active_task_list()
                save_state({"step": "pick_task"})
                write_prompt("pick_task", "Enter task # to update, 'r' to reopen test, or 'q' to finish")
            else:
                save_state({"step": "reopen_pick"})
                write_prompt("reopen_pick", "Select test case # to reopen (or 'q' to cancel)")
            return

        try:
            pick_idx = int(val)
        except ValueError:
            out("  Invalid number.")
            show_active_task_list()
            save_state({"step": "pick_task"})
            write_prompt("pick_task", "Enter task # to update, 'r' to reopen test, or 'q' to finish")
            return

        all_tasks = parse_task_files()
        active = sorted(
            [t for t in all_tasks if t["status"] != "Done"],
            key=lambda x: (priority_weight(x["priority"]), x["days_since"])
        )

        if pick_idx < 1 or pick_idx > len(active):
            out(f"  Out of range (1-{len(active)}).")
            show_active_task_list()
            save_state({"step": "pick_task"})
            write_prompt("pick_task", "Enter task # to update, 'r' to reopen test, or 'q' to finish")
            return

        sel = active[pick_idx - 1]
        out(f"  Selected: {sel['title']}")
        out(f"  Current status: {sel['status']}")
        out()
        out("    1. Pending")
        out("    2. In Progress")
        out("    3. Done")

        save_state({
            "step": "new_status",
            "task_file": sel["file"], "task_num": sel["task_num"],
            "task_title": sel["title"], "task_status": sel["status"],
            "task_description": sel["description"], "task_files": sel["files"]
        })
        write_prompt("new_status", f"New status for '{sel['title']}'? Reply: 1 (Pending) / 2 (In Progress) / 3 (Done)")

    elif step == "new_status":
        status_map = {"1": "Pending", "2": "In Progress", "3": "Done"}
        new_status = status_map.get(response.strip())

        if not new_status:
            out("  Invalid choice.")
            show_active_task_list()
            save_state({"step": "pick_task"})
            write_prompt("pick_task", "Enter task # to update, 'r' to reopen test, or 'q' to finish")
            return

        task_file = state["task_file"]
        task_num = state["task_num"]
        task_title = state["task_title"]
        task_status = state["task_status"]
        task_desc = state.get("task_description", "")
        task_files = state.get("task_files", "")

        if new_status == task_status:
            out("  Status unchanged.")
            show_active_task_list()
            save_state({"step": "pick_task"})
            write_prompt("pick_task", "Enter task # to update, or 'q' to finish")
            return

        if new_status != "Done":
            content = Path(task_file).read_text(encoding="utf-8")
            pattern = rf"(?s)(### Task {task_num}:.*?\*\*Status\*\*\s*\|\s*){re.escape(task_status)}"
            updated = re.sub(pattern, rf"\g<1>{new_status}", content)
            if updated != content:
                Path(task_file).write_text(updated, encoding="utf-8")
                out(f"  Updated: {task_title} -> {new_status}")
                auto_commit()
            show_active_task_list()
            save_state({"step": "pick_task"})
            write_prompt("pick_task", "Enter task # to update, or 'q' to finish")
            return

        # Done pipeline
        out()
        out("  COMPLETION PIPELINE")
        out("  ========================================")

        content = Path(task_file).read_text(encoding="utf-8")
        pattern = rf"(?s)(### Task {task_num}:.*?\*\*Status\*\*\s*\|\s*){re.escape(task_status)}"
        updated = re.sub(pattern, r"\g<1>Done", content)
        if updated != content:
            Path(task_file).write_text(updated, encoding="utf-8")
            out(f"  Updated: {task_title} -> Done")

        output_done_pipeline_data(task_title, task_desc, task_files)
        auto_commit()

        save_state({
            "step": "sync_knowledge",
            "task_file": task_file, "task_num": task_num, "task_title": task_title
        })
        write_prompt("sync_knowledge", "Sync knowledge file with latest changes? Reply: y / n")

    elif step == "sync_knowledge":
        val = response.strip().lower()
        if val == "y":
            sync_script = SCRIPT_DIR / "sync-knowledge.py"
            if sync_script.exists():
                subprocess.run([sys.executable, str(sync_script)], cwd=str(PROJECT_DIR))
            else:
                out("  [WARN] sync-knowledge.py not found.")

        all_tasks = parse_task_files()
        active = [t for t in all_tasks if t["status"] != "Done"]
        if not active:
            show_focus()
            clear_state()
            return

        show_active_task_list()
        save_state({"step": "pick_task"})
        write_prompt("pick_task", "Enter task # to update, or 'q' to finish")

    elif step == "reopen_pick":
        val = response.strip().lower()
        if val in ("q", ""):
            show_active_task_list()
            save_state({"step": "pick_task"})
            write_prompt("pick_task", "Enter task # to update, 'r' to reopen test, or 'q' to finish")
            return

        try:
            pick_idx = int(val)
        except ValueError:
            out("  Invalid number.")
            show_test_case_list()
            save_state({"step": "reopen_pick"})
            write_prompt("reopen_pick", "Select test case # to reopen (or 'q' to cancel)")
            return

        test_cases = parse_test_cases()
        open_tests = [tc for tc in test_cases if not tc["reopened"]]

        if pick_idx < 1 or pick_idx > len(open_tests):
            out("  Out of range.")
            show_test_case_list()
            save_state({"step": "reopen_pick"})
            write_prompt("reopen_pick", "Select test case # to reopen (or 'q' to cancel)")
            return

        selected = open_tests[pick_idx - 1]
        out(f"  Selected: {selected['title']}")

        save_state({
            "step": "reopen_feedback",
            "reopen_test_file": selected["file"],
            "reopen_test_title": selected["title"]
        })
        write_prompt("reopen_feedback", "What did the tester report? Describe what failed")

    elif step == "reopen_feedback":
        feedback = response.strip()
        if not feedback:
            out("  No feedback provided. Cancelled.")
            show_active_task_list()
            save_state({"step": "pick_task"})
            write_prompt("pick_task", "Enter task # to update, or 'q' to finish")
            return

        test_file = state["reopen_test_file"]
        test_title = state["reopen_test_title"]

        # Create fix task
        task_file = TASKS_DIR / f"{TODAY_STR}_tasks.md"
        fix_title = f"Fix: {test_title}"
        next_num = 1
        if task_file.exists():
            existing_content = task_file.read_text(encoding="utf-8")
            nums = [int(m.group(1)) for m in re.finditer(r"### Task (\d+):", existing_content)]
            if nums:
                next_num = max(nums) + 1

        description = f"Failed test: {test_title}. Tester feedback: {feedback}"
        new_task = f"""
### Task {next_num}: {fix_title}

| Field | Value |
|---|---|
| **Priority** | High |
| **Status** | Pending |
| **Estimated Hours** | 1-2 |
| **Files to Change** | (review) |

**Description**: {description}

---"""

        if task_file.exists():
            existing = task_file.read_text(encoding="utf-8")
            task_file.write_text(existing + "\n" + new_task, encoding="utf-8")
        else:
            header = f"# Task Breakdown - {TODAY_STR}\n\n---{new_task}"
            task_file.write_text(header, encoding="utf-8")

        # Flag original test as REOPENED
        test_content = Path(test_file).read_text(encoding="utf-8")
        escaped_title = re.escape(test_title)
        reopen_flag = f"\n\n> **REOPENED** on {TODAY_STR} -- {feedback}"
        test_content = re.sub(rf"(## Test:\s*{escaped_title})", rf"\1{reopen_flag}", test_content)
        Path(test_file).write_text(test_content, encoding="utf-8")

        out()
        out(f"  Task reopened: {fix_title}")
        out("  Original test case flagged as REOPENED.")
        auto_commit()

        show_active_task_list()
        save_state({"step": "pick_task"})
        write_prompt("pick_task", "Enter task # to update, or 'q' to finish")

    else:
        out(f"  Unknown step: {step}")
        clear_state()
        sys.exit(1)


def main():
    step = response = None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--step" and i + 1 < len(sys.argv):
            step = sys.argv[i + 1]; i += 2
        elif sys.argv[i] == "--response" and i + 1 < len(sys.argv):
            response = sys.argv[i + 1]; i += 2
        else:
            i += 1

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    if not step:
        fresh_start()
    else:
        process_step(step, response or "")


if __name__ == "__main__":
    main()
