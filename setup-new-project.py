#!/usr/bin/env python3
"""
Dev Autopilot — Project Setup Script (standalone)

Downloads all templates and workflow scripts from GitHub at runtime.
No companion files needed — just curl this script and run it.

Usage:
    curl -O https://raw.githubusercontent.com/vishaludemy37/dev-autopilot-templates/main/setup-new-project.py
    python setup-new-project.py
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure 'requests' is available — auto-install if missing
# ---------------------------------------------------------------------------
try:
    import requests
except ImportError:
    print("  Installing requests...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE = "https://raw.githubusercontent.com/vishaludemy37/dev-autopilot-templates/main"

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

WORKFLOW_SCRIPTS = [
    "standup.py", "requirements.py", "work.py", "report.py",
    "deploy.py", "sync-knowledge.py", "generate-frd.py", "create-tasks.py",
    "generate-frd-docx.py", "update-testcases-excel.py",
]

WORKFLOW_SUBDIRS = [
    "tasks", "requirements", "testing", "frd", "reports", ".session"
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def p(msg, color=""):
    print(f"{color}{msg}{RESET}" if color else msg)


def ask(prompt_text, default=""):
    if default:
        result = input(f"  {prompt_text} [{default}]: ").strip()
        return result if result else default
    result = input(f"  {prompt_text}: ").strip()
    return result


def fetch(path):
    """Fetch a file from the GitHub repo."""
    url = f"{BASE}/{path}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def banner():
    p("")
    p("  =============================================", CYAN)
    p("    DEV AUTOPILOT — Project Setup", BOLD)
    p("  =============================================", CYAN)
    p("")
    p("  This script sets up the Dev Autopilot workflow")
    p("  system in your project. You'll get:")
    p("")
    p("    - Daily standups with task tracking")
    p("    - Requirement logging & traceability")
    p("    - Work session management with code review")
    p("    - Weekly report generation")
    p("    - Guided EC2 deployment")
    p("    - FRD generation & test case management")
    p("")


# ---------------------------------------------------------------------------
# Collect project info
# ---------------------------------------------------------------------------
def collect_info():
    p("  PROJECT INFORMATION", BOLD)
    p("  -----------------------------------------")

    info = {}
    info["project_name"] = ask("Project name (e.g., my-saas-app)")
    if not info["project_name"]:
        p("  Project name is required.", RED)
        sys.exit(1)

    info["project_description"] = ask("One-line description", f"A project called {info['project_name']}")
    info["tech_stack"] = ask("Tech stack (e.g., Flask + PostgreSQL, Next.js + Prisma)", "Python")
    info["github_repo_url"] = ask("GitHub repo URL (e.g., https://github.com/user/repo) or leave blank", "")
    info["developer_name"] = ask("Developer name", os.environ.get("USER", os.environ.get("USERNAME", "Developer")))

    p("")
    p("  SUMMARY", BOLD)
    p("  -----------------------------------------")
    p(f"  Name:        {info['project_name']}")
    p(f"  Description: {info['project_description']}")
    p(f"  Tech Stack:  {info['tech_stack']}")
    p(f"  GitHub:      {info['github_repo_url'] or '(not set)'}")
    p(f"  Developer:   {info['developer_name']}")
    p("")

    confirm = ask("Proceed? (y/n)", "y")
    if confirm.lower() != "y":
        p("  Cancelled.", YELLOW)
        sys.exit(0)

    return info


# ---------------------------------------------------------------------------
# Placeholder replacement
# ---------------------------------------------------------------------------
def replace_placeholders(content, info):
    repo_short = ""
    url = info.get("github_repo_url", "")
    if url:
        repo_short = url.rstrip("/").replace("https://github.com/", "").replace(".git", "")

    replacements = {
        "{{PROJECT_NAME}}": info["project_name"],
        "{{PROJECT_DESCRIPTION}}": info["project_description"],
        "{{TECH_STACK}}": info["tech_stack"],
        "{{GITHUB_REPO}}": repo_short,
        "{{DEVELOPER_NAME}}": info["developer_name"],
        "{{DATE_CREATED}}": datetime.now().strftime("%Y-%m-%d"),
        "{{RUN_COMMANDS}}": "# Add your run commands here",
        "{{ENV_VARS_LIST}}": "- `ANTHROPIC_API_KEY` — enables AI features in Claude Code",
        "{{ARCHITECTURE_DESCRIPTION}}": "<!-- Describe your project architecture here -->",
        "{{MODULE_DESCRIPTIONS}}": "<!-- Describe your project modules here -->",
        "{{FRONTEND_DESCRIPTION}}": "<!-- Describe your frontend here -->",
        "{{DESIGN_PATTERNS}}": "<!-- Describe key design patterns here -->",
        "{{API_ENDPOINTS_TABLE}}": "<!-- Add API endpoints table here -->",
        "{{DEPLOYMENT_ENVIRONMENT}}": "AWS EC2 (Ubuntu)",
        "{{DEPLOYMENT_URL}}": "http://your-server-ip",
        "{{FEATURE_1}}": "Core feature 1",
        "{{FEATURE_1_DESCRIPTION}}": "Description of feature 1",
        "{{FEATURE_2}}": "Core feature 2",
        "{{FEATURE_2_DESCRIPTION}}": "Description of feature 2",
        "{{ENDPOINT_1}}": "/api/example",
        "{{METHOD_1}}": "GET",
        "{{PURPOSE_1}}": "Example endpoint",
        "{{ENDPOINT_2}}": "/api/data",
        "{{METHOD_2}}": "POST",
        "{{PURPOSE_2}}": "Submit data",
    }
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    return content


# ---------------------------------------------------------------------------
# Setup steps — all fetch from GitHub
# ---------------------------------------------------------------------------
def download_workflow_scripts(target_dir, info):
    """Download all workflow scripts from GitHub."""
    workflows_dir = target_dir / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    for subdir in WORKFLOW_SUBDIRS:
        (workflows_dir / subdir).mkdir(parents=True, exist_ok=True)

    downloaded = 0
    for script in WORKFLOW_SCRIPTS:
        dst = workflows_dir / script
        if dst.exists():
            p(f"  [SKIP] Already exists: workflows/{script}", YELLOW)
            continue

        try:
            content = fetch(f"workflows/{script}")
        except requests.RequestException as e:
            p(f"  [WARN] Failed to download workflows/{script}: {e}", YELLOW)
            continue

        content = replace_placeholders(content, info)
        dst.write_text(content, encoding="utf-8")
        downloaded += 1

    p(f"  [OK] Downloaded {downloaded} workflow script(s)", GREEN)
    return downloaded


def generate_claude_md(target_dir, info):
    """Download and generate CLAUDE.md from template."""
    output_path = target_dir / "CLAUDE.md"
    if output_path.exists():
        p("  [SKIP] CLAUDE.md already exists", YELLOW)
        return False

    try:
        content = fetch("templates/CLAUDE.md.template")
    except requests.RequestException as e:
        p(f"  [WARN] Failed to download CLAUDE.md template: {e}", YELLOW)
        return False

    content = replace_placeholders(content, info)
    output_path.write_text(content, encoding="utf-8")
    p("  [OK] Generated CLAUDE.md", GREEN)
    return True


def generate_knowledge(target_dir, info):
    """Download and generate knowledge file from template."""
    knowledge_dir = target_dir / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    output_path = knowledge_dir / f"{info['project_name']}-project.md"

    if output_path.exists():
        p("  [SKIP] Knowledge file already exists", YELLOW)
        return False

    try:
        content = fetch("templates/knowledge.md.template")
    except requests.RequestException as e:
        p(f"  [WARN] Failed to download knowledge template: {e}", YELLOW)
        return False

    content = replace_placeholders(content, info)
    output_path.write_text(content, encoding="utf-8")
    p(f"  [OK] Generated knowledge/{info['project_name']}-project.md", GREEN)
    return True


def create_gitignore(target_dir):
    gitignore_path = target_dir / ".gitignore"
    if gitignore_path.exists():
        p("  [SKIP] .gitignore already exists", YELLOW)
        return False

    content = """# Workflow session data (per-project, not shared)
