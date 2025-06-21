import subprocess
from datetime import datetime, timedelta
import os
import random
import argparse
import sys
from typing import Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.letters import LETTERS

REPO_NAME = "godspeed"
REPO_OWNER = None
FILE_NAME = "artifacts/contributions.md"
LETTER_WIDTH = 5
SPACING = 1

COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_BLUE = "\033[94m"
COLOR_RESET = "\033[0m"

def red_x() -> str:
    """Colorize [x] in the output"""
    return f"{COLOR_RED}[✗]{COLOR_RESET}"

def green_check() -> str:
    """Colorize [✓] in the output"""
    return f"{COLOR_GREEN}[✓]{COLOR_RESET}"

def yellow_bang() -> str:
    """Colorize [!] in the output"""
    return f"{COLOR_YELLOW}[!]{COLOR_RESET}"

def blue_star() -> str:
    """Colorize [*] in the output"""
    return f"{COLOR_BLUE}[*]{COLOR_RESET}"

def run_safe(cmd: str, check: bool = False) -> Tuple[bool, str]:
    """Execute git and gh cli commands"""
    try:
        env = os.environ.copy()
        if 'GH_CONFIG_DIR' not in env:
            env['GH_CONFIG_DIR'] = os.path.expanduser('~/.config/gh')

        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            text=True,
            capture_output=True,
            env=env
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output += f"\n{result.stderr.strip()}"
        return result.returncode == 0, output
    except Exception as e:
        return False, str(e)

def repo_exists() -> bool:
    """Check if remote repo exists"""
    # Try GitHub CLI first
    gh_success, _ = run_safe(f"gh repo view {REPO_OWNER}/{REPO_NAME}")
    if gh_success:
        return True
    # Additional check
    git_success, _ = run_safe("git ls-remote origin 2>/dev/null")
    return git_success

def wipe_local_history() -> bool:
    """Reset local Git history while preserving files"""
    steps = [
        ("Verify Git repo", "git rev-parse --git-dir"),
        ("Create orphan branch", "git checkout --orphan new_root"),
        ("Stage files", "git add -A"),
        ("Create root commit", 'git commit -m "Initial commit"'),
        ("Delete main branch", "git branch -D main"),
        ("Rename branch", "git branch -m main")
    ]

    print(f"{blue_star()} Resetting local history...")
    for desc, cmd in steps:
        success, error = run_safe(cmd)
        if not success:
            if "not a git repository" in error.lower():
                print(f"{red_x()} Not a Git repository: {error}")
                return False
            elif "not found" not in error.lower():
                print(f"{red_x()} Failed at '{desc}': {error}")
                return False

    print(f"{green_check()} Local history reset complete")
    return True

def get_repo_owner() -> str:
    """Attempts to get GitHub repo owner"""
    # Try direct GitHub CLI methods first
    gh_attempts = [
        "gh api user --jq '.login'",
        "gh auth status 2>&1 | grep -E 'Logged in to github.com as' | awk '{print $NF}'", # Is this correct?
    ]

    for cmd in gh_attempts:
        success, output = run_safe(cmd)
        if success and output.strip():
            return output.strip()

    # Try git remote parsing
    success, remote_url = run_safe("git config --get remote.origin.url")
    if success and remote_url:
        if 'github.com' in remote_url:
            # Try both SSH and HTTPS
            if remote_url.startswith('git@'):
                return remote_url.split(':')[1].split('/')[0]
            else:
                return remote_url.split('/')[-2]

    # Try email prefix??
    success, email = run_safe("git config user.email")
    if success and email and '@' in email:
        return email.split('@')[0]

    raise RuntimeError("Could not detect GitHub owner, please set REPO_OWNER manually")

def set_repo_visibility(visibility: str) -> bool:
    """Ensure repo has correct visibility"""
    owner = get_repo_owner()
    full_repo = f"{owner}/{REPO_NAME}"

    if not repo_exists():
        print(f"{yellow_bang()} Repository doesn't exist, creating as {visibility}")
        return reset_remote_repo(visibility)

    success, output = run_safe(f"gh repo view {full_repo} --json visibility --jq '.visibility'")
    if not success:
        print(f"{red_x()} Couldn't check visibility: {output}")
        return False

    current_vis = output.strip().lower()
    if current_vis == visibility:
        print(f"{blue_star()} Repository already {visibility}")
        return True

    success, error = run_safe(
        f"gh repo edit {full_repo} --visibility {visibility} --accept-visibility-change-consequences"
    )
    if not success:
        print(f"{red_x()} Failed to change visibility: {error}")
        return False

    print(f"{green_check()} Visibility set to {visibility}")
    return True

def reset_remote_repo(visibility="private") -> bool:
    """Reset remote repo with specified visibility"""
    print(f"{blue_star()} Resetting remote repository (visibility: {visibility})...")

    if repo_exists():
        success, error = run_safe(f"gh repo delete {REPO_OWNER}/{REPO_NAME} --yes")
        if not success:
            print(f"{red_x()} Couldn't delete repository: {error}")

    success, error = run_safe(f"gh repo create {REPO_OWNER}/{REPO_NAME} --{visibility}")
    if not success:
        print(f"{red_x()} Failed to create {visibility} repository: {error}")
        return False

    print(f"{green_check()} Remote repository reset complete")
    return True

def get_first_sunday(year=None):
    """Get first Sunday of the specified year or current year if None"""
    if year is None:
        year = datetime.now().year
    start_of_year = datetime(year, 1, 1).date()
    days_to_sunday = (6 - start_of_year.weekday()) % 7
    return start_of_year + timedelta(days=days_to_sunday)

