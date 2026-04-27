"""Execute lark-cli commands via subprocess."""

import subprocess
import json
import shlex
from typing import Optional

from agent.json_utils import extract_json_object


def run(command: str, timeout: int = 30) -> tuple[str, str, int]:
    """
    Execute a lark-cli command string via subprocess.

    Returns:
        (stdout, stderr, return_code)
    """
    cmd = command.strip()
    if cmd.startswith("lark-cli"):
        cmd = cmd[len("lark-cli"):].strip()

    # Use shlex.split to correctly handle quoted arguments (e.g. --chat-id "oc_xxx")
    full_cmd = ["lark-cli"] + shlex.split(cmd)

    result = subprocess.run(
        full_cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


def parse_action(text: str) -> Optional[dict]:
    """
    Extract the JSON action block from LLM output.
    Looks for a JSON object containing `command` and `thought`.
    """
    data = extract_json_object(text)
    if isinstance(data, dict) and "command" in data and "thought" in data:
        return data
    return None


def format_output(stdout: str, stderr: str, return_code: int) -> str:
    """Format command output for display."""
    lines = []

    if return_code != 0 and stderr:
        lines.append(f"[ERROR] {stderr}")

    if stdout:
        try:
            # Try to pretty-print JSON
            data = json.loads(stdout)
            lines.append(json.dumps(data, ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            lines.append(stdout)

    return "\n".join(lines) if lines else "(no output)"
