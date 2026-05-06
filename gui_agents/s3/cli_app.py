import argparse
import builtins
import datetime
import io
import json
import logging
import os
import platform
import pyautogui

pyautogui.FAILSAFE = False
import signal
import sys
import time

from PIL import Image, ImageGrab

from gui_agents.s3.agents.grounding import OSWorldACI
from gui_agents.s3.agents.agent_s import AgentS3

try:
    from gui_agents.s3.agents.grounding_feishu import WindowsFeishuACI
except ImportError:  # pragma: no cover - runtime dependency only
    WindowsFeishuACI = None

try:
    from gui_agents.feishu.reports import S3RuntimeRecorder
except ImportError:  # pragma: no cover - optional Feishu reporting layer
    S3RuntimeRecorder = None

current_platform = platform.system().lower()

# Global flag to track pause state for debugging
paused = False


def _safe_console_text(value) -> str:
    text = str(value)
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _print(*args, **kwargs) -> None:
    builtins.print(*[_safe_console_text(arg) for arg in args], **kwargs)


def _execute_action_code(exec_code: str) -> dict:
    """Execute a generated action in a shared namespace.

    A dedicated scope keeps helper defs/imports visible to nested functions
    created by the same generated snippet.
    """

    scope = {
        "__builtins__": builtins.__dict__,
        "__name__": "__agent_exec__",
    }
    exec(exec_code, scope, scope)
    return scope


class _TeeTextStream:
    def __init__(self, primary, log_path: str):
        self.primary = primary
        self.log = open(log_path, "a", encoding="utf-8", buffering=1)
        self.encoding = getattr(primary, "encoding", None) or "utf-8"
        self.errors = getattr(primary, "errors", None) or "replace"

    def write(self, text):
        self.primary.write(text)
        self.log.write(str(text))
        if "\n" in str(text):
            self.flush()
        return len(text)

    def flush(self):
        self.primary.flush()
        self.log.flush()

    def isatty(self):
        return False

    def close(self):
        self.flush()
        self.log.close()


def get_char():
    """Get a single character from stdin without pressing Enter"""
    try:
        # Import termios and tty on Unix-like systems
        if platform.system() in ["Darwin", "Linux"]:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return ch
        else:
            # Windows fallback
            import msvcrt

            return msvcrt.getch().decode("utf-8", errors="ignore")
    except:
        return input()  # Fallback for non-terminal environments


def signal_handler(signum, frame):
    """Handle Ctrl+C signal for debugging during agent execution"""
    global paused

    if not paused:
        _print("\n\n🔸 Agent-S Workflow Paused 🔸")
        _print("=" * 50)
        _print("Options:")
        _print("  • Press Ctrl+C again to quit")
        _print("  • Press Esc to resume workflow")
        _print("=" * 50)

        paused = True

        while paused:
            try:
                _print("\n[PAUSED] Waiting for input... ", end="", flush=True)
                char = get_char()

                if ord(char) == 3:  # Ctrl+C
                    _print("\n\n🛑 Exiting Agent-S...")
                    sys.exit(0)
                elif ord(char) == 27:  # Esc
                    _print("\n\n▶️  Resuming Agent-S workflow...")
                    paused = False
                    break
                else:
                    _print(f"\n   Unknown command: '{char}' (ord: {ord(char)})")

            except KeyboardInterrupt:
                _print("\n\n🛑 Exiting Agent-S...")
                sys.exit(0)
    else:
        # Already paused, second Ctrl+C means quit
        _print("\n\n🛑 Exiting Agent-S...")
        sys.exit(0)


# Set up signal handler for Ctrl+C
signal.signal(signal.SIGINT, signal_handler)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

datetime_str: str = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

file_handler = logging.FileHandler(
    os.path.join(LOG_DIR, "normal-{:}.log".format(datetime_str)), encoding="utf-8"
)
debug_handler = logging.FileHandler(
    os.path.join(LOG_DIR, "debug-{:}.log".format(datetime_str)), encoding="utf-8"
)
stdout_handler = logging.StreamHandler(sys.stdout)
sdebug_handler = logging.FileHandler(
    os.path.join(LOG_DIR, "sdebug-{:}.log".format(datetime_str)), encoding="utf-8"
)

