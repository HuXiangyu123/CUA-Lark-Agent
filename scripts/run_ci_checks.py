from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

CHECKS: list[tuple[str, list[str]]] = [
    (
        "formatter-version",
        [sys.executable, "-m", "black", "--version"],
    ),
    (
        "black",
        [
            sys.executable,
            "-m",
            "black",
            "--check",
            "launcher.py",
            "gui_agents",
            "tests",
        ],
    ),
    (
        "startup",
        [sys.executable, "-m", "unittest", "tests.test_agent_startup", "-v"],
    ),
    (
        "launcher-env",
        [sys.executable, "-m", "unittest", "tests.test_launcher_env_config", "-v"],
    ),
    (
        "constraints",
        [sys.executable, str(REPO_ROOT / "scripts" / "check_constraints.py")],
    ),
]


def _run_check(name: str, command: list[str]) -> int:
    print(f"[ci] running {name}: {' '.join(command)}")
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode != 0:
        print(f"[ci] failed {name} with exit code {completed.returncode}")
        return completed.returncode
    print(f"[ci] passed {name}")
    return 0


def main() -> int:
    for name, command in CHECKS:
        code = _run_check(name, command)
        if code != 0:
            return code
    print("[ci] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
