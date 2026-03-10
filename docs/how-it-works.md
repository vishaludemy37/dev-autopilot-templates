# How Dev Autopilot Works

Dev Autopilot is a workflow automation system that turns Claude Code into a full project manager, task tracker, and deployment assistant. Instead of just writing code, Claude Code now tracks requirements, generates test cases, writes reports, and deploys your app — all through natural language commands.

---

## The 4 Phases

Every piece of work flows through four phases:

### Phase 1: Capture

A client sends you a requirement via email, WhatsApp, or a call. You tell Claude Code:

> "Client emailed asking for a dark mode toggle"

Claude Code automatically:
- Logs it as REQ-001 with client name, channel, and timestamp
- Breaks it into development tasks with file targets and hour estimates
- Links tasks back to the requirement for full traceability

**Scripts involved**: `requirements.py`, `create-tasks.py`

### Phase 2: Build

You say "work on REQ-001" and Claude Code:
- Shows the requirement, linked tasks, and FRD (if generated)
- Lets you pick a task to start
- Marks it as "In Progress"
- When you say "done", it runs the Done Pipeline — code review, test case generation, Excel update, and READY_FOR_TESTING update

**Scripts involved**: `work.py`, `standup.py`, `generate-frd.py`

### Phase 3: Test

A tester (or you) runs `python workflows/work.py --tester` to see all items awaiting testing. For each item:
- Mark as **Pass** → item closes, requirement status updates
- Mark as **Fail** → a fix task is auto-created with High priority, linked back to the original requirement

**Scripts involved**: `work.py` (tester mode), `update-testcases-excel.py`

### Phase 4: Ship

When ready, you say "deploy to EC2" and the deploy script walks you through:
- GitHub repo creation (if needed)
- Pre-deployment checklist
- SSH connection and dependency installation
- Code deployment via git clone/pull
- Gunicorn + Nginx configuration
- SSL setup guidance

**Scripts involved**: `deploy.py`

---

## All 8 Scripts Explained

### 1. `standup.py` — Daily Standup

Shows today's commits, task status (pending/in-progress/done), overdue items, and a focus list for the day. Interactive — lets you update task statuses and reopen failed test cases.

**Trigger**: Say "run standup"

### 2. `requirements.py` — Requirement Tracker

Logs client requirements with REQ IDs, links them to tasks, and provides full audit trails. Supports list mode (see all requirements) and trace mode (deep-dive into one requirement with its tasks and test cases).

**Trigger**: Say "show requirements" or describe a client request naturally

### 3. `work.py` — Work Session Manager

Manages coding sessions. Pick a requirement, pick a task, code it, say "done". Also has a tester mode for QA review. Handles the full Done Pipeline: code review, test case generation, and status updates.

**Trigger**: Say "work on REQ-001" or "show work"

### 4. `report.py` — Weekly Report Generator

Generates a markdown report summarizing the week: tasks completed, in progress, pending, overdue, blockers, and recommended focus for next week. Saves to `workflows/reports/`.

**Trigger**: Say "generate report" or "weekly report"

### 5. `deploy.py` — Guided Deployment

Step-by-step deployment to AWS EC2 via Git. Handles GitHub repo creation, SSH setup, dependency installation, code deployment, Gunicorn systemd service, Nginx reverse proxy, and SSL guidance. Works for both fresh deploys and updates.

**Trigger**: Say "deploy to EC2"

### 6. `sync-knowledge.py` — Knowledge Sync

Scans recent git commits, reads changed files, and outputs a structured report. Claude Code then updates your project's knowledge file with new information — architecture changes, new features, bug fixes.

**Trigger**: Say "done for today" (runs automatically as part of closing)

### 7. `generate-frd.py` — FRD Generator

Creates Functional Requirement Documents from logged requirements. Outputs structured data that Claude Code uses to generate a full FRD with sections: Executive Summary, Functional Requirements (FR-001, FR-002...), Technical Approach, Dependencies, and Sign-off.

**Trigger**: Say "generate FRD for REQ-001"

### 8. `create-tasks.py` — Task Breakdown

Automatically breaks a requirement into development tasks with:
- Priority levels (High/Medium/Low)
- Hour estimates
- File targets (which files to change)
- Markdown task files saved to `workflows/tasks/`

**Trigger**: Runs automatically when a requirement is logged

---

## Supporting Scripts

### `generate-frd-docx.py`

Converts FRD markdown files into styled Word (.docx) documents with proper headings, tables, and formatting. Uses python-docx.

### `update-testcases-excel.py`

Manages `workflows/testing/testcases.xlsx` — adds new test cases, updates pass/fail status, and tracks test history with styled Excel formatting.

---

## The Done Pipeline

When you mark a task as "done", this automated pipeline runs:

1. **Task status update** → marked as Done in the task file
2. **Code review** → Claude Code reads the changed files and reviews for bugs, security issues, and edge cases
3. **Test case generation** → generates test steps, expected results, and edge cases; maps to FRD acceptance criteria if available
4. **Excel update** → adds the test case to `testcases.xlsx` with "Pending Test" status
5. **READY_FOR_TESTING** → appends the item to `READY_FOR_TESTING.md` for testers
6. **Knowledge sync** → optionally syncs the knowledge file with latest changes

---

## Dashboard Architecture

All workflow data is stored as markdown and Excel files inside the `workflows/` directory:

```
workflows/
  tasks/           → YYYY-MM-DD_tasks.md files
  requirements/    → YYYY-MM-DD_requirements.md files
  testing/         → YYYY-MM-DD_testcases.md + testcases.xlsx
  frd/             → REQ-XXX-FRD.md + REQ-XXX-FRD.docx
  reports/         → YYYY-WXX.md weekly reports
  .session/        → temporary state files (gitignored)
```

This data is auto-committed to GitHub after every update, making it readable by any dashboard that can parse markdown/JSON from a GitHub repo via the API.

---

## Quick Reference

| You say | What happens |
|---|---|
| "Client wants X" | Requirement logged, tasks created |
| "show requirements" | List all open requirements |
| "work on REQ-001" | Start a work session |
| "done" | Done Pipeline runs |
| "run standup" | Daily standup with task overview |
| "generate report" | Weekly summary generated |
| "deploy to EC2" | Guided deployment starts |
| "done for today" | Knowledge synced, session recap |