file_handler.setLevel(logging.INFO)
debug_handler.setLevel(logging.DEBUG)
stdout_handler.setLevel(logging.INFO)
sdebug_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    fmt="\x1b[1;33m[%(asctime)s \x1b[31m%(levelname)s \x1b[32m%(module)s/%(lineno)d-%(processName)s\x1b[1;33m] \x1b[0m%(message)s"
)
file_handler.setFormatter(formatter)
debug_handler.setFormatter(formatter)
stdout_handler.setFormatter(formatter)
sdebug_handler.setFormatter(formatter)

stdout_handler.addFilter(logging.Filter("desktopenv"))
sdebug_handler.addFilter(logging.Filter("desktopenv"))

logger.addHandler(file_handler)
logger.addHandler(debug_handler)
logger.addHandler(stdout_handler)
logger.addHandler(sdebug_handler)

platform_os = platform.system()


def _get_primary_screen_size() -> tuple[int, int]:
    return pyautogui.size()


def _get_feishu_primary_capture_size() -> tuple[int, int]:
    try:
        screenshot = ImageGrab.grab()
        return screenshot.size
    except Exception:
        return pyautogui.size()


def show_permission_dialog(code: str, action_description: str):
    """Show a platform-specific permission dialog and return True if approved."""
    if platform.system() == "Darwin":
        result = os.system(
            f'osascript -e \'display dialog "Do you want to execute this action?\n\n{code} which will try to {action_description}" with title "Action Permission" buttons {{"Cancel", "OK"}} default button "OK" cancel button "Cancel"\''
        )
        return result == 0
    elif platform.system() == "Linux":
        result = os.system(
            f'zenity --question --title="Action Permission" --text="Do you want to execute this action?\n\n{code}" --width=400 --height=200'
        )
        return result == 0
    return False


def scale_screen_dimensions(width: int, height: int, max_dim_size: int):
    scale_factor = min(max_dim_size / width, max_dim_size / height, 1)
    safe_width = int(width * scale_factor)
    safe_height = int(height * scale_factor)
    return safe_width, safe_height


def _settle_delay(exec_code: str) -> float:
    """Return UI settle delay (seconds) based on action type.

    Navigation & page-load actions need more time before the next screenshot.
    """
    code_lower = exec_code.lower()
    # App switching / opening — heavy UI transition
    if any(k in code_lower for k in ("switch_applications", "hotkey('win'", "open(")):
        return 3.0
    # Click actions that likely trigger navigation or menu expansion
    if "click" in code_lower:
        # Longer wait for clicks that open menus, dialogs, or new pages
        if any(
            k in code_lower
            for k in (
                "新建",
                "文档",
                "菜单",
                "menu",
                "更多",
                "设置",
                "添加",
                "创建",
                "打开",
                "上传",
                "保存",
            )
        ):
            return 2.5
        return 1.5
    # Drag, scroll, type — usually instant
    if any(k in code_lower for k in ("drag", "scroll", "type", "hotkey", "press")):
        return 1.0
    # Default
    return 1.5


