#!/usr/bin/env python3
"""
Weekly report generator -- summarizes tasks for the current week.

Usage:
    python workflows/report.py
    python workflows/report.py --week-offset -1
"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TASKS_DIR = SCRIPT_DIR / "tasks"
REPORTS_DIR = SCRIPT_DIR / "reports"
KNOWLEDGE_FILE = SCRIPT_DIR.parent / "knowledge" / "{{PROJECT_NAME}}-project.md"
TODAY = datetime.now()


def get_max_hours(range_str):
    parts = range_str.split("-")
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0


def get_min_hours(range_str):
    parts = range_str.split("-")
    try:
        return int(parts[0])
    except (ValueError, IndexError):
        return 0


def priority_weight(p):
    return {"High": 0, "Medium": 1, "Low": 2}.get(p, 3)


def parse_task_files(from_date=None, to_date=None, all_files=False):
    all_tasks = []
    if not TASKS_DIR.exists():
        return all_tasks

    for f in sorted(TASKS_DIR.glob("*_tasks.md")):
        date_str = f.stem.replace("_tasks", "")
        try:
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue

        if not all_files and from_date and to_date:
            if file_date.date() < from_date.date() or file_date.date() > to_date.date():
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
            if pm:
                priority = pm.group(1)
            sm = re.search(r"\*\*Status\*\*\s*\|\s*([\w\s]+)", block)
            if sm:
                status = sm.group(1).strip()
            hm = re.search(r"\*\*Estimated Hours\*\*\s*\|\s*([\d\-]+)", block)
            if hm:
                hours = hm.group(1)
            fm = re.search(r"\*\*Files to Change\*\*\s*\|\s*([^|]+)", block)
            if fm:
                files = fm.group(1).strip()
            dm = re.search(r"\*\*Description\*\*:\s*(.+)", block)
            if dm:
                description = dm.group(1).strip()

            days_since = (TODAY - file_date).days
            overdue = days_since > 3 and status != "Done"

            all_tasks.append({
                "file": str(f),
                "file_name": f.name,
                "file_date": file_date,
                "days_since": days_since,
                "task_num": task_num,
                "title": title,
                "priority": priority,
                "status": status,
                "hours": hours,
                "files": files,
                "description": description,
                "overdue": overdue,
            })

    return all_tasks


def get_blockers():
    blockers = []
    if KNOWLEDGE_FILE.exists():
        content = KNOWLEDGE_FILE.read_text(encoding="utf-8")
        m = re.search(r"(?s)## Known Issues\s*\n(.*?)(\n## |\Z)", content)
        if m:
            for line in m.group(1).split("\n"):
                if re.match(r"^-\s+", line):
                    blockers.append(re.sub(r"^-\s+", "", line))
    return blockers


def main():
    week_offset = 0
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--week-offset" and i < len(sys.argv) - 1:
            try:
                week_offset = int(sys.argv[i + 1])
            except ValueError:
                pass

    # Calculate week boundaries (Monday to Sunday)
    target_date = TODAY + timedelta(days=week_offset * 7)
    day_of_week = target_date.weekday()  # Monday=0
    week_start = (target_date - timedelta(days=day_of_week)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=6)

    # ISO week number
    iso_cal = week_start.isocalendar()
    week_label = f"{iso_cal[0]}-W{iso_cal[1]:02d}"
    output_file = REPORTS_DIR / f"{week_label}.md"

    print()
    print("  ========================================")
    print("    WEEKLY REPORT GENERATOR")
    print("  ========================================")
    print(f"  Week:  {week_label} ({week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')})")
    print()

    if not TASKS_DIR.exists():
        print("  No tasks directory found.")
        sys.exit(0)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Parse tasks
    week_tasks = parse_task_files(from_date=week_start, to_date=week_end)
    all_tasks = parse_task_files(to_date=week_end, all_files=True)

    completed = [t for t in week_tasks if t["status"] == "Done"]
    in_progress = [t for t in week_tasks if "In Progress" in t["status"]]
    pending = [t for t in week_tasks if t["status"] == "Pending"]
    overdue_all = [t for t in all_tasks if t["overdue"] and t["status"] != "Done"]

    completed_hrs_max = sum(get_max_hours(t["hours"]) for t in completed)
    completed_hrs_min = sum(get_min_hours(t["hours"]) for t in completed)
    remaining_hrs_max = sum(get_max_hours(t["hours"]) for t in in_progress + pending)

    blockers = get_blockers()

    # Build report
    report = f"""# Weekly Report - {week_label}

**Period**: {week_start.strftime('%Y-%m-%d')} (Mon) to {week_end.strftime('%Y-%m-%d')} (Sun)
**Generated**: {TODAY.strftime('%Y-%m-%d %H:%M')}
**Project**: {{{{PROJECT_NAME}}}}

---

## Summary

