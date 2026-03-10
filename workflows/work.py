#!/usr/bin/env python3
"""
Interactive work session manager -- step-based for Claude Code chat integration.

Usage:
    python workflows/work.py --list
    python workflows/work.py --requirement REQ-001
    python workflows/work.py --step pick_task --response 1
    python workflows/work.py --tester
    python workflows/work.py --step tester_pick --response 1
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
REQ_DIR = SCRIPT_DIR / "requirements"
TASKS_DIR = SCRIPT_DIR / "tasks"
TESTING_DIR = SCRIPT_DIR / "testing"
READY_FILE = TESTING_DIR / "READY_FOR_TESTING.md"
FRD_DIR = SCRIPT_DIR / "frd"
SESSION_DIR = SCRIPT_DIR / ".session"
STATE_FILE = SESSION_DIR / "work-state.json"
TODAY = datetime.now().strftime("%Y-%m-%d")
TIME_NOW = datetime.now().strftime("%H:%M")


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
    out(f"[WORK:{step_name}] {message}")


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
            description = ""
            sm = re.search(r'\*\*Status\*\*\s*\|\s*([\w\s]+)', block)
            if sm: status = sm.group(1).strip()
            hm = re.search(r'\*\*Estimated Hours\*\*\s*\|\s*([\d\-]+)', block)
            if hm: hours = hm.group(1)
            fm = re.search(r'\*\*Files to Change\*\*\s*\|\s*([^|]+)', block)
            if fm: files = fm.group(1).strip()
            dm = re.search(r"\*\*Description\*\*:\s*(.+)", block)
            if dm: description = dm.group(1).strip()
            linked.append({
                "task_num": task_num, "title": title, "status": status,
                "hours": hours, "files": files, "description": description,
                "file_name": f.name, "file_path": str(f)
            })
    return linked


def get_computed_status(tasks):
    if not tasks:
        return "new"
    all_done = all(t["status"] == "Done" for t in tasks)
    any_active = any("In Progress" in t["status"] or t["status"] == "Done" for t in tasks)
    if all_done:
        return "done"
    if any_active:
        return "in-progress"
    return "new"


def update_task_status(file_path, task_num, old_status, new_status):
    content = Path(file_path).read_text(encoding="utf-8")
    pattern = rf"(?s)(### Task {task_num}:.*?\*\*Status\*\*\s*\|\s*){re.escape(old_status)}"
    updated = re.sub(pattern, rf"\g<1>{new_status}", content)
    if updated != content:
        Path(file_path).write_text(updated, encoding="utf-8")
        return True
    return False


def update_req_status(req_id, new_status, file_path):
    content = Path(file_path).read_text(encoding="utf-8")
    pattern = rf"(?s)(### {re.escape(req_id)}.*?\*\*Status\*\*\s*\|\s*)\S+"
    updated = re.sub(pattern, rf"\g<1>{new_status}", content)
    if updated != content:
        Path(file_path).write_text(updated, encoding="utf-8")


def output_done_pipeline_data(task_title, task_description, files_to_change,
                               req_id="", priority="Medium", known_issues=""):
    if not req_id and TASKS_DIR.exists():
        for tf in TASKS_DIR.glob("*_tasks.md"):
            tf_content = tf.read_text(encoding="utf-8")
            m = re.search(rf"(?s)### Task \d+:\s*{re.escape(task_title)}.*?\*\*Source\*\*\s*\|\s*(REQ-\d+)", tf_content)
            if m:
                req_id = m.group(1)
                break

    if priority == "Medium" and TASKS_DIR.exists():
        for tf in TASKS_DIR.glob("*_tasks.md"):
            tf_content = tf.read_text(encoding="utf-8")
            m = re.search(rf"(?s)### Task \d+:\s*{re.escape(task_title)}.*?\*\*Priority\*\*\s*\|\s*(\w+)", tf_content)
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


def update_test_case_excel(req_id="", task_title="", priority="Medium",
                            preconditions="", steps="", expected="",
                            edge_cases="", known_issues=""):
    py_script = SCRIPT_DIR / "update-testcases-excel.py"
    if not py_script.exists():
        out("  [WARN] update-testcases-excel.py not found. Skipping Excel update.")
        return ""
    try:
        result = subprocess.run(
            [sys.executable, str(py_script), "add",
             "--req-id", req_id, "--task", task_title, "--priority", priority,
             "--preconditions", preconditions, "--steps", steps,
             "--expected", expected, "--edge-cases", edge_cases,
             "--known-issues", known_issues],
            capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode == 0:
            tc_id = result.stdout.strip()
            out(f"  Excel updated: {tc_id} added to workflows/testing/testcases.xlsx")
            return tc_id
        else:
            out(f"  [WARN] Excel update failed: {result.stdout}{result.stderr}")
            return ""
    except Exception as e:
        out(f"  [WARN] Excel update failed: {e}")
        return ""


def update_test_case_excel_status(tc_id, status, notes=""):
    py_script = SCRIPT_DIR / "update-testcases-excel.py"
    if not py_script.exists():
        return
    args = [sys.executable, str(py_script), "update", "--tc-id", tc_id, "--status", status]
    if notes:
        args.extend(["--notes", notes])
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
        if result.returncode == 0:
            out(f"  Excel: {result.stdout.strip()}")
    except Exception:
        pass


def finalize_task_done(state):
    task_file = state["task_file"]
    task_num = state["task_num"]
    task_title = state["task_title"]
    task_status = state["task_status"]
    task_desc = state.get("task_description", "")
    task_files = state.get("task_files", "")
    req_id = state.get("req_id", "")
    req_file = state.get("req_file", "")
    all_issues = state.get("all_issues", [])

    updated = update_task_status(task_file, task_num, task_status, "Done")
    if updated:
        out(f"  Task {task_num} marked as Done.")

    known_issues_text = "; ".join(all_issues) if all_issues else ""
    output_done_pipeline_data(task_title, task_desc, task_files,
                               req_id=req_id, known_issues=known_issues_text)

    all_tasks = get_linked_tasks(req_id)
    for t in all_tasks:
        if t["task_num"] == str(task_num):
            t["status"] = "Done"
    new_req_status = get_computed_status(all_tasks)
    if req_file:
        update_req_status(req_id, new_req_status, req_file)
        out(f"  Requirement {req_id} status: {new_req_status}")

    TESTING_DIR.mkdir(parents=True, exist_ok=True)

    import getpass
    developer = getpass.getuser()

    ready_entry = f"""
