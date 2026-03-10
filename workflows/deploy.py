#!/usr/bin/env python3
"""
Guided deployment script for {{PROJECT_NAME}} app to AWS EC2 via Git.
Step-based state machine for Claude Code chat integration.

Usage:
    python workflows/deploy.py --ec2-host 3.10.45.200 --key-file /path/to/key.pem
    python workflows/deploy.py --repo-name {{PROJECT_NAME}} --ec2-host 3.10.45.200 --key-file /path/to/key.pem
    python workflows/deploy.py --ec2-host 3.10.45.200 --key-file /path/to/key.pem --update
    python workflows/deploy.py --step <step_name> --response "<answer>"
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
SESSION_DIR = SCRIPT_DIR / ".session"
SESSION_FILE = SESSION_DIR / "deploy_session.json"
LOG_FILE = SCRIPT_DIR / f"deploy_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

# Customize these for your project
REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    # Add your project-specific env vars here
]
SENSITIVE_FILES = [".env", "*.pem", "*.key"]
RUNTIME_DIRS = []  # Add project-specific runtime directories, e.g. ["uploads", "outputs"]


# --- Helpers ---

def write_log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")


def load_session():
    if SESSION_FILE.exists():
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_session(state):
    SESSION_DIR.mkdir(exist_ok=True)
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def clear_session():
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def run_cmd(cmd, cwd=None, timeout=60):
    """Run a local command and return (output, returncode)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            cwd=cwd or str(PROJECT_DIR), timeout=timeout
        )
        return (result.stdout + result.stderr).strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "Command timed out", 1
    except Exception as e:
        return str(e), 1


def run_ssh(state, command, silent=False):
    """Run a command on EC2 via SSH."""
    key_file = state.get("key_file", "")
    ec2_user = state.get("ec2_user", "ubuntu")
    ec2_host = state.get("ec2_host", "")
    ssh_cmd = f'ssh -i "{key_file}" -o StrictHostKeyChecking=no {ec2_user}@{ec2_host} "{command}"'
    write_log(f"SSH: {command}")
    output, rc = run_cmd(ssh_cmd, timeout=120)
    if not silent:
        print(f"  > {command}")
        if output:
            for line in output.split("\n"):
                print(f"    {line}")
    return output, rc


def check_pass(item, passed, detail=""):
    mark = "[PASS]" if passed else "[FAIL]"
    print(f"  {mark} {item}")
    if detail:
        print(f"         {detail}")


def write_step(num, title):
    print(f"\n========================================")
    print(f"  STEP {num}: {title}")
    print(f"========================================")


def prompt(step_name, message):
    print(f"\n[DEPLOY:{step_name}]")
    print(message)


# --- Step functions ---

def step_init(state):
    """Show banner, detect existing remote, decide first step."""
    deploy_mode = "UPDATE (git pull)" if state.get("update") else "FRESH DEPLOY (git clone)"

    print()
    print("=============================================")
    print("  {{PROJECT_NAME}} -- EC2 Deployment (Git)")
    print("=============================================")
    print(f"  Mode:    {deploy_mode}")
    print(f"  Project: {PROJECT_DIR}")
    write_log(f"Deployment started - Mode: {deploy_mode}")

    if not state.get("skip_repo_create") and not state.get("update"):
        output, rc = run_cmd("git remote get-url origin")
        if rc == 0 and output.strip():
            check_pass("Git remote already configured", True, output.strip())
            print("  [INFO] Repository already exists. Skipping creation.")
            if not state.get("git_repo"):
                state["git_repo"] = output.strip()
            state["current_step"] = "step1"
            save_session(state)
            return step1(state)
        else:
            if state.get("repo_name"):
                state["current_step"] = "step0_create_confirm"
                save_session(state)
                return step0_detect(state)
            write_step(0, "GITHUB REPOSITORY SETUP")
            state["current_step"] = "step0_reponame"
            save_session(state)
            prompt("step0_reponame", "Enter GitHub repository name (e.g., {{PROJECT_NAME}}):")
            return
    else:
        if state.get("update"):
            print("  [INFO] Update mode -- skipping repo creation (Step 0)")
        else:
            print("  [INFO] SkipRepoCreate -- skipping repo creation (Step 0)")
        state["current_step"] = "step1"
        save_session(state)
        return step1(state)