def run_agent(
    agent,
    instruction: str,
    scaled_width: int,
    scaled_height: int,
    max_steps: int = 15,
    recorder=None,
):
    global paused

    def _capture_current_observation() -> dict:
        capture_observation = getattr(
            agent.grounding_agent, "capture_observation", None
        )
        if callable(capture_observation):
            return capture_observation(scaled_width, scaled_height)

        screenshot = pyautogui.screenshot()
        screenshot = screenshot.resize((scaled_width, scaled_height), Image.LANCZOS)

        buffered = io.BytesIO()
        screenshot.save(buffered, format="PNG")
        screenshot_bytes = buffered.getvalue()
        return {
            "screenshot": screenshot_bytes,
            "image_width": scaled_width,
            "image_height": scaled_height,
        }

    obs = {}
    traj = "Task:\n" + instruction
    subtask_traj = ""
    final_status = "failed"
    final_failure_reason = "step budget exhausted"
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    tee_stream = None
    if recorder is not None:
        runtime_context = recorder.start(instruction)
        runtime_stdout_path = (
            recorder.runtime_stdout_path()
            if hasattr(recorder, "runtime_stdout_path")
            else None
        )
        if runtime_stdout_path:
            tee_stream = _TeeTextStream(sys.stdout, runtime_stdout_path)
            sys.stdout = tee_stream
            sys.stderr = tee_stream
            stdout_handler.setStream(tee_stream)
        run_dir = recorder.run_dir() if hasattr(recorder, "run_dir") else None
        run_id = (runtime_context or {}).get("run_id")
        if run_id or run_dir:
            _print(
                "FEISHU_RUNTIME_STARTED:",
                json.dumps(
                    {
                        "run_id": run_id,
                        "run_dir": run_dir,
                        "runtime_stdout": runtime_stdout_path,
                    },
                    ensure_ascii=False,
                ),
            )

    try:
        for step in range(max_steps):
            step_index = step + 1
            # Check if we're in paused state and wait
            while paused:
                time.sleep(0.1)
            obs = _capture_current_observation()
            if recorder is not None:
                recorder.record_observation(step_index, obs)

            # Check again for pause state before prediction
            while paused:
                time.sleep(0.1)

            _print(
                f"\n🔄 Step {step_index}/{max_steps}: Getting next action from agent..."
            )
            t_predict_start = time.time()

            # Get next action code from the agent
            info, code = agent.predict(instruction=instruction, observation=obs)
            exec_code = code[0]
            reflection = info.get("reflection") if isinstance(info, dict) else None

            t_predict_elapsed = time.time() - t_predict_start
            _print(f"🧠 模型思考 {t_predict_elapsed:.1f}s")

            if "done" in exec_code.lower() or "fail" in exec_code.lower():
                is_fail = "fail" in exec_code.lower()
                final_status = "failed" if is_fail else "completed"
                final_failure_reason = "agent returned fail" if is_fail else None
                if recorder is not None:
                    recorder.record_action(
                        step_index,
                        exec_code,
                        "failed" if is_fail else "done",
                        final_failure_reason,
                        reflection=reflection,
                    )
                if platform.system() == "Darwin":
                    os.system(
                        f'osascript -e \'display dialog "Task Completed" with title "OpenACI Agent" buttons "OK" default button "OK"\''
                    )
                elif platform.system() == "Linux":
                    os.system(
                        f'zenity --info --title="OpenACI Agent" --text="Task Completed" --width=200 --height=100'
                    )

                break

            if "next" in exec_code.lower():
                if recorder is not None:
                    recorder.record_action(
                        step_index,
                        exec_code,
                        "next",
                        reflection=reflection,
                    )
                continue

            if "wait" in exec_code.lower():
                _print("⏳ Agent requested wait...")
                if recorder is not None:
                    recorder.record_action(
                        step_index,
                        exec_code,
                        "wait",
                        reflection=reflection,
                    )
                time.sleep(5)
                continue

            else:
                _print("EXECUTING CODE:", exec_code)

                # Check for pause state before execution
                while paused:
                    time.sleep(0.1)

                # Pre-exec settle: brief buffer before action
                settle_pre = 0.5 if step > 0 else 0.0
                if settle_pre > 0:
                    time.sleep(settle_pre)

                try:
                    _execute_action_code(exec_code)
                except Exception as exc:
                    final_status = "failed"
                    final_failure_reason = repr(exc)
                    if recorder is not None:
                        recorder.record_action(
                            step_index,
                            exec_code,
                            "failed",
                            final_failure_reason,
                            reflection=reflection,
                        )
                    raise
                if recorder is not None:
                    recorder.record_action(
                        step_index,
                        exec_code,
                        "executed",
                        reflection=reflection,
                    )

                # Post-exec dynamic settle: longer for navigation-triggering actions
                settle_post = _settle_delay(exec_code)
                _print(f"⏳ 等待 UI 稳定 ({settle_pre + settle_post:.1f}s)...")
                time.sleep(settle_post)

                # Update task and subtask trajectories
                if "reflection" in info and "executor_plan" in info:
                    traj += (
                        "\n\nReflection:\n"
                        + str(info["reflection"])
                        + "\n\n----------------------\n\nPlan:\n"
                        + info["executor_plan"]
                    )
    finally:
        if recorder is not None:
            final_observation = obs if isinstance(obs, dict) and obs else None
            try:
                refreshed_observation = _capture_current_observation()
            except Exception:
                refreshed_observation = None
            if isinstance(refreshed_observation, dict) and refreshed_observation:
                final_observation = refreshed_observation

            enrich_ocr = getattr(agent.grounding_agent, "_extract_obs_ocr_text", None)
            if callable(enrich_ocr) and isinstance(final_observation, dict):
                try:
                    enrich_ocr(final_observation)
                except Exception:
                    pass
            artifact_paths = recorder.finalize(
                final_status,
                final_failure_reason,
                final_observation=final_observation,
            )
            if artifact_paths:
                _print("FEISHU_RUNTIME_ARTIFACTS:", repr(artifact_paths))
            if tee_stream is not None:
                stdout_handler.setStream(original_stdout)
                sys.stdout = original_stdout
                sys.stderr = original_stderr
                tee_stream.close()


