#!/usr/bin/env python3
"""
Dev Autopilot — Project Setup Script

Sets up a new project or retrofits an existing one with the Dev Autopilot
workflow system (standup, requirements, work sessions, deployment, etc.)

Usage:
    python setup-new-project.py
"""

import os
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

TEMPLATE_DIR = Path(__file__).resolve().parent
WORKFLOWS_SRC = TEMPLATE_DIR / "workflows"
TEMPLATES_DIR = TEMPLATE_DIR / "templates"

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/vishaludemy37/dev-autopilot-templates/main"

WORKFLOW_SCRIPTS = [
    "standup.py", "requirements.py", "work.py", "report.py",
    "deploy.py", "sync-knowledge.py", "generate-frd.py", "create-tasks.py",
    "generate-frd-docx.py", "update-testcases-excel.py",
]

WORKFLOW_SUBDIRS = [
    "tasks", "requirements", "testing", "frd", "reports", ".session"
]


def p(msg, color=""):
    """Print with optional color."""
    print(f"{color}{msg}{RESET}" if color else msg)


def ask(prompt_text, default=""):
    """Ask user for input with optional default."""
    if default:
        result = input(f"  {prompt_text} [{default}]: ").strip()
        return result if result else default
    result = input(f"  {prompt_text}: ").strip()
    return result


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


def fetch_remote_file(relative_path):
    """Fetch a file from the GitHub repo. Returns content string or None."""
    url = f"{GITHUB_RAW_BASE}/{relative_path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dev-autopilot-setup"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        p(f"  [WARN] Failed to fetch {relative_path}: {e}", YELLOW)
        return None


def read_file_or_fetch(local_path, remote_relative_path):
    """Read from local path if it exists, otherwise fetch from GitHub."""
    if local_path and Path(local_path).exists():
        return Path(local_path).read_text(encoding="utf-8")
    return fetch_remote_file(remote_relative_path)


def collect_info():
    """Collect project information from user."""
    p("  PROJECT INFORMATION", BOLD)
    p("  -----------------------------------------")

    info = {}
    info["project_name"] = ask("Project name (e.g., my-saas-app)")
    if not info["project_name"]:
        p("  Project name is required.", RED)
        sys.exit(1)

    info["project_description"] = ask("One-line description", f"A project called {info['project_name']}")
    info["tech_stack"] = ask("Tech stack (e.g., Flask + PostgreSQL, Next.js + Prisma)", "Python")
    info["github_repo"] = ask("GitHub repo (e.g., username/repo-name)", "")
    info["developer_name"] = ask("Developer name", os.environ.get("USER", os.environ.get("USERNAME", "Developer")))

    p("")
    p("  SUMMARY", BOLD)
    p("  -----------------------------------------")
    p(f"  Name:        {info['project_name']}")
    p(f"  Description: {info['project_description']}")
    p(f"  Tech Stack:  {info['tech_stack']}")
    p(f"  GitHub:      {info['github_repo'] or '(not set)'}")
    p(f"  Developer:   {info['developer_name']}")
    p("")

    confirm = ask("Proceed? (y/n)", "y")
    if confirm.lower() != "y":
        p("  Cancelled.", YELLOW)
        sys.exit(0)

    return info