def step0_detect(state):
    """Detect gh CLI availability and prompt for creation method."""
    repo_name = state["repo_name"]
    write_step(0, "GITHUB REPOSITORY SETUP")
    print(f"\n  Repository name: {repo_name} (PRIVATE)")

    output, rc = run_cmd("gh --version")
    gh_available = rc == 0
    gh_authenticated = False

    if gh_available:
        check_pass("GitHub CLI (gh) installed", True, output.split("\n")[0])
        auth_out, _ = run_cmd("gh auth status")
        if "Logged in" in auth_out:
            gh_authenticated = True
            check_pass("GitHub CLI authenticated", True)
        else:
            check_pass("GitHub CLI authenticated", False)
            print("  [INFO] Run 'gh auth login' to authenticate")
    else:
        check_pass("GitHub CLI (gh) installed", False)
        print("\n  To install gh CLI:")
        print("    winget install --id GitHub.cli")

    state["gh_available"] = gh_available
    state["gh_authenticated"] = gh_authenticated

    if gh_authenticated:
        state["create_method"] = "gh"
        save_session(state)
        prompt("step0_create_confirm", f"Create private GitHub repo '{repo_name}' using gh CLI? (y/n/skip):")
    elif state.get("github_token"):
        state["create_method"] = "api"
        save_session(state)
        prompt("step0_create_confirm", f"Create private GitHub repo '{repo_name}' using GitHub API? (y/n/skip):")
    else:
        state["create_method"] = "api"
        save_session(state)
        print("\n  gh CLI not available/authenticated. Using GitHub REST API instead.")
        print("  A Personal Access Token (PAT) is needed.")
        print("  Create one at: https://github.com/settings/tokens")
        print("  Required scopes: repo (Full control of private repositories)")
        prompt("step0_token", "Enter GitHub Personal Access Token:")