def build_execution_runtime(
    args,
    engine_params: dict,
    engine_params_for_grounding: dict,
    platform_name: str | None = None,
):
    runtime_platform = (platform_name or current_platform).lower()
    max_dim = max(
        engine_params_for_grounding["grounding_width"],
        engine_params_for_grounding["grounding_height"],
    )

    if args.execution_mode == "feishu_agent":
        if runtime_platform != "windows":
            raise RuntimeError(
                f"{args.execution_mode} mode currently supports Windows only"
            )
        if WindowsFeishuACI is None:
            raise RuntimeError(
                f"{args.execution_mode} mode requires "
                "gui_agents.s3.agents.grounding_feishu"
            )
        screen_width, screen_height = _get_feishu_primary_capture_size()
        scaled_width, scaled_height = scale_screen_dimensions(
            screen_width, screen_height, max_dim_size=max_dim
        )
        grounding_agent = WindowsFeishuACI(
            platform=runtime_platform,
            engine_params_for_generation=engine_params,
            engine_params_for_grounding=engine_params_for_grounding,
            width=screen_width,
            height=screen_height,
        )

        runtime = AgentS3(
            engine_params,
            grounding_agent,
            platform=runtime_platform,
            max_trajectory_length=args.max_trajectory_length,
            enable_reflection=args.enable_reflection,
        )
        return runtime, scaled_width, scaled_height, "agent_s3"

    screen_width, screen_height = pyautogui.size()
    scaled_width, scaled_height = scale_screen_dimensions(
        screen_width, screen_height, max_dim_size=max_dim
    )
    grounding_agent = OSWorldACI(
        platform=runtime_platform,
        engine_params_for_generation=engine_params,
        engine_params_for_grounding=engine_params_for_grounding,
        width=screen_width,
        height=screen_height,
    )
    runtime = AgentS3(
        engine_params,
        grounding_agent,
        platform=runtime_platform,
        max_trajectory_length=args.max_trajectory_length,
        enable_reflection=args.enable_reflection,
    )
    return runtime, scaled_width, scaled_height, "agent_s3"