### {req_id} -- Task {task_num}: {task_title}

| Field | Value |
|---|---|
| **Requirement** | {req_id} |
| **Task** | Task {task_num}: {task_title} |
| **Developer** | {developer} |
| **Completed** | {TODAY} {TIME_NOW} |
| **Test Case** | workflows/testing/{TODAY}_testcases.md |
| **Files Changed** | {task_files} |
| **Status** | Awaiting Test |

---"""

    if READY_FILE.exists():
        existing = READY_FILE.read_text(encoding="utf-8")
        READY_FILE.write_text(existing + "\n" + ready_entry, encoding="utf-8")
    else:
        header = f"# Ready for Testing\n\nItems below have passed code review and are awaiting manual testing.\n\n---{ready_entry}"
        READY_FILE.write_text(header, encoding="utf-8")
    out("  Added to READY_FOR_TESTING.md")


# =============================================
# LIST MODE
# =============================================

def do_list():
    out()
    out("  ========================================")
    out("    OPEN REQUIREMENTS")
    out("  ========================================")
    out()

    all_reqs = parse_all_requirements()
    open_reqs = [r for r in all_reqs if r["status"] in ("new", "in-progress")]

    if not open_reqs:
        out("  No open requirements. All done!")
        return

    for i, req in enumerate(open_reqs, 1):
        tasks = get_linked_tasks(req["id"])
        total_hours = 0
        for t in tasks:
            parts = t["hours"].split("-")
            try:
                total_hours += int(parts[-1])
            except ValueError:
                pass
        short_req = req["requirement"][:60] + "..." if len(req["requirement"]) > 60 else req["requirement"]
        out(f"  {i}. {req['id']} [{req['status']}]  {req['client']} -- {short_req}")
        out(f"     {len(tasks)} task(s), ~{total_hours} hrs | {req['date']}")
    out()
    out("  Start with: python workflows/work.py --requirement REQ-XXX")
    out()


# =============================================
# TESTER MODE
# =============================================

def do_tester():
    clear_state()
    out()
    out("  ========================================")
    out("    TESTER MODE")
    out("  ========================================")
    out()

    if not READY_FILE.exists():
        out("  No items ready for testing.")
        return

    ready_content = READY_FILE.read_text(encoding="utf-8")
    blocks = re.split(r"(?=### REQ-\d+)", ready_content)
    items = []

    for block in blocks:
        m = re.match(r"^### (REQ-\d+) -- Task (\d+): (.+)", block)
        if not m:
            continue
        r_id, t_num, t_title = m.group(1), m.group(2), m.group(3).strip()
        test_status = "Awaiting Test"
        sm = re.search(r"\*\*Status\*\*\s*\|\s*([^|]+)", block)
        if sm:
            test_status = sm.group(1).strip()
        if test_status != "Awaiting Test":
            continue
        files = ""
        test_case = ""
        fm = re.search(r"\*\*Files Changed\*\*\s*\|\s*([^|]+)", block)
        if fm: files = fm.group(1).strip()
        tm = re.search(r"\*\*Test Case\*\*\s*\|\s*([^|]+)", block)
        if tm: test_case = tm.group(1).strip()
        items.append({"req_id": r_id, "task_num": t_num, "title": t_title,
                       "files": files, "test_case": test_case})

    if not items:
        out("  No items awaiting test.")
        return

    out(f"  AWAITING TEST ({len(items)})")
    out("  ----------------------------------------")
    for i, item in enumerate(items, 1):
        out(f"  {i}. {item['req_id']} Task {item['task_num']}: {item['title']}")
        out(f"     Files: {item['files']}")
        out(f"     Test case: {item['test_case']}")

    save_state({"step": "tester_pick", "mode": "tester"})
    write_prompt("tester_pick", "Enter item # to review (or 'q' to quit)")


# =============================================
# WORK MODE - Start
# =============================================

def start_work(requirement):
    clear_state()

    all_reqs = parse_all_requirements()
    req = next((r for r in all_reqs if r["id"] == requirement), None)

    if not req:
        out(f"  Requirement {requirement} not found.")
        sys.exit(1)

    out()
    out("  ========================================")
    out(f"    WORK SESSION: {requirement}")
    out("  ========================================")
    out()
    out(f"  Client:      {req['client']}")
    out(f"  Channel:     {req['channel']}")
    out(f"  Requirement: {req['requirement']}")
    out(f"  Status:      {req['status']}")
    out()

    tasks = get_linked_tasks(requirement)

    if not tasks:
        out("  No tasks linked to this requirement.")
        return

    out(f"  TASKS ({len(tasks)})")
    out("  ----------------------------------------")
    for i, t in enumerate(tasks, 1):
        check = "[x]" if t["status"] == "Done" else "[ ]"
        out(f"  {i}. {check} {t['title']} -- {t['status']}")
        out(f"     Hours: {t['hours']} | Files: {t['files']}")

    frd_file = FRD_DIR / f"{requirement}-FRD.md"
    if frd_file.exists():
        out()
        out(f"  FRD: workflows/frd/{requirement}-FRD.md")
        out("  ----------------------------------------")
        frd_content = frd_file.read_text(encoding="utf-8")
        fr_matches = re.findall(r"(?m)^### (FR-\d+):\s*(.+)", frd_content)
        if fr_matches:
            out("  ACCEPTANCE CRITERIA:")
            for fr_id, fr_title in fr_matches:
                out(f"    {fr_id}: {fr_title}")
    else:
        out()
        out("  [WARN] No FRD found -- working from requirement text only")

    workable = [t for t in tasks if t["status"] != "Done"]
    if not workable:
        out()
        out("  All tasks are done!")
        return

    save_state({"step": "pick_task", "mode": "work", "req_id": requirement, "req_file": req["file"]})
    write_prompt("pick_task", "Pick a task to work on (number, or 'q' to quit)")


# =============================================
# STATE MACHINE
# =============================================

def process_step(step, response):
    state = load_state()

    if step == "pick_task":
        val = response.strip().lower()
        req_id = state.get("req_id", "")
        req_file = state.get("req_file", "")

        if val in ("q", ""):
            out("  Session ended.")
            clear_state()
            return

        try:
            pick_idx = int(val)
        except ValueError:
            out("  Invalid number.")
            save_state(state)
            write_prompt("pick_task", "Pick a task to work on (number, or 'q' to quit)")
            return

        tasks = get_linked_tasks(req_id)
        if pick_idx < 1 or pick_idx > len(tasks):
            out(f"  Out of range (1-{len(tasks)}).")
            save_state(state)
            write_prompt("pick_task", "Pick a task to work on (number, or 'q' to quit)")
            return

        sel = tasks[pick_idx - 1]
        if sel["status"] == "Done":
            out("  That task is already done.")
            save_state(state)
            write_prompt("pick_task", "Pick a different task (number, or 'q' to quit)")
            return

        if sel["status"] == "Pending":
            updated = update_task_status(sel["file_path"], sel["task_num"], "Pending", "In Progress")
            if updated:
                sel["status"] = "In Progress"
                out("  Marked as In Progress.")

        new_req_status = get_computed_status(tasks)
        update_req_status(req_id, new_req_status, req_file)

        out()
        out("  ========================================")
        out(f"    WORKING: Task {sel['task_num']} -- {sel['title']}")
        out("  ========================================")
        out()
        out("  Files to edit:")
        for f in sel["files"].split(","):
            out(f"    - {f.strip()}")
        out()
        out(f"  Description: {sel['description']}")
        out(f"  Estimated:   {sel['hours']} hrs")

        save_state({
            "step": "action", "mode": "work", "req_id": req_id, "req_file": req_file,
            "task_file": sel["file_path"], "task_num": sel["task_num"],
            "task_title": sel["title"], "task_status": sel["status"],
            "task_description": sel["description"], "task_files": sel["files"]
        })
        write_prompt("action", "Type 'done' when finished or 'pause' to save and exit")

    elif step == "action":
        val = response.strip().lower()
        req_id = state.get("req_id", "")
        req_file = state.get("req_file", "")

        if val == "pause":
            out()
            out("  PAUSED")
            out("  Task stays as In Progress.")
            out(f"  Resume with: python workflows/work.py --requirement {req_id}")
            out()
            clear_state()
            return

        if val != "done":
            out("  Type 'done' or 'pause'.")
            save_state(state)
            write_prompt("action", "Type 'done' when finished or 'pause' to save and exit")
            return

        out()
        out("  COMPLETION PIPELINE")
        out("  ========================================")

        state["all_issues"] = []
        finalize_task_done(state)
        auto_commit()

        save_state({"step": "sync_knowledge", "mode": "work", "req_id": req_id, "req_file": req_file})
        write_prompt("sync_knowledge", "Sync knowledge file? Reply: y / n")

    elif step == "sync_knowledge":
        val = response.strip().lower()
        if val == "y":
            sync_script = SCRIPT_DIR / "sync-knowledge.py"
            if sync_script.exists():
                subprocess.run([sys.executable, str(sync_script)], cwd=str(PROJECT_DIR))
            else:
                out("  [WARN] sync-knowledge.py not found.")

        out()
        out("  Session complete.")
        clear_state()

    elif step == "tester_pick":
        val = response.strip().lower()
        if val in ("q", ""):
            out("  Tester session ended.")
            clear_state()
            return

        try:
            pick_idx = int(val)
        except ValueError:
            out("  Invalid number.")
            save_state(state)
            write_prompt("tester_pick", "Enter item # to review (or 'q' to quit)")
            return

        ready_content = READY_FILE.read_text(encoding="utf-8")
        blocks = re.split(r"(?=### REQ-\d+)", ready_content)
        items = []
        for block in blocks:
            m = re.match(r"^### (REQ-\d+) -- Task (\d+): (.+)", block)
            if not m:
                continue
            r_id, t_num, t_title = m.group(1), m.group(2), m.group(3).strip()
            test_status = "Awaiting Test"
            sm = re.search(r"\*\*Status\*\*\s*\|\s*([^|]+)", block)
            if sm: test_status = sm.group(1).strip()
            if test_status != "Awaiting Test":
                continue
            files = ""
            test_case = ""
            fm = re.search(r"\*\*Files Changed\*\*\s*\|\s*([^|]+)", block)
            if fm: files = fm.group(1).strip()
            tm = re.search(r"\*\*Test Case\*\*\s*\|\s*([^|]+)", block)
            if tm: test_case = tm.group(1).strip()
            items.append({"req_id": r_id, "task_num": t_num, "title": t_title,
                           "files": files, "test_case": test_case})

        if pick_idx < 1 or pick_idx > len(items):
            out("  Out of range.")
            save_state(state)
            write_prompt("tester_pick", "Enter item # to review (or 'q' to quit)")
            return

        selected = items[pick_idx - 1]
        out()
        out(f"  Testing: {selected['req_id']} Task {selected['task_num']}: {selected['title']}")
        out(f"  Test case at: {selected['test_case']}")

        save_state({
            "step": "tester_verdict", "mode": "tester",
            "tester_req_id": selected["req_id"], "tester_task_num": selected["task_num"],
            "tester_title": selected["title"], "tester_files": selected["files"]
        })
        write_prompt("tester_verdict", "Result? Reply: pass / fail")

    elif step == "tester_verdict":
        val = response.strip().lower()
        req_id = state["tester_req_id"]
        task_num = state["tester_task_num"]
        title = state["tester_title"]
        files = state.get("tester_files", "")

        if val == "pass":
            ready_content = READY_FILE.read_text(encoding="utf-8")
            pattern = rf"(### {re.escape(req_id)} -- Task {re.escape(task_num)}:.*?\*\*Status\*\*\s*\|\s*)Awaiting Test"
            ready_content = re.sub(pattern, r"\1Passed", ready_content, flags=re.DOTALL)
            READY_FILE.write_text(ready_content, encoding="utf-8")
            out("  PASSED. Item marked as verified.")

            py_script = SCRIPT_DIR / "update-testcases-excel.py"
            if py_script.exists():
                try:
                    result = subprocess.run(
                        [sys.executable, str(py_script), "find", "--req-id", req_id, "--task", title],
                        capture_output=True, text=True, encoding="utf-8"
                    )
                    tc_id = result.stdout.strip()
                    if tc_id and re.match(r"^TC-\d+$", tc_id):
                        update_test_case_excel_status(tc_id, "Pass")
                except Exception:
                    pass

            all_tasks = get_linked_tasks(req_id)
            all_done = all(t["status"] == "Done" for t in all_tasks)
            if all_done:
                all_reqs = parse_all_requirements()
                req = next((r for r in all_reqs if r["id"] == req_id), None)
                if req:
                    update_req_status(req_id, "done", req["file"])
                    out(f"  All tasks for {req_id} done and tested. Requirement CLOSED.")

            auto_commit()
            save_state({"step": "tester_pick", "mode": "tester"})
            write_prompt("tester_pick", "Enter item # to review (or 'q' to quit)")

        elif val == "fail":
            save_state({
                "step": "tester_feedback", "mode": "tester",
                "tester_req_id": req_id, "tester_task_num": task_num,
                "tester_title": title, "tester_files": files
            })
            write_prompt("tester_feedback", "What failed? Describe the issue")

        else:
            out("  Invalid. Enter 'pass' or 'fail'.")
            save_state(state)
            write_prompt("tester_verdict", "Result? Reply: pass / fail")

    elif step == "tester_feedback":
        feedback = response.strip()
        req_id = state["tester_req_id"]
        task_num = state["tester_task_num"]
        title = state["tester_title"]
        files = state.get("tester_files", "")

        if not feedback:
            feedback = "Test failed (no details)"

        ready_content = READY_FILE.read_text(encoding="utf-8")
        pattern = rf"(### {re.escape(req_id)} -- Task {re.escape(task_num)}:.*?\*\*Status\*\*\s*\|\s*)Awaiting Test"
        ready_content = re.sub(pattern, r"\1Failed", ready_content, flags=re.DOTALL)
        READY_FILE.write_text(ready_content, encoding="utf-8")

        task_file = TASKS_DIR / f"{TODAY}_tasks.md"
        fix_title = f"Fix: {title}"
        next_num = 1
        if task_file.exists():
            existing_content = task_file.read_text(encoding="utf-8")
            nums = [int(m.group(1)) for m in re.finditer(r"### Task (\d+):", existing_content)]
            if nums:
                next_num = max(nums) + 1

        new_task = f"""