def step0_create(state):
    """Actually create the GitHub repo."""
    repo_name = state["repo_name"]
    git_branch = state.get("git_branch", "main")
    method = state.get("create_method", "gh")
    has_git = (PROJECT_DIR / ".git").exists()
    repo_url = None
    clone_url = None

    if method == "gh":
        if not has_git:
            print("  [INFO] Initializing git repository...")
            run_cmd("git init")
            run_cmd(f"git branch -M {git_branch}")
            check_pass("Git initialized", True)

        print("  Creating private repo via gh CLI...")
        output, rc = run_cmd(f"gh repo create {repo_name} --private --source=. --remote=origin --push")
        if rc == 0:
            url_out, _ = run_cmd("gh repo view --json url -q .url")
            repo_url = url_out.strip()
            clone_url = f"{repo_url}.git" if repo_url else None
            check_pass("GitHub repo created", True, repo_url)
            write_log(f"Repo created via gh CLI: {repo_url}")
        else:
            print(f"  [ERROR] gh repo create failed: {output}")
            if "already exists" in output:
                print("  [INFO] Repo may already exist. Trying to add as remote...")
                user_out, _ = run_cmd("gh api user -q .login")
                repo_url = f"https://github.com/{user_out.strip()}/{repo_name}"
                clone_url = f"{repo_url}.git"
                run_cmd(f"git remote add origin {clone_url}")
            else:
                return
    else:
        token = state.get("github_token", "")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        print("  [INFO] Verifying token...")
        try:
            req = Request("https://api.github.com/user", headers=headers)
            with urlopen(req) as resp:
                user_data = json.loads(resp.read())
                gh_username = user_data["login"]
                check_pass("Authenticated as", True, gh_username)
        except HTTPError as e:
            print(f"  [ERROR] Invalid token or API error: {e}")
            clear_session()
            return

        body = json.dumps({"name": repo_name, "private": True, "auto_init": False}).encode()
        try:
            req = Request(
                "https://api.github.com/user/repos", data=body,
                headers={**headers, "Content-Type": "application/json"}, method="POST",
            )
            with urlopen(req) as resp:
                repo_data = json.loads(resp.read())
                repo_url = repo_data["html_url"]
                clone_url = repo_data["clone_url"]
                check_pass("GitHub repo created", True, repo_url)
                write_log(f"Repo created via API: {repo_url}")
        except HTTPError as e:
            error_body = e.read().decode()
            if "already exists" in error_body:
                print(f"  [INFO] Repo '{repo_name}' already exists.")
                repo_url = f"https://github.com/{gh_username}/{repo_name}"
                clone_url = f"https://github.com/{gh_username}/{repo_name}.git"
                check_pass("Using existing repo", True, repo_url)
            else:
                print(f"  [ERROR] Failed to create repo: {e}")
                clear_session()
                return

        if not has_git:
            print("  [INFO] Initializing git repository...")
            run_cmd("git init")
            run_cmd(f"git branch -M {git_branch}")
            check_pass("Git initialized", True)

        existing, rc = run_cmd("git remote get-url origin")
        if rc == 0:
            print("  [INFO] Remote 'origin' already exists. Updating URL...")
            run_cmd(f"git remote set-url origin {clone_url}")
        else:
            run_cmd(f"git remote add origin {clone_url}")
        check_pass("Remote 'origin' set", True, clone_url)

    # Create .gitignore if missing
    gitignore_path = PROJECT_DIR / ".gitignore"
    if not gitignore_path.exists():
        print("  [INFO] Creating .gitignore...")
        gitignore_content = (
            "# Environment and secrets\n.env\n*.pem\n*.key\n\n"
            "# Python\n__pycache__/\n*.py[cod]\n*$py.class\n*.so\n"
            "venv/\n.venv/\n*.egg-info/\ndist/\nbuild/\n\n"
            "# IDE\n.idea/\n.vscode/\n*.swp\n*.swo\n\n"
            "# OS\n.DS_Store\nThumbs.db\n\n"
            "# Logs\n*.log\nworkflows/deploy_*.log\n"
        )
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(gitignore_content)
        check_pass(".gitignore created", True)

    state["repo_url"] = repo_url or ""
    state["clone_url"] = clone_url or ""
    if not state.get("git_repo") and clone_url:
        state["git_repo"] = clone_url
    elif not state.get("git_repo") and repo_url:
        state["git_repo"] = f"{repo_url}.git"

    save_session(state)

    run_cmd("git add -A")

    staged_out, _ = run_cmd("git diff --cached --name-only")
    if staged_out and ".env" in staged_out.split("\n"):
        print("  [WARN] .env was staged! Removing from staging...")
        run_cmd("git rm --cached .env")

    staged_out, _ = run_cmd("git diff --cached --name-only")
    files = [f for f in staged_out.strip().split("\n") if f] if staged_out.strip() else []
    print(f"\n  Files to commit ({len(files)}):")
    for f in files[:20]:
        print(f"    {f}")
    if len(files) > 20:
        print(f"    ... and {len(files) - 20} more")

    state["staged_count"] = len(files)
    save_session(state)
    prompt("step0_push_confirm", f"Commit and push these {len(files)} files? (y/n/skip):")


def step0_push(state):
    """Commit and push to GitHub."""
    git_branch = state.get("git_branch", "main")

    run_cmd(f'git commit -m "Initial commit - {{{{PROJECT_NAME}}}}"')
    check_pass("Initial commit created", True)

    print(f"  [INFO] Pushing to origin/{git_branch}...")
    output, rc = run_cmd(f"git push -u origin {git_branch}", timeout=120)
    if rc == 0:
        check_pass("Pushed to GitHub", True)
        write_log(f"Initial push to {state.get('repo_url', '')}")
    else:
        print(f"  [ERROR] Push failed: {output}")
        print("  [INFO] You may need to configure credentials:")
        print("    git config credential.helper store")

    repo_url = state.get("repo_url", "")
    git_branch_val = state.get("git_branch", "main")
    if repo_url:
        knowledge_file = PROJECT_DIR / "knowledge" / "{{PROJECT_NAME}}-project.md"
        if knowledge_file.exists():
            content = knowledge_file.read_text(encoding="utf-8")
            if "GitHub Repository" not in content:
                content += f"\n\n## GitHub Repository\n- **URL**: {repo_url}\n- **Visibility**: Private\n- **Branch**: {git_branch_val}"
                knowledge_file.write_text(content, encoding="utf-8")
                check_pass("Repo URL saved to knowledge file", True)

    state["current_step"] = "step1"
    save_session(state)
    return step1(state)