def main():
    parser = argparse.ArgumentParser(description="Run AgentS3 with specified model.")
    parser.add_argument(
        "--provider",
        type=str,
        default="openai",
        help="Specify the provider to use (e.g., openai, anthropic, etc.)",
    )
    parser.add_argument(
        "--execution_mode",
        type=str,
        default="classic_s3",
        choices=["classic_s3", "feishu_agent"],
        help="Execution branch: legacy AgentS3 or Feishu-enhanced AgentS3.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5-2025-08-07",
        help="Specify the model to use (e.g., gpt-5-2025-08-07)",
    )
    parser.add_argument(
        "--model_url",
        type=str,
        default="",
        help="The URL of the main generation model API.",
    )
    parser.add_argument(
        "--model_api_key",
        type=str,
        default="",
        help="The API key of the main generation model.",
    )
    parser.add_argument(
        "--model_temperature",
        type=float,
        default=None,
        help="Temperature to fix the generation model at (e.g. o3 can only be run with 1.0)",
    )

    # Grounding model config: Self-hosted endpoint based (required)
    parser.add_argument(
        "--ground_provider",
        type=str,
        required=True,
        help="The provider for the grounding model",
    )
    parser.add_argument(
        "--ground_url",
        type=str,
        required=True,
        help="The URL of the grounding model",
    )
    parser.add_argument(
        "--ground_api_key",
        type=str,
        default="",
        help="The API key of the grounding model.",
    )
    parser.add_argument(
        "--ground_model",
        type=str,
        required=True,
        help="The model name for the grounding model",
    )
    parser.add_argument(
        "--grounding_width",
        type=int,
        required=True,
        help="Width of screenshot image after processor rescaling",
    )
    parser.add_argument(
        "--grounding_height",
        type=int,
        required=True,
        help="Height of screenshot image after processor rescaling",
    )
    parser.add_argument(
        "--ground_coord_scale",
        type=int,
        default=None,
        help="Coordinate range the grounding model outputs (1000 for Doubao). "
        "Only needed for models that output in normalized coords.",
    )

    # AgentS3 specific arguments
    parser.add_argument(
        "--max_trajectory_length",
        type=int,
        default=8,
        help="Maximum number of image turns to keep in trajectory",
    )
    parser.add_argument(
        "--enable_reflection",
        action="store_true",
        default=True,
        help="Enable reflection agent to assist the worker agent",
    )
    parser.add_argument(
        "--reflection_mode",
        type=str,
        default="on_failure",
        choices=["full", "reduced", "on_failure", "off"],
        help="Reflection frequency: full (every step), reduced (every other), "
        "on_failure (only after failed steps), off (disabled)",
    )
    parser.add_argument(
        "--reasoning_effort",
        type=str,
        default="medium",
        choices=["low", "medium", "high", "xhigh"],
        help="Reasoning effort for GPT/o-series models (low/medium/high/xhigh)",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=15,
        help="Maximum number of steps (default: 15)",
    )
    args = parser.parse_args()

    # Load the general engine params
    engine_params = {
        "engine_type": args.provider,
        "model": args.model,
        "base_url": args.model_url,
        "api_key": args.model_api_key,
        "temperature": getattr(args, "model_temperature", None),
        "reasoning_effort": args.reasoning_effort,
        "reflection_mode": args.reflection_mode,
    }

    # Load the grounding engine from a custom endpoint
    engine_params_for_grounding = {
        "engine_type": args.ground_provider,
        "model": args.ground_model,
        "base_url": args.ground_url,
        "api_key": args.ground_api_key,
        "grounding_width": args.grounding_width,
        "grounding_height": args.grounding_height,
    }
    if args.ground_coord_scale is not None:
        engine_params_for_grounding["ground_coord_scale"] = args.ground_coord_scale

    runtime, scaled_width, scaled_height, _runtime_kind = build_execution_runtime(
        args,
        engine_params,
        engine_params_for_grounding,
    )

    while True:
        query = input("Query: ")
        runtime.reset()
        recorder = None
        if args.execution_mode == "feishu_agent" and S3RuntimeRecorder is not None:
            recorder = S3RuntimeRecorder()
        run_agent(
            runtime,
            query,
            scaled_width,
            scaled_height,
            args.budget,
            recorder=recorder,
        )

        response = input("Would you like to provide another query? (y/n): ")
        if response.lower() != "y":
            break


if __name__ == "__main__":
    main()
