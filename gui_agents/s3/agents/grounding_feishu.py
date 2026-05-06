"""Windows + Feishu/Lark ACI extension of the upstream OSWorldACI.

Adds:
- Primary-screen grounded coordinate alignment for Feishu runtime
- Enhanced grounding tracing in generate_coords()
- CJK-compatible OCR regex in get_ocr_elements()
- Feishu-specific agent actions: feishu_focus, feishu_click, feishu_type, feishu_doc_click
- Windows open() branch
"""

import re
import sys
import time
from io import BytesIO
from typing import Dict, List, Optional

from PIL import Image, ImageGrab

from gui_agents.feishu.tooling.tool_router import build_feishu_tool_guidance
from gui_agents.s3.agents.grounding import OSWorldACI, agent_action
from gui_agents.s3.memory.procedural_memory import PROCEDURAL_MEMORY
from gui_agents.s3.agents._feishu_exec import (
    LOG_DIR,
    REPO_ROOT,
    build_feishu_doc_click_code,
    build_feishu_doc_type_code,
    build_feishu_focus_code,
    build_feishu_safe_focus_code,
    build_feishu_uia_click_code,
    build_win32_click_code,
    build_windows_open_code,
)
from gui_agents.s3.utils.common_utils import call_llm_safe


def _build_feishu_clipboard_paste_code(
    text: str,
    *,
    overwrite: bool = False,
    enter: bool = False,
    call_guard: str | None = None,
) -> str:
    """Generate Windows clipboard paste code for Unicode Feishu text input."""

    log_path = str(REPO_ROOT / LOG_DIR)
    call_line = (
        "_feishu_paste_text("
        f"_FEISHU_PASTE_TEXT, _overwrite={overwrite!r}, _enter={enter!r}"
        ")\n"
    )
    if call_guard:
        call_block = f"if {call_guard}:\n    {call_line}"
    else:
        call_block = call_line

    return f"""
import ctypes
import pathlib
import time

try:
    import pyperclip as _feishu_clipboard
except Exception:
    _feishu_clipboard = None

_FEISHU_PASTE_TEXT = {text!r}
_FEISHU_LOG_PATH = pathlib.Path({log_path!r}) / "execution-trace.log"

def _feishu_set_clipboard_text(_text):
    if _feishu_clipboard is not None:
        _feishu_clipboard.copy(_text)
        time.sleep(0.12)
        try:
            return _feishu_clipboard.paste() == _text
        except Exception:
            return True
    import tkinter as _tk
    _root = _tk.Tk()
    _root.withdraw()
    _root.clipboard_clear()
    _root.clipboard_append(_text)
    _root.update()
    _root.destroy()
    time.sleep(0.12)
    return True

def _feishu_key_down(_vk):
    ctypes.windll.user32.keybd_event(_vk, 0, 0, 0)

def _feishu_key_up(_vk):
    ctypes.windll.user32.keybd_event(_vk, 0, 0x0002, 0)

def _feishu_tap_key(_vk):
    _feishu_key_down(_vk)
    time.sleep(0.03)
    _feishu_key_up(_vk)
    time.sleep(0.05)

def _feishu_ctrl_combo(_vk):
    _feishu_key_down(0x11)
    time.sleep(0.02)
    _feishu_key_down(_vk)
    time.sleep(0.05)
    _feishu_key_up(_vk)
    _feishu_key_up(0x11)
    time.sleep(0.12)

def _feishu_paste_text(_text, _overwrite=False, _enter=False):
    _clipboard_ok = _feishu_set_clipboard_text(_text)
    if _overwrite:
        _feishu_ctrl_combo(0x41)  # A
        _feishu_tap_key(0x08)  # Backspace
    _feishu_ctrl_combo(0x56)  # V
    if _enter:
        _feishu_tap_key(0x0D)  # Enter
    try:
        _FEISHU_LOG_PATH.parent.mkdir(exist_ok=True)
        with open(_FEISHU_LOG_PATH, "a", encoding="utf-8") as _tf:
            _tf.write(
                "FEISHU_TYPED_UNICODE: "
                + repr({{"text": _text, "clipboard_ok": _clipboard_ok, "overwrite": _overwrite, "enter": _enter}})
                + "\\n"
            )
    except Exception:
        pass

{call_block}
"""


