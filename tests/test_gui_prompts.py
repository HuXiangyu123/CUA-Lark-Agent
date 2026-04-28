import unittest

from agent.gui.prompts import build_gui_user_prompt


class GuiPromptTest(unittest.TestCase):
    def test_emoji_goal_adds_toolbar_hints(self):
        prompt = build_gui_user_prompt(
            goal="点击笑脸图标，选择一个表情发送",
            step_index=1,
            max_steps=6,
            screenshot_width=2322,
            screenshot_height=1272,
            app_name="Feishu",
            window_origin_x=0,
            window_origin_y=38,
            history_summary="(no previous steps)",
            run_state_summary="- Submit actions this run: 0",
        )
        self.assertIn("`Aa`, smiley emoji, `@`, scissors, plus, expand, send", prompt)
        self.assertIn("immediately to the right of `Aa`", prompt)

    def test_repeated_click_history_adds_reassessment_hint(self):
        prompt = build_gui_user_prompt(
            goal="选择一个emoji发送",
            step_index=3,
            max_steps=6,
            screenshot_width=2322,
            screenshot_height=1272,
            app_name="Feishu",
            window_origin_x=0,
            window_origin_y=38,
            history_summary="Step 1: action=click\nStep 2: action=click",
            run_state_summary="- Submit actions this run: 0",
        )
        self.assertIn("do not click the same icon at nearly the same spot again", prompt)

    def test_send_goal_warns_old_messages_do_not_count(self):
        prompt = build_gui_user_prompt(
            goal='请发送消息 "test"',
            step_index=2,
            max_steps=6,
            screenshot_width=2322,
            screenshot_height=1272,
            app_name="Feishu",
            window_origin_x=0,
            window_origin_y=38,
            history_summary="Step 1: action=type text='test'",
            run_state_summary="- Submit actions this run: 0",
        )
        self.assertIn("A matching old message may already be visible", prompt)
        self.assertIn("Do not return done until this run has executed a real send/submit action", prompt)

    def test_visual_mismatch_adds_retype_hint(self):
        prompt = build_gui_user_prompt(
            goal='请发送消息 "genshin start"',
            step_index=3,
            max_steps=6,
            screenshot_width=2322,
            screenshot_height=1272,
            app_name="Feishu",
            window_origin_x=0,
            window_origin_y=38,
            history_summary="Step 1: action=click\nStep 2: action=type text='genshin start'",
            run_state_summary=(
                "- Submit actions this run: 0\n"
                "- Last visual check: composer text mismatches target\n"
                "- Send visually confirmed: false"
            ),
        )
        self.assertIn("Do not submit yet", prompt)
        self.assertIn("select all in the composer", prompt)


if __name__ == "__main__":
    unittest.main()
