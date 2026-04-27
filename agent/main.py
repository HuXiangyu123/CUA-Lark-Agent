"""Lark CUA Agent — interactive REPL powered by GPT-5.4."""

import os
import sys
import json
import argparse
import readline
from pathlib import Path

from openai import OpenAI

from agent.commands import format_registry, API_COMMANDS
from agent.gui import GuiRunner
from agent.gui.manual import capture_once, execute_manual_action
from agent.prompts import build_system_prompt, build_user_prompt
from agent.executor import run, parse_action, format_output
from agent.router import RouteMode, resolve_route

# Maximum number of input history lines to keep
_MAX_HISTORY = 100


def _load_history():
    """Load persistent readline history from disk."""
    histfile = Path.home() / ".lark-cua-history"
    if histfile.exists():
        try:
            readline.read_history_file(histfile)
        except Exception:
            pass
    readline.set_history_length(_MAX_HISTORY)


def _save_history():
    """Persist readline history to disk."""
    histfile = Path.home() / ".lark-cua-history"
    try:
        readline.write_history_file(histfile)
    except Exception:
        pass


def _prompt() -> str:
    """Print blank line + prompt with clean terminal state."""
    print()
    sys.stdout.flush()
    return input("You: ")


def load_env():
    """Load .env file from project root into environment."""
    # .env is in the project root, two levels up from agent/main.py
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    if key not in os.environ:
                        os.environ[key] = value.strip()


def init_openai_client() -> tuple[OpenAI, str]:
    """Initialize OpenAI client from environment variables."""
    api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENAI_MODEL", "gpt-5.4")

    if not api_key:
        print("ERROR: OPENAI_API_KEY is not set. Please set it in .env or environment.")
        sys.exit(1)

    return OpenAI(api_key=api_key, base_url=f"{api_base}"), model


def init_gui_client() -> tuple[OpenAI, str]:
    """Initialize GUI/VLM client from GUI-specific env vars with OPENAI fallback."""
    api_base = _first_nonempty_env(
        ("GUI_VLM_API_BASE", "VLM_API_BASE", "CUA_API_BASE", "OPENAI_API_BASE"),
        "https://api.openai.com/v1",
    ).rstrip("/")
    api_key = _first_nonempty_env(
        ("GUI_VLM_API_KEY", "VLM_API_KEY", "CUA_API_KEY", "OPENAI_API_KEY"),
        "",
    )
    model = _first_nonempty_env(
        ("GUI_VLM_MODEL", "VLM_MODEL", "CUA_MODEL", "OPENAI_MODEL"),
        "gpt-5.4",
    )

    if not api_key:
        print("ERROR: GUI_VLM_API_KEY / VLM_API_KEY / OPENAI_API_KEY is not set for GUI mode.")
        sys.exit(1)

    return OpenAI(api_key=api_key, base_url=api_base), model


def build_gui_progress_hook():
    """Optionally stream GUI progress events to stderr for desktop integration."""
    if not _env_flag(("GUI_PROGRESS_STDERR", "CUA_PROGRESS_STDERR"), False):
        return None

    def _hook(payload: dict) -> None:
        print(f"__GUI_PROGRESS__{json.dumps(payload, ensure_ascii=False)}", file=sys.stderr, flush=True)

    return _hook


def build_messages(system_prompt: str, history: list[dict]) -> list[dict]:
    """Build OpenAI messages list."""
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    return messages


def call_llm(client: OpenAI, model: str, messages: list[dict]) -> str:
    """Call the LLM and return the response content."""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
    )
    return response.choices[0].message.content


def repl(client: OpenAI, model: str, system_prompt: str, requested_mode: RouteMode):
    """Interactive REPL loop."""
    history: list[dict] = []
    last_output = ""
    gui_runner = GuiRunner(client, model)

    _load_history()
    print("=" * 60)
    print("Lark CUA Agent — powered by GPT-5.4 + lark-cli")
    print("Type your request in Chinese or English.")
    print(f"Current mode: {requested_mode.value}")
    print("Type 'exit' or 'quit' to stop.")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = _prompt().strip()
        except (EOFError, KeyboardInterrupt):
            _save_history()
            print("\nGoodbye!")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            _save_history()
            print("Goodbye!")
            break

        if not user_input:
            continue

        route, cleaned_input = resolve_route(user_input, requested_mode)
        if not cleaned_input:
            continue

        # Add user message to history
        history.append({"role": "user", "content": cleaned_input})

        if route == RouteMode.GUI:
            print("\n[GUI Thinking...]")
            try:
                result = gui_runner.run(cleaned_input)
            except Exception as e:
                print(f"\nERROR running GUI flow: {e}")
                history.pop()
                continue

            summary = result.to_console_text()
            print(f"\n[GUI Result]: {summary}")
            history.append({"role": "assistant", "content": summary})
            last_output = summary
            print()
            continue

        # Build context with last command output
        user_context = build_user_prompt([], last_output)

        messages = build_messages(system_prompt, history[:-1])
        messages.append({"role": "user", "content": user_context + f"\n\nUser says: {cleaned_input}"})

        print("\n[Thinking...]")
        try:
            response = call_llm(client, model, messages)
        except Exception as e:
            print(f"\nERROR calling LLM: {e}")
            history.pop()  # remove failed user message
            continue

        print(f"\n[Agent]: {response}")

        # Try to extract action
        action = parse_action(response)

        if action:
            command = action.get("command", "").strip()
            thought = action.get("thought", "")
            confirm = action.get("confirm", False)

            if command:
                # Execute the command
                print(f"\n[Executing]: {command}")
                stdout, stderr, code = run(command)
                output = format_output(stdout, stderr, code)
                last_output = output

                print(f"\n[Result]:\n{output}")

                # Add assistant response to history
                history.append({
                    "role": "assistant",
                    "content": response + f"\n\nCommand output:\n{output}"
                })

                # If the result looks like an ID, add a note
                if '"id"' in stdout or '"chat_id"' in stdout or '"open_id"' in stdout:
                    print("\n[Tip] If you need to use an ID from the output above for the next step, include it in your next request.")
            else:
                # No command needed, just a response
                history.append({"role": "assistant", "content": response})
                last_output = ""
        else:
            # No actionable command found, just show the response
            history.append({"role": "assistant", "content": response})
            last_output = ""

        print()


