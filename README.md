# Dev Autopilot — Workflow Automation Templates

Dev Autopilot turns Claude Code from a coding assistant into a full project manager. It tracks client requirements, breaks them into tasks, generates test cases, writes weekly reports, and deploys your app to AWS — all through natural language commands in your terminal. Clone this repo, run the setup script, and your next project ships with a built-in PM.

---

## Quick Start

### Mode 1: Fresh Project (start from scratch)

```bash
# 1. Clone this repo anywhere (NOT inside an existing project)
git clone https://github.com/vishaludemy37/dev-autopilot-templates.git
cd dev-autopilot-templates

# 2. Run the setup script
python setup-new-project.py
# Choose mode: 1, fill in your project details
# → Creates a new project folder with everything set up
```

### Mode 2: Retrofit Existing Project (add to your codebase)

```bash
# 1. Go to your existing project
cd /path/to/your-project

# 2. Download JUST the setup script (do NOT clone the repo here)
curl -O https://raw.githubusercontent.com/vishaludemy37/dev-autopilot-templates/main/setup-new-project.py

# 3. Run it
python setup-new-project.py
# Choose mode: 2, fill in your project details
# → Downloads templates and workflow scripts from GitHub automatically

# 4. Clean up the setup script (it's no longer needed)
rm setup-new-project.py
```

> **Why not clone?** Cloning creates a nested `.git` folder inside your project, which causes conflicts with your own repo. Mode 2 downloads everything it needs directly from GitHub — no cloning required.

The setup script will walk you through everything interactively.

---

## Two Modes

### Mode 1: Fresh Project

Starting a brand-new project? The setup script will:
- Create your project directory with the full workflow structure
- Generate a customized `CLAUDE.md` with all trigger words configured
- Copy all 8 workflow scripts with your project name baked in
- Initialize git and optionally create a GitHub repo
- You're ready to code in under 2 minutes

**Example:**
```
$ python setup-new-project.py
> Choose mode: 1 (Fresh project)
> Project name: my-saas-app
> Tech stack: Next.js + Prisma + PostgreSQL
> GitHub repo: myusername/my-saas-app
> Developer name: John

Done! cd my-saas-app and start coding.
```

### Mode 2: Retrofit Existing Project

Already have a codebase? Download `setup-new-project.py` into your project and run it — no cloning needed. It fetches all templates and scripts directly from GitHub.

- Adds the `workflows/` directory with all scripts
- Generates `CLAUDE.md` tailored to your project
- Creates a knowledge file for project context
- Commits everything — zero disruption to your existing code

**Example:**
```
$ cd /path/to/existing-project
$ curl -O https://raw.githubusercontent.com/vishaludemy37/dev-autopilot-templates/main/setup-new-project.py
$ python setup-new-project.py
> Choose mode: 2 (Retrofit existing project)
> Project name: existing-app
> ...

Done! Your existing project now has Dev Autopilot.
$ rm setup-new-project.py   # clean up
```

---

## All 8 Workflow Scripts

| Script | What it does |
|---|---|
| `standup.py` | Daily standup — shows commits, task status, overdue items, focus list |
| `requirements.py` | Logs client requirements, links to tasks, full audit trail |
| `work.py` | Manages work sessions — pick task, code, mark done, auto-review |
| `report.py` | Generates weekly markdown reports with metrics and recommendations |
| `deploy.py` | Guided AWS EC2 deployment — repo setup, SSH, Gunicorn, Nginx, SSL |
| `sync-knowledge.py` | Syncs project knowledge file with recent code changes |
| `generate-frd.py` | Generates Functional Requirement Documents from requirements |
| `create-tasks.py` | Breaks requirements into prioritized tasks with file targets |

Plus 2 supporting scripts: `generate-frd-docx.py` (FRD to Word) and `update-testcases-excel.py` (test case Excel manager).

---

## Prerequisites

- **Python 3.9+** — for running workflow scripts
- **Node.js 18+** — if your project uses Node (not required for workflows)
- **Git** — version control
- **Claude Code** — Anthropic's CLI (`npm install -g @anthropic-ai/claude-code`)
- **Anthropic API Key** — set as `ANTHROPIC_API_KEY` in your `.env`
- **GitHub Account** — for repo hosting and optional dashboard integration

---

## How It Works

See [docs/how-it-works.md](docs/how-it-works.md) for a detailed explanation of:
- The 4 phases (Capture → Build → Test → Ship)
- What each script does
- The Done Pipeline (auto code review + test case generation)
- Dashboard architecture

---

## Course Link

> **Udemy Course**: _Coming soon — link will be added here_

---

## License

MIT