| Metric | Count |
|---|---|
| Tasks completed | {len(completed)} |
| Tasks in progress | {len(in_progress)} |
| Tasks pending | {len(pending)} |
| Tasks overdue | {len(overdue_all)} |
| **Total this week** | **{len(week_tasks)}** |
| Hours completed | ~{completed_hrs_min}-{completed_hrs_max} hrs |
| Hours remaining | ~{remaining_hrs_max} hrs (upper bound) |

---

## Completed

"""

    if not completed:
        report += "No tasks completed this week.\n"
    else:
        for t in sorted(completed, key=lambda x: priority_weight(x["priority"])):
            report += f"- [x] **{t['title']}** ({t['priority']}, {t['hours']} hrs) -- {t['files']}\n"

    report += "\n---\n\n## In Progress\n\n"

    if not in_progress:
        report += "No tasks currently in progress.\n"
    else:
        for t in sorted(in_progress, key=lambda x: priority_weight(x["priority"])):
            overdue_tag = f" **[OVERDUE {t['days_since']}d]**" if t["overdue"] else ""
            report += f"- [ ] **{t['title']}** ({t['priority']}, {t['hours']} hrs){overdue_tag} -- {t['files']}\n"

    report += "\n---\n\n## Pending\n\n"

    if not pending:
        report += "No pending tasks.\n"
    else:
        for prio in ["High", "Medium", "Low"]:
            group = [t for t in pending if t["priority"] == prio]
            if not group:
                continue
            report += f"\n### {prio} Priority\n\n"
            for t in group:
                overdue_tag = f" **[OVERDUE {t['days_since']}d]**" if t["overdue"] else ""
                report += f"- [ ] {t['title']} ({t['hours']} hrs){overdue_tag} -- {t['files']}\n"

    report += "\n---\n\n## Overdue Tasks\n\n"

    if not overdue_all:
        report += "No overdue tasks.\n"
    else:
        for t in sorted(overdue_all, key=lambda x: -x["days_since"]):
            report += f"- **{t['title']}** -- {t['days_since']} days old, status: {t['status']}, from {t['file_name']}\n"

    report += "\n---\n\n## Blockers\n\n"

    if not blockers:
        report += "No known blockers.\n"
    else:
        for b in blockers:
            report += f"- {b}\n"

    # Next week focus
    all_incomplete = sorted(
        [t for t in all_tasks if t["status"] != "Done"],
        key=lambda x: (priority_weight(x["priority"]), -x["days_since"])
    )
    focus_tasks = all_incomplete[:5]

    report += "\n---\n\n## Next Week's Recommended Focus\n\n"

    if not focus_tasks:
        report += "All tasks complete. Plan new work.\n"
    else:
        for rank, t in enumerate(focus_tasks, 1):
            overdue_tag = " (OVERDUE)" if t["overdue"] else ""
            report += f"{rank}. **[{t['priority']}]** {t['title']}{overdue_tag} -- {t['hours']} hrs, files: {t['files']}\n"

        report += "\n**Recommendations:**\n\n"

        high_count = sum(1 for t in all_incomplete if t["priority"] == "High")
        overdue_count = len(overdue_all)

        if overdue_count > 0:
            report += f"- Clear {overdue_count} overdue task(s) first -- they are dragging behind\n"
        if high_count > 0:
            report += f"- {high_count} high-priority task(s) need attention\n"
        if remaining_hrs_max > 20:
            report += f"- ~{remaining_hrs_max} hrs of estimated work remaining -- consider trimming scope\n"
        if blockers:
            report += "- Resolve blockers to unblock deployment and downstream work\n"
        if high_count == 0 and overdue_count == 0:
            report += "- No urgent items -- good time to tackle medium-priority improvements\n"

    report += "\n---\n\n*Generated by workflows/report.py*\n"

    # Write report
    output_file.write_text(report, encoding="utf-8")

    # Terminal output
    print("  SUMMARY")
    print("  ----------------------------------------")
    print(f"  Completed:     {len(completed)} tasks (~{completed_hrs_min}-{completed_hrs_max} hrs)")
    print(f"  In Progress:   {len(in_progress)} tasks")
    print(f"  Pending:       {len(pending)} tasks")
    print(f"  Overdue:       {len(overdue_all)} tasks")
    print(f"  Hours left:    ~{remaining_hrs_max} hrs")
    print()

    if blockers:
        print("  BLOCKERS")
        print("  ----------------------------------------")
        for b in blockers:
            print(f"  ! {b}")
        print()

    if focus_tasks:
        print("  NEXT WEEK FOCUS")
        print("  ----------------------------------------")
        for rank, t in enumerate(focus_tasks, 1):
            overdue_tag = " [OVERDUE]" if t["overdue"] else ""
            print(f"  {rank}. [{t['priority']}] {t['title']}{overdue_tag}")
        print()

    print(f"  Report saved: {output_file}")
    print()


if __name__ == "__main__":
    main()
