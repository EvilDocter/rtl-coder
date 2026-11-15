"""Cross-platform Task Runner for Windows, Mac, and Linux.

Usage:
  python taskrunner.py test
  python taskrunner.py lint
  python taskrunner.py format
  python taskrunner.py clean
"""

import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str]) -> int:
    print(f"--> {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def test():
    return run_cmd([sys.executable, "-m", "pytest", "tests/"])


def lint():
    return run_cmd([sys.executable, "-m", "ruff", "check", "."])


def format_code():
    return run_cmd([sys.executable, "-m", "ruff", "format", "."])


def clean():
    root = Path(__file__).resolve().parent
    deleted = 0
    for cache_dir in root.rglob("__pycache__"):
        import shutil
        shutil.rmtree(cache_dir, ignore_errors=True)
        deleted += 1
    for pytest_dir in root.rglob(".pytest_cache"):
        import shutil
        shutil.rmtree(pytest_dir, ignore_errors=True)
        deleted += 1
    print(f"Cleaned {deleted} cache directories.")
    return 0


TASKS = {
    "test": test,
    "lint": lint,
    "format": format_code,
    "clean": clean,
}

if __name__ == "__main__":
    task_name = sys.argv[1] if len(sys.argv) > 1 else "test"
    if task_name not in TASKS:
        print(f"Unknown task: {task_name}. Available: {list(TASKS.keys())}")
        sys.exit(1)
    sys.exit(TASKS[task_name]())