workflows/.session/

# FRD generated documents (per-project)
workflows/frd/

# Environment and secrets
.env
.env.local

# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
venv/
.venv/

# Node
node_modules/

# OS
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/
*.swp
*.swo

# Logs
*.log
workflows/deploy_*.log
"""
    gitignore_path.write_text(content, encoding="utf-8")
    p("  [OK] Created .gitignore", GREEN)
    return True


def update_gitignore(target_dir):
    """Add workflow entries to an existing .gitignore."""
    gitignore_path = target_dir / ".gitignore"
    workflow_entries = "\n# Dev Autopilot\nworkflows/.session/\nworkflows/frd/\n"
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if "workflows/.session/" not in content:
            content += workflow_entries
            gitignore_path.write_text(content, encoding="utf-8")
            p("  [OK] Added workflow entries to .gitignore", GREEN)
        else:
            p("  [SKIP] .gitignore already has workflow entries", YELLOW)
    else:
        create_gitignore(target_dir)


def create_env_example(target_dir):
    env_path = target_dir / ".env.example"
    if env_path.exists():
        p("  [SKIP] .env.example already exists", YELLOW)
        return False

    content = """# Copy this to .env and fill in your values
# cp .env.example .env

# Required for Claude Code workflow scripts
ANTHROPIC_API_KEY=your-api-key-here

# Required for GitHub integration (standup commit tracking)
GITHUB_TOKEN=your-github-token-here