def step1(state):
    """Pre-deployment checklist."""
    write_step(1, "PRE-DEPLOYMENT CHECKLIST")
    all_pass = True

    git_dir = PROJECT_DIR / ".git"
    git_init = git_dir.exists()
    check_pass("Git initialized locally", git_init)
    if not git_init:
        all_pass = False

    has_origin = False
    if git_init:
        remotes, _ = run_cmd("git remote -v")
        has_origin = "origin" in remotes
        check_pass("Git remote 'origin' configured", has_origin, remotes.split("\n")[0] if remotes else "")
        if not has_origin:
            print("  [INFO] Add a remote: git remote add origin <repo-url>")
            all_pass = False

    gitignore_path = PROJECT_DIR / ".gitignore"
    gitignore_exists = gitignore_path.exists()
    check_pass(".gitignore exists", gitignore_exists)
    if gitignore_exists:
        gi_content = gitignore_path.read_text(encoding="utf-8")
        for pattern in SENSITIVE_FILES:
            found = pattern in gi_content
            check_pass(f"  .gitignore covers {pattern}", found)
            if not found:
                print(f"  [WARN] {pattern} is NOT in .gitignore -- secrets may be exposed!")
                all_pass = False
    else:
        print("  [ERROR] No .gitignore -- sensitive files could be committed!")
        all_pass = False

    git_branch = state.get("git_branch", "main")
    if git_init:
        status_out, _ = run_cmd("git status --porcelain")
        is_clean = not status_out.strip()
        check_pass("No uncommitted changes", is_clean)
        if not is_clean:
            print("  [INFO] Uncommitted changes detected. Commit and push before deploying.")

    if git_init and has_origin:
        ahead, _ = run_cmd(f"git rev-list --count origin/{git_branch}..HEAD")
        is_pushed = ahead.strip() == "0"
        check_pass(f"All commits pushed to origin/{git_branch}", is_pushed)
        if not is_pushed:
            print(f"  [INFO] {ahead.strip()} commit(s) not pushed.")

    # Add your project's key files to check here
    req_exists = (PROJECT_DIR / "requirements.txt").exists()
    if req_exists:
        check_pass("requirements.txt exists", True)

    env_exists = (PROJECT_DIR / ".env").exists()
    check_pass(".env file exists locally (reference)", env_exists)
    if env_exists:
        print("  [INFO] .env is gitignored -- you'll create it manually on the server")

    if git_init:
        env_tracked, _ = run_cmd("git ls-files .env")
        env_safe = not env_tracked.strip()
        check_pass(".env is NOT tracked by git", env_safe)
        if not env_safe:
            print("  [ERROR] .env IS tracked by git! Remove it: git rm --cached .env")
            all_pass = False

    if not all_pass:
        print("\n  [WARN] Some checks failed. Review above before continuing.")

    state["current_step"] = "step1_confirm"
    save_session(state)
    prompt("step1_confirm", "Pre-deployment checks reviewed. Continue to EC2 setup? (y/n/skip):")


def step2(state):
    """EC2 setup guidance and connection test."""
    write_step(2, "EC2 INSTANCE SETUP GUIDE")

    print("""
  If you haven't created an EC2 instance yet, follow these steps in AWS Console:

  1. INSTANCE TYPE
     - Recommended: t3.small (2 vCPU, 2GB RAM) or t3.micro for testing

  2. AMI (Operating System)
     - Recommended: Ubuntu Server 22.04 LTS (HVM), SSD Volume Type
     - Amazon Linux 2023 also works (change ec2_user to 'ec2-user')

  3. SECURITY GROUPS (Inbound Rules)
     - SSH (port 22)   : Your IP only
     - HTTP (port 80)  : 0.0.0.0/0 (public web access)
     - HTTPS (port 443): 0.0.0.0/0 (if adding SSL later)
     - Custom (5000)   : Your IP only (for testing, remove later)

  4. KEY PAIR
     - Create or select a .pem key pair
     - Download and save it securely

  5. STORAGE
     - Recommended: 20 GB gp3
""")

    ec2_host = state.get("ec2_host", "")
    key_file = state.get("key_file", "")

    if not ec2_host:
        state["current_step"] = "step2_ec2host"
        save_session(state)
        prompt("step2_ec2host", "Enter EC2 public IP or hostname:")
        return

    if not key_file:
        state["current_step"] = "step2_keyfile"
        save_session(state)
        prompt("step2_keyfile", "Enter path to .pem key file:")
        return

    return step2_test_ssh(state)