### Task {next_num}: {fix_title}

| Field | Value |
|---|---|
| **Priority** | High |
| **Status** | Pending |
| **Estimated Hours** | 1-2 |
| **Files to Change** | {files} |
| **Source** | {req_id} |

**Description**: Failed test: {title}. Tester feedback: {feedback}

---"""

        if task_file.exists():
            existing = task_file.read_text(encoding="utf-8")
            task_file.write_text(existing + "\n" + new_task, encoding="utf-8")
        else:
            header = f"# Task Breakdown - {TODAY}\n\n---{new_task}"
            task_file.write_text(header, encoding="utf-8")

        py_script = SCRIPT_DIR / "update-testcases-excel.py"
        if py_script.exists():
            try:
                result = subprocess.run(
                    [sys.executable, str(py_script), "find", "--req-id", req_id, "--task", title],
                    capture_output=True, text=True, encoding="utf-8"
                )
                tc_id = result.stdout.strip()
                if tc_id and re.match(r"^TC-\d+$", tc_id):
                    update_test_case_excel_status(tc_id, "Fail", feedback)
            except Exception:
                pass

        out(f"  FAILED. Fix task created: Task {next_num} -- {fix_title}")
        out(f"  Linked to {req_id}")
        auto_commit()

        save_state({"step": "tester_pick", "mode": "tester"})
        write_prompt("tester_pick", "Enter item # to review (or 'q' to quit)")

    else:
        out(f"  Unknown step: {step}")
        clear_state()
        sys.exit(1)


def main():
    list_mode = False
    tester_mode = False
    requirement = step = response = None

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--list":
            list_mode = True; i += 1
        elif arg == "--tester":
            tester_mode = True; i += 1
        elif arg == "--requirement" and i + 1 < len(sys.argv):
            requirement = sys.argv[i + 1]; i += 2
        elif arg == "--step" and i + 1 < len(sys.argv):
            step = sys.argv[i + 1]; i += 2
        elif arg == "--response" and i + 1 < len(sys.argv):
            response = sys.argv[i + 1]; i += 2
        else:
            i += 1

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    if list_mode:
        do_list()
    elif tester_mode and not step:
        do_tester()
    elif requirement and not step:
        start_work(requirement)
    elif step:
        process_step(step, response or "")
    else:
        out()
        out("  Usage:")
        out("  python work.py --list                    Show open requirements")
        out("  python work.py --requirement REQ-001     Start working on a requirement")
        out("  python work.py --tester                  Tester mode")
        out()


if __name__ == "__main__":
    main()