class WindowsFeishuACI(OSWorldACI):
    """OSWorldACI extended for Windows multi-monitor + Feishu/Lark automation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def resize_coordinates(self, coordinates: List[int]) -> List[int]:
        coord_scale = self.engine_params_for_grounding.get("ground_coord_scale")
        if coord_scale is not None:
            image_x = round(coordinates[0] * self.width / coord_scale)
            image_y = round(coordinates[1] * self.height / coord_scale)
        else:
            grounding_width = self.engine_params_for_grounding["grounding_width"]
            grounding_height = self.engine_params_for_grounding["grounding_height"]
            image_x = round(coordinates[0] * self.width / grounding_width)
            image_y = round(coordinates[1] * self.height / grounding_height)
        return [image_x, image_y]

    def generate_coords(self, ref_expr: str, obs: Dict) -> List[int]:
        model_name = self.engine_params_for_grounding.get("model", "").lower()
        is_doubao = "doubao" in model_name

        self.grounding_model.reset()

        if is_doubao:
            coord_scale = self.engine_params_for_grounding.get(
                "ground_coord_scale", 1000
            )
            platform_names = {
                "windows": "Windows",
                "darwin": "macOS",
                "linux": "Linux",
            }
            platform_name = platform_names.get(self.platform, self.platform)
            prompt = (
                f"You are a GUI agent operating on a {platform_name} desktop. "
                "Given a screenshot, locate the described UI element "
                "and output the click action with its coordinates.\n\n"
                "## Action Space\n"
                "click(point='<point>x y</point>')\n\n"
                "## Output Format\n"
                "Thought: ...\n"
                "Action: click(point='<point>x y</point>')\n\n"
                "## Rules\n"
                f"- Coordinates: use 0-{coord_scale} for both axes.\n"
                "- Locate the center point of the described element.\n"
                "- End your response with the Action line.\n\n"
                f"## Element Description\n{ref_expr}"
            )
            self.grounding_model.add_message(
                text_content=prompt,
                image_content=obs["screenshot"],
                put_text_last=False,
            )
            response = call_llm_safe(self.grounding_model, temperature=0.0, top_p=0.7)
        else:
            prompt = f"Query:{ref_expr}\nOutput only the coordinate of one point in your response.\n"
            self.grounding_model.add_message(
                text_content=prompt, image_content=obs["screenshot"], put_text_last=True
            )
            response = call_llm_safe(self.grounding_model)

        print("RAW GROUNDING MODEL RESPONSE:", response)

        point_match = re.search(r"<point>\s*(\d+)\s+(\d+)\s*</point>", response)
        if point_match:
            return [int(point_match.group(1)), int(point_match.group(2))]

        numericals = re.findall(r"\d+", response)
        try:
            obs_image = Image.open(BytesIO(obs["screenshot"]))
            obs_size = obs_image.size
        except Exception:
            obs_size = None
        trace_payload = {
            "ref_expr": ref_expr,
            "response_tail": (
                response[-400:] if isinstance(response, str) else repr(response)
            ),
            "numericals": numericals[:8],
            "obs_size": obs_size,
            "grounding_size": (
                self.engine_params_for_grounding["grounding_width"],
                self.engine_params_for_grounding["grounding_height"],
            ),
        }
        self._trace_execution("GROUNDING_RESPONSE: " + repr(trace_payload))
        assert len(numericals) >= 2
        coords = [int(numericals[0]), int(numericals[1])]
        if obs_size is not None:
            raw_x, raw_y = coords
            gw = self.engine_params_for_grounding["grounding_width"]
            gh = self.engine_params_for_grounding["grounding_height"]
            if raw_x < 0 or raw_y < 0 or raw_x > gw or raw_y > gh:
                self._trace_execution(
                    "GROUNDING_COORD_OUT_OF_RANGE: "
                    + repr(
                        {
                            "coords": coords,
                            "grounding_size": (gw, gh),
                            "obs_size": obs_size,
                            "ref_expr": ref_expr,
                        }
                    )
                )
        return coords

    def get_ocr_elements(self, b64_image_data: str):
        import pytesseract
        from collections import defaultdict
        from pytesseract import Output

        image = Image.open(BytesIO(b64_image_data))
        image_data = pytesseract.image_to_data(image, output_type=Output.DICT)
        # CJK-compatible: strip leading/trailing punctuation while preserving CJK characters
        for i, word in enumerate(image_data["text"]):
            image_data["text"][i] = re.sub(r"^\W+|\W+$", "", word, flags=re.UNICODE)

        ocr_elements = []
        ocr_table = "Text Table:\nWord id\tText\n"
        grouping_map = defaultdict(list)
        ocr_id = 0
        for i in range(len(image_data["text"])):
            block_num = image_data["block_num"][i]
            if image_data["text"][i]:
                grouping_map[block_num].append(image_data["text"][i])
                ocr_table += f"{ocr_id}\t{image_data['text'][i]}\n"
                ocr_elements.append(
                    {
                        "id": ocr_id,
                        "text": image_data["text"][i],
                        "group_num": block_num,
                        "word_num": len(grouping_map[block_num]),
                        "left": image_data["left"][i],
                        "top": image_data["top"][i],
                        "width": image_data["width"][i],
                        "height": image_data["height"][i],
                    }
                )
                ocr_id += 1
        return ocr_table, ocr_elements

    @agent_action
    def open(self, app_or_filename: str):
        """Open any application or file. The Windows path handles Feishu, browsers,
        and generic apps without calling sandbox scripts.
        Args:
            app_or_filename:str, the name of the application or filename to open
        """
        if self.platform == "linux":
            return f"import pyautogui; pyautogui.hotkey('win'); time.sleep(0.5); pyautogui.write({repr(app_or_filename)}); time.sleep(1.0); pyautogui.hotkey('enter'); time.sleep(0.5)"
        if self.platform == "darwin":
            return f"import pyautogui; import time; pyautogui.hotkey('command', 'space', interval=0.5); pyautogui.typewrite({repr(app_or_filename)}); pyautogui.press('enter'); time.sleep(1.0)"
        if self.platform == "windows":
            return build_windows_open_code(app_or_filename)
        raise AssertionError(f"Unsupported platform: {self.platform}")

    # ------------------------------------------------------------------
    # Host-side helpers (run at agent-eval time, NOT inside exec())
    # ------------------------------------------------------------------

    def _trace_execution(self, message: str) -> None:
        try:
            trace_path = REPO_ROOT / LOG_DIR / "execution-trace.log"
            trace_path.parent.mkdir(exist_ok=True)
            with trace_path.open("a", encoding="utf-8") as f:
                f.write(message + "\n")
        except Exception as exc:
            print(f"FEISHU_TRACE_WRITE_ERROR: {exc!r}", file=sys.stderr)

    def capture_observation(self, scaled_width: int, scaled_height: int) -> Dict:
        screenshot = ImageGrab.grab()
        captured_width, captured_height = screenshot.size
        resized = screenshot.resize((scaled_width, scaled_height), Image.LANCZOS)
        buffered = BytesIO()
        resized.save(buffered, format="PNG")
        observation = {
            "screenshot": buffered.getvalue(),
            "image_width": scaled_width,
            "image_height": scaled_height,
            "source_image_width": captured_width,
            "source_image_height": captured_height,
        }
        self._trace_execution(
            "FEISHU_CAPTURE_OBS: "
            + repr(
                {
                    "captured_size": (captured_width, captured_height),
                    "resized_size": (scaled_width, scaled_height),
                    "capture_mode": "primary_screen",
                }
            )
        )
        return observation

    def _extract_obs_ocr_text(self, obs: Dict) -> str:
        if not isinstance(obs, dict):
            return ""

        cached = obs.get("ocr_text")
        if isinstance(cached, str) and cached.strip():
            return cached

        screenshot = obs.get("screenshot")
        if not screenshot:
            return ""

        try:
            _, ocr_elements = self.get_ocr_elements(screenshot)
        except Exception as exc:
            self._trace_execution(f"FEISHU_OCR_ENRICH_ERROR: {exc!r}")
            return ""

        words = [elem.get("text", "").strip() for elem in ocr_elements]
        ocr_text = "\n".join(word for word in words if word)
        if ocr_text:
            obs["ocr_text"] = ocr_text
            self._trace_execution(
                "FEISHU_OCR_ENRICHED: " + repr({"word_count": len(words)})
            )
        return ocr_text

    def _absolute_click_code(
        self, x: int, y: int, num_clicks: int = 1, button_type: str = "left"
    ) -> str:
        return (
            "import pyautogui\n"
            f"pyautogui.click({x}, {y}, clicks={num_clicks}, button={button_type!r})\n"
        )

    def _focus_feishu_now(self) -> bool:
        """Bring the Feishu/Lark window to the foreground using ctypes only.

        Safe to call host-side: uses GetTopWindow/GetWindow loop which cannot
        hang, unlike Desktop(backend='uia').
        """
        try:
            import ctypes
            import os as _os

            GW_HWNDNEXT = 2
            PQLI = 0x1000

            def _get_exe(hwnd):
                pid = ctypes.c_ulong(0)
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                h = ctypes.windll.kernel32.OpenProcess(PQLI, False, pid.value)
                if not h:
                    return ""
                try:
                    buf = ctypes.create_unicode_buffer(512)
                    sz = ctypes.c_ulong(512)
                    ctypes.windll.kernel32.QueryFullProcessImageNameW(
                        h, 0, buf, ctypes.byref(sz)
                    )
                    return _os.path.basename(buf.value).lower()
                finally:
                    ctypes.windll.kernel32.CloseHandle(h)

            hwnd = ctypes.windll.user32.GetTopWindow(0)
            skipped_windows = 0
            while hwnd:
                try:
                    if ctypes.windll.user32.IsWindowVisible(hwnd):
                        exe = _get_exe(hwnd)
                        if "feishu" in exe or "lark" in exe:
                            ctypes.windll.user32.ShowWindow(hwnd, 9)
                            ctypes.windll.user32.SetForegroundWindow(hwnd)
                            time.sleep(0.5)
                            self._trace_execution(
                                f"FEISHU_FOCUS_NOW: ctypes hwnd={hwnd} exe={exe}"
                            )
                            return True
                except Exception:
                    skipped_windows += 1
                hwnd = ctypes.windll.user32.GetWindow(hwnd, GW_HWNDNEXT)

            if skipped_windows:
                self._trace_execution(
                    f"FEISHU_FOCUS_NOW: skipped_windows={skipped_windows}"
                )
            self._trace_execution("FEISHU_FOCUS_NOW: window_not_found")
            return False
        except Exception as exc:
            self._trace_execution(f"FEISHU_FOCUS_NOW_ERROR: {exc!r}")
            return False

    def _refresh_obs_screenshot(self) -> None:
        try:
            screenshot = ImageGrab.grab(all_screens=True)
            captured_size = screenshot.size
            grounding_width = self.engine_params_for_grounding["grounding_width"]
            grounding_height = self.engine_params_for_grounding["grounding_height"]
            screenshot = screenshot.resize(
                (grounding_width, grounding_height), Image.LANCZOS
            )
            buffered = BytesIO()
            screenshot.save(buffered, format="PNG")
            if self.obs is None:
                self.obs = {}
            self.obs["screenshot"] = buffered.getvalue()
            self._trace_execution(
                "FEISHU_REFRESH_OBS: "
                + repr(
                    {
                        "captured_size": captured_size,
                        "grounding_size": (grounding_width, grounding_height),
                    }
                )
            )
        except Exception as exc:
            self._trace_execution(f"FEISHU_REFRESH_OBS_ERROR: {exc!r}")

    def _repair_text_mojibake(self, text: str) -> str:
        """Repair Chinese text that was UTF-8 bytes decoded as GBK."""
        if not isinstance(text, str):
            return text
        candidates = [text]
        for encoding in ("gbk", "gb18030", "cp936"):
            for errors in ("strict", "ignore"):
                try:
                    repaired = text.encode(encoding, errors=errors).decode(
                        "utf-8", errors=errors
                    )
                except UnicodeError:
                    continue
                if repaired and repaired not in candidates:
                    candidates.append(repaired)

        def score(value: str) -> int:
            good_chars = sum("一" <= ch <= "鿿" for ch in value)
            bad_markers = sum(
                value.count(m)
                for m in (
                    "?",
                    "\u951f",
                    "\u95bf",
                    "\u95b9",
                    "\u95b8",
                    "\u934f",
                    "\u6fde",
                    "\u7023",
                    "\u599e",
                    "\u9410",
                    "\u9354",
                    "\u9352",
                    "\u55d5",
                    "\u97e9",
                    "\u690b",
                    "\u70b0",
                    "\u529f",
                    "\u6d5c",
                    "\u621e",
                    "\u6783",
                    "\u5997",
                    "\u93c2",
                    "\u677f",
                    "\u7f13",
                    "\u7ecc",
                    "\u6ae7",
                    "\u7f01",
                    "\u581c",
                    "\u7c2c",
                    "\u6fc2",
                    "\u6212",
                    "\u7c21",
                )
            )
            return (
                good_chars * 3
                - bad_markers * 5
                + len(value.replace("?", "").replace("\u951f", ""))
            )

        repaired = max(candidates, key=score)
        if repaired != text:
            print("TEXT_MOJIBAKE_REPAIRED:", repr(text), "=>", repr(repaired))
        return repaired

    def _extract_feishu_target_text(self, element_description: str) -> str:
        """Extract UIA target text conservatively.

        Wrongly collapsing a long relational description into a short context token
        causes incorrect clicks. For UIA helpers, a miss is safer than a false hit,
        so only shorten inputs that already look like explicit visible text.
        """
        text = self._repair_text_mojibake(element_description).strip()
        if not text:
            return text

        def normalize(value: str) -> str:
            return value.strip(" \t\r\n.,!?;:;()[]{}<>")

        normalized = normalize(text)
        if not normalized:
            return text

        # Long relational descriptions should pass through unchanged. This avoids
        # mis-extracting nearby context words such as chat titles or "Aa".
        relation_markers = (
            "right of",
            "left of",
            "next to",
            "immediately",
            "bottom",
            "top",
            "inside",
            "at the",
            "旁边",
            "右侧",
            "左侧",
            "底部",
            "顶部",
            "附近",
            "聊天框",
            "输入框",
            "button",
            "icon",
            "chat window",
        )
        lower_text = normalized.lower()
        if (
            len(normalized) > 32
            or any(marker in lower_text for marker in relation_markers)
            or normalized.count(" ") >= 4
        ):
            return normalized

        quoted = [
            normalize(match.group(1))
            for match in re.finditer(r"""['"]([^'"]{1,80})['"]""", normalized)
            if normalize(match.group(1))
        ]

        # Only collapse to quoted text when the whole input is effectively that
        # exact label, not when the quote is merely a reference object.
        if len(quoted) == 1:
            quoted_text = quoted[0]
            stripped = normalize(
                re.sub(r"""['"]([^'"]{1,80})['"]""", quoted_text, normalized)
            )
            if stripped == quoted_text:
                return quoted_text

        return normalized

    # ------------------------------------------------------------------
    # Feishu-specific agent actions
    # ------------------------------------------------------------------

    @agent_action
    def feishu_focus(self):
        """Focus the running Feishu/Lark desktop window. Use this before Feishu-specific actions.
        Args:
        """
        return build_feishu_focus_code()

    @agent_action
    def feishu_click_message_input(self):
        """Click the IM composer input using semantic runtime grounding.
        Use this when the Feishu IM chat main page is already visible and you need
        to focus the message input without static page-descriptor coordinates.
        Args:
        """
        return self.click(
            "Feishu IM message composer input at the bottom of the current chat"
        )

    @agent_action
    def feishu_type_message(
        self,
        text: str,
        overwrite: bool = False,
        enter: bool = False,
        focus_first: bool = True,
    ):
        """Paste text into the IM composer, optionally clicking it first.
        Prefer this over generic type tools when sending a normal IM message in
        the Feishu desktop chat main page.
        Args:
            text:str, text to paste into the chat composer
            overwrite:bool, whether to select existing draft before pasting
            enter:bool, whether to press Enter after pasting
            focus_first:bool, whether to click the message-input region first (default True; set False when composer is already focused)
        """
        focus_code = self.feishu_click_message_input() if focus_first else ""
        return (
            "import pyautogui\n"
            + focus_code
            + _build_feishu_clipboard_paste_code(
                text,
                overwrite=overwrite,
                enter=enter,
            )
        )

    @agent_action
    def feishu_click_send_button(self):
        """Click the IM send button using semantic runtime grounding.
        Prefer this when Enter is unsuitable and the send_button / send button is visible.
        Args:
        """
        return self.click("Feishu IM send button in the current chat composer")

    @agent_action
    def feishu_vc_click_start_card(self):
        """Click the Start Meeting entry on the Feishu VC home page.
        Prefer this when the VC home surface shows both Start and Join cards.
        Args:
        """
        return self.feishu_click("发起会议")

    @agent_action
    def feishu_vc_click_join_card(self):
        """Click the Join Meeting entry on the Feishu VC home page.
        Prefer this when the user wants to join an existing meeting by meeting ID.
        Args:
        """
        return self.feishu_click("加入会议")

    @agent_action
    def feishu_vc_click_start_button(self):
        """Click the Start Meeting primary button from the VC start preview.
        Use this after confirming the preview window is already visible.
        Args:
        """
        return self.feishu_click("开始会议")

    @agent_action
    def feishu_vc_type_meeting_id(
        self,
        meeting_id: str,
        overwrite: bool = True,
        focus_first: bool = True,
    ):
        """Type the meeting ID into the VC join preview input.
        Prefer this over long natural-language descriptions for the meeting-ID box.
        Args:
            meeting_id:str, the meeting ID to paste
            overwrite:bool, whether to clear the input first
            focus_first:bool, whether to target the visible meeting ID input first
        """
        return self.feishu_type(
            meeting_id,
            "会议 ID" if focus_first else None,
            overwrite=overwrite,
            enter=False,
        )

    @agent_action
    def feishu_vc_click_join_button(self):
        """Click the Join Meeting primary button from the VC join preview.
        Use this after the meeting ID has been entered.
        Args:
        """
        return self.feishu_click("加入会议")

    @agent_action
    def feishu_vc_click_invite_button(self):
        """Click the invite/participants control in an active VC meeting.
        Prefer grounded visual clicking because this toolbar control may not always
        expose stable UIA text.
        Args:
        """
        return self.click(
            "the invite or participants control in the active Feishu video meeting toolbar"
        )

    @agent_action
    def feishu_vc_click_invite_entry(self):
        """Click the visible Invite entry after the active-meeting invite popover opens.
        Use this when the small invite popover shows options such as 邀请 and 复制邀请链接.
        Args:
        """
        return self.feishu_click("邀请")

    @agent_action
    def feishu_vc_click_share_button(self):
        """Click the Share button inside the VC invite dialog.
        Use this only after the invite dialog is already open and the recipient is selected.
        Args:
        """
        return self.feishu_click("分享")

    @agent_action
    def feishu_type(
        self,
        text: str,
        element_description: Optional[str] = None,
        overwrite: bool = False,
        enter: bool = False,
    ):
        """Focus Feishu/Lark and paste text, optionally clicking an element first using UIA.
        Args:
            text:str, text to paste into Feishu
            element_description:str, optional description of the Feishu input element to click before typing
            overwrite:bool, whether to select all existing text before pasting
            enter:bool, whether to press Enter after pasting
        """
        click_code = ""
        if element_description is not None:
            element_description = self._repair_text_mojibake(element_description)
            target_text = self._extract_feishu_target_text(element_description)
            self._trace_execution(
                "FEISHU_TYPE_UIA_ONLY: "
                + repr({"description": element_description, "target_text": target_text})
            )
            click_code = build_feishu_uia_click_code(target_text, 1, "left")

        if click_code:
            # Already clicked a specific element — don't refocus the main window
            # (that would close any floating dialog that's now open).
            focus_code = ""
        else:
            # Safe focus: only brings Feishu forward when it isn't already foreground.
            focus_code = build_feishu_safe_focus_code()

        if click_code:
            _paste_block = _build_feishu_clipboard_paste_code(
                text,
                overwrite=overwrite,
                enter=enter,
                call_guard="clicked",
            )
            return focus_code + f"\nimport pyautogui\n{click_code}\n{_paste_block}\n"

        return focus_code + _build_feishu_clipboard_paste_code(
            text,
            overwrite=overwrite,
            enter=enter,
        )

    @agent_action
    def feishu_doc_click(self, button_name: str):
        """Click a toolbar button in a Feishu cloud document open in the browser.
        Uses the foreground browser window's geometry instead of visual grounding.
        Only use this when the Feishu cloud doc is open in a browser window.
        Args:
            button_name:str, exact name of the toolbar button, e.g. "分享", "评论", "更多", "分析"
        """
        button_name = self._repair_text_mojibake(button_name)
        self._trace_execution("FEISHU_DOC_CLICK: " + repr({"button_name": button_name}))
        return build_feishu_doc_click_code(button_name)

    @agent_action
    def feishu_doc_type(self, text: str):
        """Paste text into the currently focused element in the browser WITHOUT clicking.

        Use this after feishu_doc_click("分享") when the share popup's search input is
        already focused. Do NOT use agent.type(element_description, text) in that context
        because the click to locate the element dismisses the light-dismiss popup.
        Args:
            text:str, the text to paste into the focused input field
        """
        text = self._repair_text_mojibake(text)
        self._trace_execution("FEISHU_DOC_TYPE: " + repr({"text": text}))
        return build_feishu_doc_type_code(text)

    def build_worker_system_prompt(self, instruction: str, platform: str) -> str:
        skipped_actions = {
            "set_cell_values",
            "drag_and_drop",
            "highlight_text_span",
            "save_to_knowledge",
            "call_code_agent",
            "hold_and_press",
        }

        lower_instruction = instruction.lower()
        is_im_task = any(
            keyword in instruction
            for keyword in ("消息", "群", "聊天", "会话", "发送", "回复", "表情", "@")
        )
        is_doc_task = any(
            keyword in instruction for keyword in ("文档", "云文档", "分享", "浏览器")
        ) or any(
            keyword in lower_instruction for keyword in ("document", "browser", "share")
        )
        is_vc_task = any(
            keyword in instruction
            for keyword in (
                "视频会议",
                "发起会议",
                "开始会议",
                "加入会议",
                "会议 ID",
                "会议ID",
                "会议号",
                "分享邀请",
                "复制邀请",
            )
        )

        if is_im_task and not is_doc_task:
            skipped_actions.update(
                {
                    "feishu_doc_click",
                    "feishu_doc_type",
                    "scroll",
                    "switch_applications",
                    "type",
                }
            )
        elif (
            not any(keyword in instruction for keyword in ("切换", "打开"))
            and "open" not in lower_instruction
        ):
            skipped_actions.add("switch_applications")

        sys_prompt = PROCEDURAL_MEMORY.construct_simple_worker_procedural_memory(
            type(self), skipped_actions=sorted(skipped_actions)
        ).replace("CURRENT_OS", platform)
        sys_prompt = sys_prompt.replace("TASK_DESCRIPTION", instruction)

        if is_im_task and not is_doc_task:
            sys_prompt += (
                "\n\n## Feishu IM Prior Tool Strategy\n"
                "- First reason from the screenshot before choosing a tool.\n"
                "- If the IM composer is already visible, prefer `agent.feishu_type_message(...)` "
                "or `agent.feishu_click_message_input()` over long natural-language element descriptions.\n"
                "- When the composer is already focused (blinking cursor, placeholder gone), "
                "call `agent.feishu_type_message(text, focus_first=False)` to skip the redundant click.\n"
                "- Use `agent.feishu_click(...)` only for controls with exact visible text.\n"
                "- For icon-only controls such as emoji, plus, image, or picker items, prefer grounded `agent.click(...)`.\n"
                "- If the task asks for both typing and emoji, finish composing the draft first and then open the emoji picker.\n"
            )

        if is_vc_task:
            sys_prompt += (
                "\n\n## Feishu VC Prior Tool Strategy\n"
                "- First reason from the screenshot before choosing a tool; do not assume a fixed start->preview->meeting chain.\n"
                "- On the VC home page, prefer `agent.feishu_vc_click_start_card()` or `agent.feishu_vc_click_join_card()` instead of long natural-language card descriptions.\n"
                "- On the start preview, prefer `agent.feishu_vc_click_start_button()` when the visible primary button is the next required action.\n"
                "- On the join preview, prefer `agent.feishu_vc_type_meeting_id(...)` for the meeting-ID input and `agent.feishu_vc_click_join_button()` for the visible primary button.\n"
                "- In an active meeting, prefer `agent.feishu_vc_click_invite_button()` for the toolbar invite control.\n"
                "- If a small invite popover appears, use `agent.feishu_vc_click_invite_entry()` to continue into the full invite dialog.\n"
                "- Inside the invite dialog, use visible controls and prefer `agent.feishu_vc_click_share_button()` only when the recipient is already selected.\n"
            )

        return sys_prompt

    def build_dynamic_guidance(self, instruction: str, obs: Dict) -> str:
        try:
            self._extract_obs_ocr_text(obs)
            return build_feishu_tool_guidance(instruction, obs)
        except Exception as exc:
            self._trace_execution(f"FEISHU_TOOL_GUIDANCE_ERROR: {exc!r}")
            return ""

    def _should_prepare_grounded_fallback(
        self, element_description: str, target_text: str
    ) -> bool:
        lower_description = element_description.lower()
        relation_markers = (
            "right of",
            "left of",
            "next to",
            "immediately",
            "inside",
            "bottom",
            "top",
            "icon",
            "emoji",
            "picker",
            "toolbar",
            "右侧",
            "左侧",
            "旁边",
            "图标",
            "表情",
        )
        return (
            len(element_description.strip()) > 32
            or element_description.strip() != target_text.strip()
            or any(marker in lower_description for marker in relation_markers)
        )

    @agent_action
    def feishu_click(
        self,
        element_description: str,
        num_clicks: int = 1,
        button_type: str = "left",
    ):
        """Focus Feishu/Lark, then click an element using UIA text matching.
        For icon-like relational descriptions, prepare a grounded click fallback
        that runs only if UIA text matching misses.
        Args:
            element_description:str, a detailed visual description of the Feishu element to click. Include exact visible text when selecting a chat, row, button, tab, or menu item.
            num_clicks:int, number of times to click the element
            button_type:str, mouse button to press, such as left, middle, or right
        """
        element_description = self._repair_text_mojibake(element_description)
        target_text = self._extract_feishu_target_text(element_description)
        fallback_code = None
        if self.obs is not None and self._should_prepare_grounded_fallback(
            element_description, target_text
        ):
            try:
                coords = self.generate_coords(element_description, self.obs)
                x, y = self.resize_coordinates(coords)
                fallback_code = build_win32_click_code(
                    x, y, num_clicks=num_clicks, button_type=button_type
                )
                self._trace_execution(
                    "FEISHU_CLICK_GROUNDED_FALLBACK_READY: "
                    + repr(
                        {
                            "description": element_description,
                            "target_text": target_text,
                            "point": (x, y),
                        }
                    )
                )
            except Exception as exc:
                self._trace_execution(
                    "FEISHU_CLICK_GROUNDED_FALLBACK_ERROR: "
                    + repr({"description": element_description, "error": repr(exc)})
                )
        self._trace_execution(
            "FEISHU_CLICK_UIA_ONLY: "
            + repr(
                {
                    "description": element_description,
                    "target_text": target_text,
                    "has_grounded_fallback": fallback_code is not None,
                }
            )
        )
        return build_feishu_uia_click_code(
            target_text,
            num_clicks,
            button_type,
            fallback_code=fallback_code,
        )