def step2_test_ssh(state):
    """Test SSH connection and confirm."""
    ec2_host = state["ec2_host"]
    ec2_user = state.get("ec2_user", "ubuntu")
    key_file = state["key_file"]

    print(f"\n  EC2 Host:  {ec2_host}")
    print(f"  SSH User:  {ec2_user}")
    print(f"  Key File:  {key_file}")

    print("  [INFO] Testing SSH connection...")
    output, rc = run_ssh(state, "echo 'SSH connection successful'", silent=True)
    ssh_ok = "successful" in output
    check_pass(f"SSH connection to {ec2_host}", ssh_ok, output)

    if not ssh_ok:
        print("\n  [ERROR] Cannot connect via SSH. Check:")
        print("    - EC2 instance is running")
        print("    - Security group allows SSH from your IP")
        print("    - Key file is correct and has proper permissions")
        print(f"    - Username is correct ({ec2_user})")
        clear_session()
        return

    state["current_step"] = "step2_confirm"
    save_session(state)
    prompt("step2_confirm", "EC2 instance is ready. Proceed to install dependencies? (y/n/skip):")


def step3(state):
    """Install dependencies on EC2."""
    write_step(3, "INSTALL DEPENDENCIES ON EC2")
    print("  [INFO] This will install git, Python 3, pip, venv, and nginx on the EC2 instance.")

    cmds = [
        "sudo apt-get update -y",
        "sudo apt-get install -y git python3 python3-pip python3-venv nginx",
        "git --version", "python3 --version", "pip3 --version", "nginx -v",
    ]
    print("\n  Commands to run:")
    for c in cmds:
        print(f"    {c}")

    state["current_step"] = "step3_confirm"
    save_session(state)
    prompt("step3_confirm", "Install git, Python, pip, venv, and nginx on EC2? (y/n/skip):")


def step3_execute(state):
    """Run install commands."""
    cmds = [
        "sudo apt-get update -y",
        "sudo apt-get install -y git python3 python3-pip python3-venv nginx",
        "git --version", "python3 --version", "pip3 --version", "nginx -v",
    ]
    for cmd in cmds:
        run_ssh(state, cmd)
    check_pass("Dependencies installed", True)

    state["current_step"] = "step4"
    save_session(state)
    return step4(state)


def step4(state):
    """Deploy code via git (clone or pull)."""
    write_step(4, "DEPLOY CODE VIA GIT")

    app_name = state.get("app_name", "{{PROJECT_NAME}}").lower().replace(" ", "-")
    ec2_user = state.get("ec2_user", "ubuntu")
    remote_dir = f"/home/{ec2_user}/{app_name}"
    state["remote_dir"] = remote_dir
    git_repo = state.get("git_repo", "")
    git_branch = state.get("git_branch", "main")

    if not git_repo:
        detected, rc = run_cmd("git remote get-url origin")
        if rc == 0 and detected.strip():
            print(f"  [INFO] Detected repo from local git: {detected.strip()}")
            state["detected_repo"] = detected.strip()
            save_session(state)
            prompt("step4_use_detected", f"Use this repo ({detected.strip()})? (y/n):")
            return
        state["current_step"] = "step4_repo_url"
        save_session(state)
        prompt("step4_repo_url", "Enter GitHub repo URL (HTTPS or SSH):")
        return

    return step4_show_clone(state)


def step4_show_clone(state):
    """Show clone/pull info and confirm."""
    git_repo = state["git_repo"]
    git_branch = state.get("git_branch", "main")
    remote_dir = state["remote_dir"]
    is_update = state.get("update", False)

    print(f"\n  Repository:  {git_repo}")
    print(f"  Branch:      {git_branch}")
    print(f"  Remote dir:  {remote_dir}")

    if is_update:
        print("\n  MODE: Update -- pulling latest changes")
        state["current_step"] = "step4_confirm"
        save_session(state)
        prompt("step4_confirm", f"Pull latest code from {git_branch} on EC2? (y/n/skip):")
    else:
        print("\n  MODE: Fresh deploy -- cloning repository")
        print("  [INFO] For private repos, set up authentication on EC2:")
        print("    Option A: GitHub PAT in the HTTPS URL")
        print("    Option B: Deploy key (SSH) added to the repo settings")
        print("    Option C: SSH agent forwarding")
        state["current_step"] = "step4_confirm"
        save_session(state)
        prompt("step4_confirm", f"Clone repo to EC2:{remote_dir}? (y/n/skip):")


