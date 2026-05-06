import unittest

from gui_agents.s3.agents.grounding_feishu import WindowsFeishuACI


class TestFeishuRuntimePriorTools(unittest.TestCase):
    def setUp(self) -> None:
        self.aci = object.__new__(WindowsFeishuACI)
        self.aci.width = 1920
        self.aci.height = 1080
        self.aci.virtual_screen_left = 0
        self.aci.virtual_screen_top = 0
        self.trace_messages: list[str] = []
        self.aci._trace_execution = self.trace_messages.append

    def test_click_message_input_uses_semantic_grounding(self) -> None:
        self.aci.click = (
            lambda description="", *a, **kw: f"agent.click({description!r})"
        )

        code = self.aci.feishu_click_message_input()

        self.assertIn("agent.click(", code)
        self.assertIn("composer input", code)
        self.assertIn(
            "composer input", str(self.aci.feishu_click_message_input.__doc__ or "")
        )

    def test_type_message_uses_semantic_focus_then_paste(self) -> None:
        self.aci.click = (
            lambda description="", *a, **kw: f"agent.click({description!r})"
        )

        code = self.aci.feishu_type_message("hello", overwrite=False, enter=False)

        self.assertIn("agent.click(", code)
        self.assertIn("composer input", code)
        self.assertIn("_feishu_set_clipboard_text", code)
        self.assertIn("_feishu_ctrl_combo(0x56)", code)
        self.assertIn("FEISHU_TYPED_UNICODE", code)
        self.assertNotIn("pyautogui.hotkey('ctrl', 'v')", code)

    def test_feishu_type_uses_win32_clipboard_paste_for_chinese_text(self) -> None:
        code = self.aci.feishu_type("项目同步", overwrite=False, enter=False)

        compile(code, "<generated-feishu-type>", "exec")
        self.assertIn("_FEISHU_PASTE_TEXT = '项目同步'", code)
        self.assertIn("_feishu_set_clipboard_text", code)
        self.assertIn("_feishu_ctrl_combo(0x56)", code)
        self.assertIn("FEISHU_TYPED_UNICODE", code)
        self.assertNotIn("pyautogui.hotkey('ctrl', 'v')", code)

    def test_feishu_type_after_uia_click_pastes_only_when_click_succeeds(self) -> None:
        code = self.aci.feishu_type(
            "项目同步",
            "添加主题",
            overwrite=True,
            enter=True,
        )

        compile(code, "<generated-feishu-type-click>", "exec")
        self.assertIn("if clicked:", code)
        self.assertIn("_feishu_paste_text(_FEISHU_PASTE_TEXT", code)
        self.assertIn("_overwrite=True", code)
        self.assertIn("_enter=True", code)
        self.assertIn("_feishu_ctrl_combo(0x41)", code)
        self.assertIn("_feishu_tap_key(0x0D)", code)

    def test_click_send_button_uses_semantic_grounding(self) -> None:
        self.aci.click = (
            lambda description="", *a, **kw: f"agent.click({description!r})"
        )

        code = self.aci.feishu_click_send_button()

        self.assertIn("agent.click(", code)
        self.assertIn("send button", code)
        self.assertIn(
            "send button", str(self.aci.feishu_click_send_button.__doc__ or "")
        )

    def test_feishu_click_prepares_grounded_fallback_for_icon_description(self) -> None:
        self.aci.obs = {"screenshot": b"fake"}
        self.aci.generate_coords = lambda description, obs: [500, 600]
        self.aci.resize_coordinates = lambda coords: [960, 540]

        code = self.aci.feishu_click(
            "The smiley face emoji icon to the right of the message input box"
        )

        self.assertIn("FEISHU_UIA_CLICK_FALLBACK", code)
        self.assertIn("FEISHU_CLICK_COORDS:", code)
        self.assertIn(
            "FEISHU_CLICK_GROUNDED_FALLBACK_READY",
            "".join(self.trace_messages),
        )

    def test_feishu_click_keeps_plain_text_targets_uia_only(self) -> None:
        self.aci.obs = {"screenshot": b"fake"}
        self.aci.generate_coords = lambda description, obs: [500, 600]
        self.aci.resize_coordinates = lambda coords: [960, 540]

        code = self.aci.feishu_click("bot功能测试")

        self.assertNotIn("FEISHU_UIA_CLICK_FALLBACK", code)
        self.assertNotIn("FEISHU_CLICK_COORDS:", code)

    def test_worker_im_prompt_adds_static_prior_tool_strategy(self) -> None:
        prompt = self.aci.build_worker_system_prompt(
            "打开消息中的bot功能测试群聊，在消息发送框输入hello，并发送",
            "windows",
        )

        self.assertIn("First reason from the screenshot", prompt)
        self.assertIn("agent.feishu_type_message(...)", prompt)
        self.assertIn("icon-only controls", prompt)

    def test_worker_vc_prompt_adds_vc_helper_strategy(self) -> None:
        prompt = self.aci.build_worker_system_prompt(
            "发起视频会议并验证进入成功",
            "windows",
        )

        self.assertIn("Feishu VC Prior Tool Strategy", prompt)
        self.assertIn("agent.feishu_vc_click_start_card()", prompt)
        self.assertIn("agent.feishu_vc_click_start_button()", prompt)
        self.assertIn("agent.feishu_vc_type_meeting_id(...)", prompt)


if __name__ == "__main__":
    unittest.main()