def replace_placeholders(content, info):
    """Replace all {{PLACEHOLDER}} values in content."""
    replacements = {
        "{{PROJECT_NAME}}": info["project_name"],
        "{{PROJECT_DESCRIPTION}}": info["project_description"],
        "{{TECH_STACK}}": info["tech_stack"],
        "{{GITHUB_REPO}}": info.get("github_repo", ""),
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


def copy_workflow_scripts(target_dir, info):
    """Copy and templatize workflow scripts."""
    workflows_target = target_dir / "workflows"
    workflows_target.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    for subdir in WORKFLOW_SUBDIRS:
        (workflows_target / subdir).mkdir(parents=True, exist_ok=True)

    copied = 0
    for script in WORKFLOW_SCRIPTS:
        src = WORKFLOWS_SRC / script
        dst = workflows_target / script

        if dst.exists():
            p(f"  [SKIP] Already exists: workflows/{script}", YELLOW)
            continue

        content = read_file_or_fetch(src, f"workflows/{script}")
        if content is None:
            p(f"  [WARN] Could not get: workflows/{script}", YELLOW)
            continue

        content = replace_placeholders(content, info)
        dst.write_text(content, encoding="utf-8")
        copied += 1

    p(f"  [OK] Copied {copied} workflow script(s)", GREEN)
    return copied


def generate_claude_md(target_dir, info):
    """Generate CLAUDE.md from template."""
    template_path = TEMPLATES_DIR / "CLAUDE.md.template"
    output_path = target_dir / "CLAUDE.md"

    if output_path.exists():
        p("  [SKIP] CLAUDE.md already exists", YELLOW)
        return False

    content = read_file_or_fetch(template_path, "templates/CLAUDE.md.template")
    if content is None:
        p("  [WARN] Could not get CLAUDE.md.template", YELLOW)
        return False

    content = replace_placeholders(content, info)
    output_path.write_text(content, encoding="utf-8")
    p("  [OK] Generated CLAUDE.md", GREEN)
    return True


def generate_knowledge(target_dir, info):
    """Generate knowledge file from template."""
    template_path = TEMPLATES_DIR / "knowledge.md.template"
    knowledge_dir = target_dir / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    output_path = knowledge_dir / f"{info['project_name']}-project.md"

    if output_path.exists():
        p(f"  [SKIP] Knowledge file already exists", YELLOW)
        return False

    content = read_file_or_fetch(template_path, "templates/knowledge.md.template")
    if content is None:
        p("  [WARN] Could not get knowledge.md.template", YELLOW)
        return False

    content = replace_placeholders(content, info)
    output_path.write_text(content, encoding="utf-8")
    p(f"  [OK] Generated knowledge/{info['project_name']}-project.md", GREEN)
    return True


def create_gitignore(target_dir):
    """Create .gitignore if it doesn't exist."""
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


def create_env_example(target_dir):
    """Create .env.example if it doesn't exist."""
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


def init_git(target_dir, info):
    """Initialize git and optionally create GitHub repo."""
    git_dir = target_dir / ".git"

    if git_dir.exists():
        p("  [SKIP] Git already initialized", YELLOW)
    else:
        subprocess.run(["git", "init"], cwd=str(target_dir), capture_output=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=str(target_dir), capture_output=True)
        p("  [OK] Git initialized", GREEN)

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=str(target_dir), capture_output=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(target_dir), capture_output=True)
    if result.returncode != 0:
        subprocess.run(
            ["git", "commit", "-m", f"Initial commit: {info['project_name']} with Dev Autopilot"],
            cwd=str(target_dir), capture_output=True
        )
        p("  [OK] Initial commit created", GREEN)

    # GitHub repo
    if info.get("github_repo"):
        create_repo = ask("Create GitHub repo and push? (y/n)", "n")
        if create_repo.lower() == "y":
            # Check if gh CLI is available
            gh_check = subprocess.run(["gh", "--version"], capture_output=True)
            if gh_check.returncode == 0:
                repo_name = info["github_repo"].split("/")[-1] if "/" in info["github_repo"] else info["github_repo"]
                subprocess.run(
                    ["gh", "repo", "create", repo_name, "--private", "--source=.", "--remote=origin", "--push"],
                    cwd=str(target_dir)
                )
                p("  [OK] GitHub repo created and pushed", GREEN)
            else:
                p("  [WARN] gh CLI not found. Install it: npm install -g gh", YELLOW)
                p(f"  Manual steps: create repo at github.com, then:", YELLOW)
                p(f"    git remote add origin https://github.com/{info['github_repo']}.git", YELLOW)
                p(f"    git push -u origin main", YELLOW)


# =============================================
# MODE 1: Fresh Project
# =============================================