def step4_execute(state):
    """Clone or pull on EC2."""
    git_repo = state["git_repo"]
    git_branch = state.get("git_branch", "main")
    remote_dir = state["remote_dir"]
    is_update = state.get("update", False)

    if is_update:
        repo_check, _ = run_ssh(state, f"test -d {remote_dir}/.git && echo 'exists' || echo 'missing'", silent=True)
        if "missing" in repo_check:
            print(f"  [ERROR] No git repo found at {remote_dir}. Run without --update for fresh deploy.")
            clear_session()
            return

        run_ssh(state, f"cd {remote_dir} && git fetch origin")
        run_ssh(state, f"cd {remote_dir} && git checkout {git_branch}")
        run_ssh(state, f"cd {remote_dir} && git pull origin {git_branch}")

        git_log, _ = run_ssh(state, f"cd {remote_dir} && git log --oneline -5", silent=True)
        print("\n  Latest commits on server:")
        for line in git_log.split("\n"):
            print(f"    {line}")

        check_pass("Code updated via git pull", True)
        write_log(f"Git pull completed on {git_branch}")
    else:
        dir_check, _ = run_ssh(state, f"test -d {remote_dir} && echo 'exists' || echo 'missing'", silent=True)
        if "exists" in dir_check:
            print(f"  [WARN] {remote_dir} already exists on EC2. Removing and cloning fresh...")
            run_ssh(state, f"rm -rf {remote_dir}")

        run_ssh(state, f"git clone -b {git_branch} {git_repo} {remote_dir}")

        clone_check, _ = run_ssh(state, f"test -d {remote_dir} && echo 'ok' || echo 'fail'", silent=True)
        check_pass("Repository cloned successfully", "ok" in clone_check)

        if "ok" not in clone_check:
            print("  [ERROR] Clone may have failed. Common causes:")
            print("    - Private repo without authentication on EC2")
            print("    - Wrong repo URL or branch name")
            print("  [INFO] SSH into EC2 and run 'git clone' manually to debug")
            clear_session()
            return

        write_log(f"Git clone completed: {git_repo} -> {remote_dir}")

    if RUNTIME_DIRS:
        print("  [INFO] Creating runtime directories on EC2...")
        dir_paths = " ".join(f"{remote_dir}/{d}" for d in RUNTIME_DIRS)
        run_ssh(state, f"mkdir -p {dir_paths}")
        check_pass("Runtime directories created", True, f"({', '.join(RUNTIME_DIRS)})")

    state["current_step"] = "step5"
    save_session(state)
    return step5(state)


def step5(state):
    """Python venv and packages."""
    write_step(5, "PYTHON VIRTUAL ENVIRONMENT & PACKAGES")
    remote_dir = state["remote_dir"]
    is_update = state.get("update", False)

    print("  [INFO] Creating venv and installing requirements on EC2...")

    if is_update:
        print("  [INFO] Update mode: reinstalling requirements in existing venv...")
        cmds = [f"cd {remote_dir} && source venv/bin/activate && pip install -r requirements.txt"]
    else:
        cmds = [
            f"cd {remote_dir} && python3 -m venv venv",
            f"cd {remote_dir} && source venv/bin/activate && pip install --upgrade pip",
            f"cd {remote_dir} && source venv/bin/activate && pip install -r requirements.txt",
            f"cd {remote_dir} && source venv/bin/activate && pip install gunicorn",
        ]

    print("\n  Commands:")
    for c in cmds:
        print(f"    {c}")

    state["venv_cmds"] = cmds
    state["current_step"] = "step5_confirm"
    save_session(state)
    prompt("step5_confirm", "Create venv and install packages on EC2? (y/n/skip):")


def step5_execute(state):
    """Run venv/pip commands."""
    remote_dir = state["remote_dir"]
    for cmd in state.get("venv_cmds", []):
        run_ssh(state, cmd)

    gunicorn_check, _ = run_ssh(state, f"cd {remote_dir} && source venv/bin/activate && gunicorn --version", silent=True)
    check_pass("gunicorn installed", "gunicorn" in gunicorn_check, gunicorn_check)

    state["current_step"] = "step6"
    save_session(state)
    return step6(state)