def main():
    load_env()
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "action":
        print(execute_manual_action(args))
        return

    if args.command == "capture":
        print(capture_once(args.output_dir, args.name, args.app))
        return

    if args.command == "gui-run":
        client, default_model = init_gui_client()
        model = args.model or default_model
        runner = GuiRunner(
            client,
            model,
            max_steps=args.max_steps,
            dry_run=args.dry_run,
            pause_seconds=args.pause,
            progress_hook=build_gui_progress_hook(),
        )
        result = runner.run(args.goal)
        if args.json_output:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(result.to_console_text())
        return

    if args.mode == RouteMode.GUI.value:
        client, default_model = init_gui_client()
    else:
        client, default_model = init_openai_client()
    model = args.model or default_model

    command_registry = format_registry()
    system_prompt = build_system_prompt(command_registry, API_COMMANDS)

    repl(client, model, system_prompt, RouteMode(args.mode))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lark CUA Agent")
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument(
        "--mode",
        default="auto",
        choices=[mode.value for mode in RouteMode],
        help="Execution mode: auto, api, gui",
    )

    subparsers = parser.add_subparsers(dest="command")

    capture_parser = subparsers.add_parser(
        "capture",
        help="Capture one screenshot without using any model",
    )
    capture_parser.add_argument(
        "--output-dir",
        default=_first_nonempty_env(("GUI_TRACE_DIR", "CUA_TRACE_DIR"), "traces"),
        help="Directory used to save the screenshot",
    )
    capture_parser.add_argument(
        "--name",
        default="manual_capture",
        help="Base filename for the screenshot",
    )
    capture_parser.add_argument(
        "--app",
        help="Optional app name. If set, capture only that front window region.",
    )

    action_parser = subparsers.add_parser(
        "action",
        help="Run one low-level GUI action without using any model",
    )
    action_parser.add_argument(
        "action_type",
        choices=[
            "click",
            "double_click",
            "right_click",
            "drag",
            "scroll",
            "type",
            "hotkey",
            "wait",
        ],
        help="GUI action type",
    )
    action_parser.add_argument("--x", type=int, help="Start x coordinate")
    action_parser.add_argument("--y", type=int, help="Start y coordinate")
    action_parser.add_argument("--end-x", type=int, help="Drag target x coordinate")
    action_parser.add_argument("--end-y", type=int, help="Drag target y coordinate")
    action_parser.add_argument("--amount", type=int, help="Scroll amount, positive=up negative=down")
    action_parser.add_argument("--text", help="Text for type action")
    action_parser.add_argument(
        "--keys",
        help="Comma-separated keys for hotkey action, e.g. command,k",
    )
    action_parser.add_argument(
        "--duration-ms",
        type=int,
        help="Wait duration in milliseconds",
    )
    action_parser.add_argument("--target", help="Optional semantic target label")
    action_parser.add_argument(
        "--relative-to-app",
        help="Translate x/y and end-x/end-y from app-window-relative coordinates to screen coordinates",
    )
    action_parser.add_argument(
        "--pause",
        type=float,
        default=float(_first_nonempty_env(("GUI_ACTION_PAUSE", "CUA_ACTION_PAUSE"), "0.5")),
        help="Pause between pyautogui actions",
    )
    action_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the action without executing it",
    )

    gui_run_parser = subparsers.add_parser(
        "gui-run",
        help="Run one non-interactive GUI goal with the VLM planner",
    )
    gui_run_parser.add_argument("goal", help="Natural language GUI goal")
    gui_run_parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Override GUI max steps",
    )
    gui_run_parser.add_argument(
        "--pause",
        type=float,
        default=None,
        help="Override pause between GUI actions",
    )
    gui_run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan and trace without executing GUI actions",
    )
    gui_run_parser.add_argument(
        "--json-output",
        action="store_true",
        help="Print structured JSON result instead of plain text",
    )

    return parser


def _first_nonempty_env(names: tuple[str, ...], default: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def _env_flag(names: tuple[str, ...], default: bool) -> bool:
    value = _first_nonempty_env(names, "")
    if value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
