import unittest

from gui_agents.feishu.testcases.nl_parser import parse_instruction


class TestNLParser(unittest.TestCase):
    def test_parse_send_message_instruction(self) -> None:
        testcase = parse_instruction('在"测试群"发送"Hello World"并验证发送成功')

        self.assertEqual(testcase["product"], "im")
        self.assertEqual(testcase["steps"][0]["action"], "open_chat")
        self.assertEqual(testcase["steps"][0]["target"], "测试群")
        self.assertEqual(
            testcase["steps"][1]["payload"],
            {"text": "Hello World"},
        )
        self.assertEqual(testcase["steps"][2]["action"], "send_message")
        self.assertIn("message_sent", testcase["assertions"])
        self.assertEqual(
            testcase["artifacts"]["runtime_contract"],
            "semantic_validation_only",
        )
        self.assertEqual(testcase["artifacts"]["active_executor"], "feishu_agent")

    def test_parse_launcher_style_open_chat_and_input_instruction(self) -> None:
        testcase = parse_instruction(
            "打开bot功能测试群聊，在消息发送框输入hello，并且发送"
        )

        self.assertEqual(testcase["steps"][0]["target"], "bot功能测试")
        self.assertEqual(testcase["steps"][1]["payload"], {"text": "hello"})

    def test_rejects_unsupported_emoji_instruction(self) -> None:
        with self.assertRaisesRegex(ValueError, "supports text send_message only"):
            parse_instruction(
                "打开消息中的bot功能测试群聊，在消息发送框输入hello，并且点击表情图标随机选择一个表情并发送"
            )

    def test_vc_parses_as_guidance_only_testcase(self) -> None:
        testcase = parse_instruction("发起视频会议并验证入会成功")

        self.assertEqual(testcase["product"], "vc")
        self.assertEqual(testcase["steps"], [])
        self.assertTrue(testcase["artifacts"]["semantic_guidance_only"])
        self.assertEqual(testcase["artifacts"]["intent"], "start_video_meeting")

    def test_rejects_instruction_without_clear_chat_or_message(self) -> None:
        with self.assertRaisesRegex(ValueError, "unable to extract chat_name"):
            parse_instruction("帮我处理一下飞书消息")

    def test_parse_empty_instruction_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "instruction cannot be empty"):
            parse_instruction("   ")

    def test_parse_docs_create_doc_instruction(self) -> None:
        testcase = parse_instruction(
            "在飞书云文档中创建一个新文档，输入标题“2026年Q2项目进展”，正文“本周完成联调”。"
        )

        self.assertEqual(testcase["product"], "docs")
        self.assertEqual(testcase["steps"][0]["action"], "open_docs_home")
        self.assertEqual(testcase["steps"][4]["action"], "type_doc_title")
        self.assertEqual(
            testcase["steps"][4]["payload"],
            {"text": "2026年Q2项目进展"},
        )
        self.assertEqual(testcase["steps"][5]["action"], "type_doc_body")
        self.assertEqual(testcase["steps"][5]["payload"], {"text": "本周完成联调"})
        self.assertIn("doc_title_contains_text", testcase["assertions"])
        self.assertIn("doc_body_contains_text", testcase["assertions"])
        self.assertEqual(
            testcase["artifacts"]["ordered_steps_role"],
            "acceptance_scaffold_not_workflow",
        )

    def test_parse_docs_title_only_instruction(self) -> None:
        testcase = parse_instruction("新建一个云文档，标题为“项目周报”。")

        self.assertEqual(testcase["product"], "docs")
        self.assertEqual(len(testcase["steps"]), 5)
        self.assertEqual(testcase["steps"][-1]["action"], "type_doc_title")
        self.assertEqual(testcase["steps"][-1]["payload"], {"text": "项目周报"})

    def test_base_parses_as_guidance_only_testcase(self) -> None:
        testcase = parse_instruction("新建一个多维表格")

        self.assertEqual(testcase["product"], "base")
        self.assertEqual(testcase["steps"], [])
        self.assertTrue(testcase["artifacts"]["semantic_guidance_only"])
        self.assertEqual(testcase["artifacts"]["intent"], "base_semantic_task")

    def test_base_guidance_preserves_title_hint(self) -> None:
        testcase = parse_instruction("新建一个多维表格，标题为“销售跟进表”")

        self.assertEqual(testcase["product"], "base")
        self.assertEqual(testcase["steps"], [])
        self.assertEqual(testcase["artifacts"]["params"]["title_hint"], "销售跟进表")

    def test_calendar_create_event_parses_as_guidance_testcase(self) -> None:
        testcase = parse_instruction(
            "打开日历，创建明天下午 2 点的日程，标题为“项目同步”，并邀请张三"
        )

        self.assertEqual(testcase["product"], "calendar")
        self.assertEqual(testcase["steps"], [])
        self.assertTrue(testcase["artifacts"]["semantic_guidance_only"])
        self.assertEqual(testcase["artifacts"]["intent"], "create_event")
        self.assertIn("calendar_home_ready", testcase["assertions"])
        self.assertIn("calendar_create_surface_ready", testcase["assertions"])
        self.assertEqual(testcase["artifacts"]["params"]["event_title"], "项目同步")
        self.assertEqual(testcase["artifacts"]["params"]["attendee"], "张三")

    def test_calendar_view_today_parses_as_guidance_testcase(self) -> None:
        testcase = parse_instruction(
            "打开日历主页，查看今天的日程安排并确认日历页面已打开"
        )

        self.assertEqual(testcase["product"], "calendar")
        self.assertEqual(testcase["steps"], [])
        self.assertEqual(testcase["artifacts"]["intent"], "view_today")
        self.assertIn("calendar_home_ready", testcase["assertions"])


if __name__ == "__main__":
    unittest.main()