def adjust_start_date(start_date_str=None, year=None):
    """Convert string to date and adjust to nearest Sunday"""
    if start_date_str is None:
        sunday_date = get_first_sunday(year)
        print(f"\n{blue_star()} Using default start date (first Sunday of year): {sunday_date}")
        return sunday_date

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        days_to_sunday = (6 - start_date.weekday()) % 7
        sunday_date = start_date + timedelta(days=days_to_sunday)
        print(f"{blue_star()} Adjusted start date to Sunday: {sunday_date}")
        return sunday_date
    except ValueError as e:
        print(f"{red_x()} Invalid date format. Use YYYY-MM-DD: {e}")
        sys.exit(1)

def generate_commit_dates(word, start_date, total_weeks=52):
    """Generate commit timeline with proper spacing"""
    commit_dates = []
    current_week = 0

    for i, char in enumerate(word.upper()):
        pattern = LETTERS.get(char, [[0]*5]*7)

        for col in range(5):
            if char in ['I', '!', ' '] and col != 2:
                continue

            for row in range(7):
                if pattern[row][col]:
                    commit_date = start_date + timedelta(
                        weeks=current_week,
                        days=row
                    )
                    commit_dates.append(commit_date)

            current_week += 1

        if i < len(word) - 1:
            current_week += 1

    return commit_dates

def make_commit(date: datetime) -> bool:
    """Create realistic file change commit"""
    try:
        os.makedirs("artifacts", exist_ok=True)
        with open(FILE_NAME, "a") as f:
            f.write(f"\n## Update {date.strftime('%Y-%m-%d')}\n")
            f.write(f"- Feature {random.randint(1,100)}\n")

        date_str = date.strftime("%Y-%m-%dT12:00:00Z")
        success, error = run_safe("git add .")
        if not success:
            print(f"{red_x()} Failed to stage changes: {error}")
            return False

        success, error = run_safe(
            f'GIT_AUTHOR_DATE="{date_str}" GIT_COMMITTER_DATE="{date_str}" git commit -m "Update"'
        )
        if not success:
            print(f"{red_x()} Failed to commit: {error}")
            return False

        return True
    except Exception as e:
        print(f"{red_x()} Error creating commit: {str(e)}")
        return False

def main():
    global REPO_OWNER
    REPO_OWNER = get_repo_owner()

    parser = argparse.ArgumentParser(description="Generate GitHub contribution art")
    parser.add_argument("message", help="Text to display (A-Z and ! only)")
    parser.add_argument("--start-date",
                       help="Starting date (YYYY-MM-DD), will adjust to Sunday")
    parser.add_argument("--mode", choices=["latest", "year"], default="latest",
                       help="Time range: 'latest' (default) or 'year'")
    parser.add_argument("--year", type=int, help="Specific year (e.g., 2020)")
    parser.add_argument("--reset", action="store_true",
                       help="Reset repository (clears history)")
    parser.add_argument("--visibility", choices=["private", "public"], default="private",
                       help="Repository visibility (default: private)")
    args = parser.parse_args()

    # Handle !!.
    # args.message = args.message.replace('\\!', '!').upper()

    if not set_repo_visibility(args.visibility):
        print(f"{yellow_bang()} Continuing with potentially incorrect visibility")

    if args.reset:
        print(f"{blue_star()} Resetting repository, --reset flag detected...")
        if not wipe_local_history():
            print(f"{red_x()} Aborting due to local reset failure")
            sys.exit(1)

        if not reset_remote_repo(args.visibility):
            print(f"{yellow_bang()} Continuing with potentially stale remote")
    else:
        print(f"{blue_star()} Using existing repository, no reset requested")

    try:
        year = args.year if args.mode == 'year' and args.year is not None else None
        start_date = adjust_start_date(args.start_date, year)
    except ValueError as e:
        print(f"{red_x()} {e}")
        sys.exit(1)

    print(f"{blue_star()} Creating '{args.message}' starting from {start_date}...")

    if args.mode == "year" and args.year:
        total_weeks = 52
    else:
        total_weeks = 52

    dates = generate_commit_dates(args.message, start_date, total_weeks)
    total_commits = len(dates)
    failed_commits = 0

    for i, date in enumerate(dates, 1):
        if not make_commit(date):
            failed_commits += 1
        if i % 10 == 0 or i == total_commits:
            print(f"{blue_star()} Progress: {i}/{total_commits} commits", end="\r")

    print(f"\n\n{blue_star()} Pushing message to GitHub...")
    success, error = run_safe("git push -f origin main")
    if not success:
        print(f"{red_x()} Failed to push changes: {error}")
        sys.exit(1)

    print(f"{green_check()} Successfully completed!")
    print("""                    _._
                __.{,_.).__
             .-"           "-.
           .'  __.........__  '.
          /.-'`___.......___`'-.\\
         /_.-'` /   \\ /   \\ `'-._\\
         |     |   '/ \\'   |     |
         |      '-'     '-'      |
         ;                       ;
         _\\         ___         /_
        /  '.'-.__  ___  __.-'.'  \\
      _/_    `'-..._____...-'`    _\\_
     /   \\           .           /   \\
     \\____)          .           (____/
         \\___________.___________/
           \\___________________/
          (_____________________)
       SCREW YOU ALL, I'M GOING HOME""")
    if failed_commits > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