def step6(state):
    """Configure gunicorn systemd service."""
    write_step(6, "GUNICORN SYSTEMD SERVICE")
    remote_dir = state["remote_dir"]
    ec2_user = state.get("ec2_user", "ubuntu")
    app_name = state.get("app_name", "{{PROJECT_NAME}}").lower().replace(" ", "-")

    service_content = f"""[Unit]
Description={{{{PROJECT_NAME}}}} (Gunicorn)
After=network.target

[Service]
User={ec2_user}
Group=www-data
WorkingDirectory={remote_dir}
Environment="PATH={remote_dir}/venv/bin"
EnvironmentFile={remote_dir}/.env
ExecStart={remote_dir}/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target"""

    state["service_content"] = service_content
    state["service_name"] = app_name

    print(f"  Service name: {app_name}")
    print(f"  Working dir:  {remote_dir}")
    print(f"  Bind:         127.0.0.1:5000")
    print(f"  Workers:      3")
    print()
    print("  Service file content:")
    for line in service_content.split("\n"):
        print(f"    {line}")

    state["current_step"] = "step6_confirm"
    save_session(state)
    prompt("step6_confirm", "Create systemd service on EC2? (y/n/skip):")


def step6_execute(state):
    """Write and enable systemd service."""
    service_name = state["service_name"]
    service_content = state["service_content"]

    escaped = service_content.replace('"', '\\"').replace('\n', '\\n')
    run_ssh(state, f'echo -e "{escaped}" | sudo tee /etc/systemd/system/{service_name}.service')
    run_ssh(state, "sudo systemctl daemon-reload")
    run_ssh(state, f"sudo systemctl enable {service_name}")
    run_ssh(state, f"sudo systemctl restart {service_name}")

    import time
    time.sleep(2)
    status_out, _ = run_ssh(state, f"sudo systemctl is-active {service_name}", silent=True)
    is_active = "active" in status_out and "inactive" not in status_out
    check_pass(f"Service {service_name} running", is_active, status_out.strip())

    state["current_step"] = "step7"
    save_session(state)
    prompt("step7_confirm", "Configure Nginx reverse proxy? (y/n/skip):")


def step7(state):
    """Configure Nginx."""
    write_step(7, "NGINX REVERSE PROXY")
    ec2_host = state.get("ec2_host", "your-server-ip")
    app_name = state.get("app_name", "{{PROJECT_NAME}}").lower().replace(" ", "-")

    nginx_config = f"""server {{
    listen 80;
    server_name {ec2_host};

    location / {{
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 50M;
    }}
}}"""

    state["nginx_config"] = nginx_config

    print("  Nginx config:")
    for line in nginx_config.split("\n"):
        print(f"    {line}")

    state["current_step"] = "step7_confirm"
    save_session(state)
    prompt("step7_confirm", "Write Nginx config and restart? (y/n/skip):")


def step7_execute(state):
    """Write Nginx config and restart."""
    app_name = state.get("app_name", "{{PROJECT_NAME}}").lower().replace(" ", "-")
    nginx_config = state["nginx_config"]

    escaped = nginx_config.replace('"', '\\"').replace('\n', '\\n')
    run_ssh(state, f'echo -e "{escaped}" | sudo tee /etc/nginx/sites-available/{app_name}')
    run_ssh(state, f"sudo ln -sf /etc/nginx/sites-available/{app_name} /etc/nginx/sites-enabled/{app_name}")
    run_ssh(state, "sudo rm -f /etc/nginx/sites-enabled/default")
    run_ssh(state, "sudo nginx -t")
    run_ssh(state, "sudo systemctl restart nginx")

    check_pass("Nginx configured and restarted", True)
    ec2_host = state.get("ec2_host", "")
    print(f"\n  Your app should now be accessible at: http://{ec2_host}")
    print("  [INFO] For HTTPS, set up a domain name and use certbot:")
    print("    sudo apt install certbot python3-certbot-nginx")
    print("    sudo certbot --nginx -d yourdomain.com")

    print("\n  DEPLOYMENT COMPLETE!")
    write_log("Deployment completed successfully")
    clear_session()


# --- State router ---