def mode_fresh(info):
    """Set up a fresh project from scratch."""
    p("")
    p("  MODE 1: FRESH PROJECT", BOLD)
    p("  =========================================", CYAN)
    p("")

    # Determine target directory
    target_dir = Path.cwd() / info["project_name"]

    use_cwd = ask(f"Create project in ./{info['project_name']}? (y) or use current dir? (c)", "y")
    if use_cwd.lower() == "c":
        target_dir = Path.cwd()
    else:
        if target_dir.exists():
            p(f"  [WARN] Directory {target_dir} already exists", YELLOW)
            overwrite = ask("Continue anyway? (y/n)", "n")
            if overwrite.lower() != "y":
                sys.exit(0)
        target_dir.mkdir(parents=True, exist_ok=True)

    p(f"\n  Target: {target_dir}\n")

    # Step 1: Create .gitignore
    p("  STEP 1: Creating .gitignore", BOLD)
    create_gitignore(target_dir)

    # Step 2: Generate CLAUDE.md
    p("  STEP 2: Generating CLAUDE.md", BOLD)
    generate_claude_md(target_dir, info)

    # Step 3: Generate knowledge file
    p("  STEP 3: Generating knowledge file", BOLD)
    generate_knowledge(target_dir, info)

    # Step 4: Copy workflow scripts
    p("  STEP 4: Copying workflow scripts", BOLD)
    copy_workflow_scripts(target_dir, info)

    # Step 5: Create .env.example
    p("  STEP 5: Creating .env.example", BOLD)
    create_env_example(target_dir)

    # Step 6: Initialize git
    p("  STEP 6: Initializing git", BOLD)
    init_git(target_dir, info)

    # Summary
    p("")
    p("  =========================================", GREEN)
    p("  SETUP COMPLETE!", GREEN)
    p("  =========================================", GREEN)
    p("")
    p(f"  Your project is ready at: {target_dir}")
    p("")
    p("  Next steps:")
    p(f"    cd {info['project_name']}")
    p("    # Start coding, then tell Claude Code:")
    p('    # "Client wants feature X" to log requirements')
    p('    # "run standup" for daily standup')
    p('    # "work on REQ-001" to start a work session')
    p("")


# =============================================
# MODE 2: Retrofit Existing Project
# =============================================

def mode_retrofit(info):
    """Add Dev Autopilot to an existing project."""
    p("")
    p("  MODE 2: RETROFIT EXISTING PROJECT", BOLD)
    p("  =========================================", CYAN)
    p("")

    target_dir = Path.cwd()

    # Check if we're in a git repo
    git_dir = target_dir / ".git"
    if not git_dir.exists():
        p("  [WARN] Not a git repository. Initialize git first? (y/n)", YELLOW)
        init = ask("Initialize git?", "y")
        if init.lower() == "y":
            subprocess.run(["git", "init"], cwd=str(target_dir), capture_output=True)
            subprocess.run(["git", "branch", "-M", "main"], cwd=str(target_dir), capture_output=True)
            p("  [OK] Git initialized", GREEN)
        else:
            p("  Cannot proceed without git.", RED)
            sys.exit(1)

    p(f"  Target: {target_dir}\n")

    # Step 1: Generate CLAUDE.md
    p("  STEP 1: Generating CLAUDE.md", BOLD)
    generate_claude_md(target_dir, info)

    # Step 2: Generate knowledge file
    p("  STEP 2: Generating knowledge file", BOLD)
    generate_knowledge(target_dir, info)

    # Step 3: Copy workflow scripts
    p("  STEP 3: Copying workflow scripts", BOLD)
    copy_workflow_scripts(target_dir, info)

    # Step 4: Update .gitignore
    p("  STEP 4: Updating .gitignore", BOLD)
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

    # Step 5: Create .env.example
    p("  STEP 5: Creating .env.example", BOLD)
    create_env_example(target_dir)

    # Step 6: Commit
    p("  STEP 6: Committing changes", BOLD)
    subprocess.run(["git", "add", "."], cwd=str(target_dir), capture_output=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(target_dir), capture_output=True)
    if result.returncode != 0:
        subprocess.run(
            ["git", "commit", "-m", "Add Dev Autopilot workflow system"],
            cwd=str(target_dir), capture_output=True
        )
        p("  [OK] Changes committed", GREEN)
    else:
        p("  [SKIP] No changes to commit", YELLOW)

    # Summary
    p("")
    p("  =========================================", GREEN)
    p("  RETROFIT COMPLETE!", GREEN)
    p("  =========================================", GREEN)
    p("")
    p("  Dev Autopilot has been added to your project.")
    p("")
    p("  Next steps:")
    p('    # Tell Claude Code: "Client wants feature X" to log requirements')
    p('    # "run standup" for daily standup')
    p('    # "work on REQ-001" to start a work session')
    p("")


# =============================================
# MAIN
# =============================================

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