# Add your project-specific environment variables below
"""
    env_path.write_text(content, encoding="utf-8")
    p("  [OK] Created .env.example", GREEN)
    return True


def setup_git(target_dir, info):
    """Initialize git if needed, commit, and optionally add remote."""
    git_dir = target_dir / ".git"

    if git_dir.exists():
        p("  [SKIP] Git already initialized", YELLOW)
    else:
        subprocess.run(["git", "init"], cwd=str(target_dir), capture_output=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=str(target_dir), capture_output=True)
        p("  [OK] Git initialized", GREEN)

    # Commit
    subprocess.run(["git", "add", "."], cwd=str(target_dir), capture_output=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(target_dir), capture_output=True)
    if result.returncode != 0:
        subprocess.run(
            ["git", "commit", "-m", f"Add Dev Autopilot to {info['project_name']}"],
            cwd=str(target_dir), capture_output=True
        )
        p("  [OK] Changes committed", GREEN)
    else:
        p("  [SKIP] No changes to commit", YELLOW)

    # Remote
    repo_url = info.get("github_repo_url", "")
    if repo_url:
        # Check if origin already exists
        check = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(target_dir), capture_output=True, text=True
        )
        if check.returncode != 0:
            subprocess.run(
                ["git", "remote", "add", "origin", repo_url],
                cwd=str(target_dir), capture_output=True
            )
            p(f"  [OK] Added remote: {repo_url}", GREEN)
        else:
            p(f"  [SKIP] Remote origin already set to: {check.stdout.strip()}", YELLOW)


def print_summary(info, target_dir):
    """Print the final success message."""
    name = info["project_name"]
    stack = info["tech_stack"]
    loc = str(target_dir)

    p("")
    p("  =========================================", GREEN)
    p("  SETUP COMPLETE!", GREEN)
    p("  =========================================", GREEN)
    p("")
    p(f"  Project : {name}")
    p(f"  Stack   : {stack}")
    p(f"  Location: {loc}")
    p("")
    p("  Your first commands (type these in Claude Code):", BOLD)
    p("")
    p('    > client emailed asking for [feature]')
    p('    > run standup')
    p('    > work on REQ-001')
    p('    > done for today')
    p("")


# ---------------------------------------------------------------------------
# MODE 1: Fresh Project
# ---------------------------------------------------------------------------
def mode_fresh(info):
    p("")
    p("  MODE 1: FRESH PROJECT", BOLD)
    p("  =========================================", CYAN)
    p("")

    target_dir = Path.cwd()
    p(f"  Target: {target_dir}\n")

    p("  STEP 1: Downloading templates from GitHub...", BOLD)
    p("  STEP 1a: Creating .gitignore", BOLD)
    create_gitignore(target_dir)

    p("  STEP 2: Generating CLAUDE.md", BOLD)
    generate_claude_md(target_dir, info)

    p("  STEP 3: Generating knowledge file", BOLD)
    generate_knowledge(target_dir, info)

    p("  STEP 4: Downloading workflow scripts", BOLD)
    download_workflow_scripts(target_dir, info)

    p("  STEP 5: Creating .env.example", BOLD)
    create_env_example(target_dir)

    p("  STEP 6: Setting up git", BOLD)
    setup_git(target_dir, info)

    print_summary(info, target_dir)


# ---------------------------------------------------------------------------
# MODE 2: Retrofit Existing Project
# ---------------------------------------------------------------------------
def mode_retrofit(info):
    p("")
    p("  MODE 2: RETROFIT EXISTING PROJECT", BOLD)
    p("  =========================================", CYAN)
    p("")

    target_dir = Path.cwd()

    # Check for git
    git_dir = target_dir / ".git"
    if not git_dir.exists():
        p("  [WARN] Not a git repository.", YELLOW)
        init = ask("Initialize git?", "y")
        if init.lower() == "y":
            subprocess.run(["git", "init"], cwd=str(target_dir), capture_output=True)
            subprocess.run(["git", "branch", "-M", "main"], cwd=str(target_dir), capture_output=True)
            p("  [OK] Git initialized", GREEN)
        else:
            p("  Cannot proceed without git.", RED)
            sys.exit(1)

    p(f"  Target: {target_dir}\n")

    p("  STEP 1: Generating CLAUDE.md", BOLD)
    generate_claude_md(target_dir, info)

    p("  STEP 2: Generating knowledge file", BOLD)
    generate_knowledge(target_dir, info)

    p("  STEP 3: Downloading workflow scripts", BOLD)
    download_workflow_scripts(target_dir, info)

    p("  STEP 4: Updating .gitignore", BOLD)
    update_gitignore(target_dir)

    p("  STEP 5: Creating .env.example", BOLD)
    create_env_example(target_dir)

    p("  STEP 6: Committing changes", BOLD)
    setup_git(target_dir, info)

    print_summary(info, target_dir)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    banner()

    p("  Choose a mode:", BOLD)
    p("    1. Fresh project     — create a new project from scratch")
    p("    2. Retrofit existing — add Dev Autopilot to an existing codebase")
    p("")

    mode = ask("Mode (1 or 2)", "1")

    if mode not in ("1", "2"):
        p("  Invalid choice. Enter 1 or 2.", RED)
        sys.exit(1)

    info = collect_info()

    if mode == "1":
        mode_fresh(info)
    else:
        mode_retrofit(info)


if __name__ == "__main__":
    main()