def process_step(step_name, response, state):
    """Route step responses to the right handler."""
    val = response.strip().lower()

    if step_name == "step0_reponame":
        state["repo_name"] = response.strip()
        save_session(state)
        return step0_detect(state)

    elif step_name == "step0_token":
        state["github_token"] = response.strip()
        save_session(state)
        prompt("step0_create_confirm", f"Create private GitHub repo '{state['repo_name']}' using GitHub API? (y/n/skip):")

    elif step_name == "step0_create_confirm":
        if val == "y":
            return step0_create(state)
        elif val == "skip":
            state["current_step"] = "step1"
            save_session(state)
            return step1(state)
        else:
            print("  Skipped repo creation.")
            state["current_step"] = "step1"
            save_session(state)
            return step1(state)

    elif step_name == "step0_push_confirm":
        if val == "y":
            return step0_push(state)
        elif val == "skip":
            state["current_step"] = "step1"
            save_session(state)
            return step1(state)
        else:
            print("  Skipped initial push.")
            state["current_step"] = "step1"
            save_session(state)
            return step1(state)

    elif step_name == "step1_confirm":
        if val in ("y", "skip"):
            return step2(state)
        else:
            print("  Deployment cancelled.")
            clear_session()

    elif step_name == "step2_ec2host":
        state["ec2_host"] = response.strip()
        save_session(state)
        key_file = state.get("key_file", "")
        if not key_file:
            prompt("step2_keyfile", "Enter path to .pem key file:")
        else:
            return step2_test_ssh(state)

    elif step_name == "step2_keyfile":
        state["key_file"] = response.strip()
        save_session(state)
        return step2_test_ssh(state)

    elif step_name == "step2_confirm":
        if val in ("y", "skip"):
            return step3(state)
        else:
            print("  Deployment cancelled.")
            clear_session()

    elif step_name == "step3_confirm":
        if val == "y":
            return step3_execute(state)
        elif val == "skip":
            state["current_step"] = "step4"
            save_session(state)
            return step4(state)
        else:
            print("  Deployment cancelled.")
            clear_session()

    elif step_name == "step4_use_detected":
        if val == "y":
            state["git_repo"] = state["detected_repo"]
            save_session(state)
            return step4_show_clone(state)
        else:
            prompt("step4_repo_url", "Enter GitHub repo URL (HTTPS or SSH):")

    elif step_name == "step4_repo_url":
        state["git_repo"] = response.strip()
        save_session(state)
        return step4_show_clone(state)

    elif step_name == "step4_confirm":
        if val == "y":
            return step4_execute(state)
        elif val == "skip":
            state["current_step"] = "step5"
            save_session(state)
            return step5(state)
        else:
            print("  Deployment cancelled.")
            clear_session()

    elif step_name == "step5_confirm":
        if val == "y":
            return step5_execute(state)
        elif val == "skip":
            state["current_step"] = "step6"
            save_session(state)
            return step6(state)
        else:
            print("  Deployment cancelled.")
            clear_session()

    elif step_name == "step6_confirm":
        if val == "y":
            return step6_execute(state)
        elif val == "skip":
            state["current_step"] = "step7"
            save_session(state)
            prompt("step7_confirm", "Configure Nginx reverse proxy? (y/n/skip):")
        else:
            print("  Deployment cancelled.")
            clear_session()

    elif step_name == "step7_confirm":
        if val == "y":
            return step7_execute(state)
        elif val == "skip":
            print("\n  DEPLOYMENT COMPLETE (Nginx skipped)!")
            write_log("Deployment completed (Nginx skipped)")
            clear_session()
        else:
            print("  Deployment cancelled.")
            clear_session()


def main():
    parser = argparse.ArgumentParser(description="Guided EC2 Deployment")
    parser.add_argument("--repo-name", default="")
    parser.add_argument("--ec2-host", default="")
    parser.add_argument("--key-file", default="")
    parser.add_argument("--ec2-user", default="ubuntu")
    parser.add_argument("--git-branch", default="main")
    parser.add_argument("--github-token", default="")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--skip-repo-create", action="store_true")
    parser.add_argument("--step", default="")
    parser.add_argument("--response", default="")
    args = parser.parse_args()

    SESSION_DIR.mkdir(exist_ok=True)

    if args.step:
        state = load_session()
        process_step(args.step, args.response, state)
        return

    state = load_session()
    if not state:
        state = {
            "repo_name": args.repo_name,
            "ec2_host": args.ec2_host,
            "key_file": args.key_file,
            "ec2_user": args.ec2_user,
            "git_branch": args.git_branch,
            "github_token": args.github_token,
            "update": args.update,
            "skip_repo_create": args.skip_repo_create,
        }
        save_session(state)

    step_init(state)


if __name__ == "__main__":
    main()
