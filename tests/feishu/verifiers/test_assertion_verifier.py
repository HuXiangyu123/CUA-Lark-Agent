from pathlib import Path
import unittest

from gui_agents.feishu.detectors.base_state_detector import detect_base_state
from gui_agents.feishu.detectors.calendar_state_detector import detect_calendar_state
from gui_agents.feishu.detectors.docs_state_detector import detect_docs_state
from gui_agents.feishu.detectors.im_state_detector import detect_feishu_state
from gui_agents.feishu.detectors.vc_state_detector import detect_vc_state
from gui_agents.feishu.verifiers.assertion_verifier import AssertionVerifier


IM_FIXTURE_DIR = Path("tests/fixtures/im")
DOCS_FIXTURE_DIR = Path("tests/fixtures/docs")
BASE_FIXTURE_DIR = Path("tests/fixtures/base")
CALENDAR_FIXTURE_DIR = Path("tests/fixtures/calendar")
VC_FIXTURE_DIR = Path("tests/fixtures/vc")


class TestAssertionVerifier(unittest.TestCase):
    def setUp(self) -> None:
        self.verifier = AssertionVerifier()

    def _observation(self, filename: str) -> dict:
        return {"image_path": str(IM_FIXTURE_DIR / filename)}

    def _docs_observation(self, filename: str) -> dict:
        return {"image_path": str(DOCS_FIXTURE_DIR / filename)}

    def _base_observation(self, filename: str) -> dict:
        return {"image_path": str(BASE_FIXTURE_DIR / filename)}

    def _calendar_observation(self, filename: str) -> dict:
        return {"image_path": str(CALENDAR_FIXTURE_DIR / filename)}

    def _vc_observation(self, filename: str) -> dict:
        return {"image_path": str(VC_FIXTURE_DIR / filename)}

    def test_verifies_chat_title_match(self) -> None:
        observation = self._observation("im_chat_main_full.png")
        state = detect_feishu_state(observation)

        result = self.verifier.verify_assertion(
            "chat_title_matched",
            state,
            observation,
            expected={"chat_name": "bot功能测试"},
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["assertion"], "chat_title_matched")

    def test_verifies_message_input_contains_text(self) -> None:
        observation = self._observation("im_message_draft_visible.png")
        state = detect_feishu_state(observation)

        result = self.verifier.verify_assertion(
            "message_input_contains_text",
            state,
            observation,
            expected={"message_text": "测试文字"},
        )

        self.assertTrue(result["passed"])
        self.assertIn("draft_present=True", result["evidence"])

    def test_verifies_message_sent(self) -> None:
        observation = self._observation("im_message_sent_visible.png")
        state = detect_feishu_state(observation)

        result = self.verifier.verify_assertion(
            "message_sent",
            state,
            observation,
            expected={"message_text": "测试文字"},
        )

        self.assertTrue(result["passed"])
        self.assertIn("message_sent_visible=True", result["evidence"])

    def test_verifies_im_search_panel_ready(self) -> None:
        observation = self._observation("im_message_searchchat_visible.png")
        state = detect_feishu_state(observation)

        result = self.verifier.verify_assertion(
            "im_search_panel_ready", state, observation
        )

        self.assertTrue(result["passed"])
        self.assertIn("page_type=chat_search_panel", result["evidence"])

    def test_returns_structured_failure_for_mismatch(self) -> None:
        observation = self._observation("im_message_draft_visible.png")
        state = detect_feishu_state(observation)

        result = self.verifier.verify_assertion(
            "message_input_contains_text",
            state,
            observation,
            expected={"message_text": "错误文本"},
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["failure_type"], "verification")
        self.assertIn("mismatch", result["failure_reason"])

    def test_verify_step_wraps_step_id(self) -> None:
        observation = self._observation("im_message_sent_visible.png")
        state = detect_feishu_state(observation)

        result = self.verifier.verify_step(
            {
                "step_id": "step_3",
                "assertion": "message_sent",
                "payload": {"text": "测试文字"},
            },
            state,
            observation,
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["step_id"], "step_3")

    def test_message_input_verifier_supports_ocr_fallback(self) -> None:
        result = self.verifier.verify_assertion(
            "message_input_contains_text",
            {
                "page_type": "chat_main",
                "product": "im",
                "chat_name": "bot功能测试",
                "message_input_visible": True,
                "send_button_visible": True,
                "search_box_visible": False,
                "modal_type": None,
                "last_error_banner": None,
                "product_state": {},
            },
            {"ocr_text": "发送给 bot功能测试\n测试文字\n发送"},
            expected={"params": {"text": "测试文字"}},
        )

        self.assertTrue(result["passed"])
        self.assertIn("source=ocr_fallback", result["evidence"])

    def test_message_sent_verifier_supports_ocr_fallback(self) -> None:
        result = self.verifier.verify_assertion(
            "message_sent",
            {
                "page_type": "chat_main",
                "product": "im",
                "chat_name": "bot功能测试",
                "message_input_visible": True,
                "send_button_visible": True,
                "search_box_visible": False,
                "modal_type": None,
                "last_error_banner": None,
                "product_state": {},
            },
            {"ocr_text": "bot功能测试\n测试文字\n19:20"},
            expected={"params": {"text": "测试文字"}},
        )

        self.assertTrue(result["passed"])
        self.assertIn("source=ocr_fallback", result["evidence"])

    def test_verifies_docs_home_ready(self) -> None:
        observation = self._docs_observation("主页.png")
        state = detect_docs_state(observation)

        result = self.verifier.verify_assertion(
            "docs_home_ready",
            state,
            observation,
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["assertion"], "docs_home_ready")

    def test_verifies_base_home_ready(self) -> None:
        observation = self._base_observation("多维表格主页-不带弹窗.png")
        state = detect_base_state(observation)

        result = self.verifier.verify_assertion(
            "base_home_ready",
            state,
            observation,
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["assertion"], "base_home_ready")

    def test_verifies_base_editor_ready(self) -> None:
        observation = self._base_observation("新建多维表格后浏览器界面-带弹窗.png")
        state = detect_base_state(observation)

        result = self.verifier.verify_assertion(
            "base_editor_ready",
            state,
            observation,
        )

        self.assertTrue(result["passed"])
        self.assertIn("base_editor_ready=True", result["evidence"])

    def test_verifies_docs_editor_ready(self) -> None:
        observation = self._docs_observation("网页端文档.png")
        state = detect_docs_state(observation)

        result = self.verifier.verify_assertion(
            "doc_editor_ready",
            state,
            observation,
        )

        self.assertTrue(result["passed"])
        self.assertIn("editor_ready=True", result["evidence"])

    def test_verifies_doc_title_with_ocr_fallback(self) -> None:
        result = self.verifier.verify_assertion(
            "doc_title_contains_text",
            {
                "page_type": "docs_browser_editor",
                "product": "docs",
                "chat_name": None,
                "message_input_visible": False,
                "send_button_visible": False,
                "search_box_visible": False,
                "modal_type": None,
                "last_error_banner": None,
                "product_state": {},
            },
            {"ocr_text": "项目周报\n输入 / 快速插入内容"},
            expected={"params": {"text": "项目周报"}},
        )

        self.assertTrue(result["passed"])
        self.assertIn("source=ocr_fallback", result["evidence"])

    def test_verifies_doc_body_from_product_state(self) -> None:
        result = self.verifier.verify_assertion(
            "doc_body_contains_text",
            {
                "page_type": "docs_browser_editor",
                "product": "docs",
                "chat_name": None,
                "message_input_visible": False,
                "send_button_visible": False,
                "search_box_visible": False,
                "modal_type": None,
                "last_error_banner": None,
                "product_state": {"body_text": "本周完成联调"},
            },
            {},
            expected={"params": {"text": "本周完成联调"}},
        )

        self.assertTrue(result["passed"])
        self.assertIn("body_text=本周完成联调", result["evidence"])

    def test_verifies_docs_share_dialog_opened(self) -> None:
        observation = self._docs_observation("云文档编辑界面_最近编辑.png")
        state = detect_docs_state(observation)

        state["product_state"]["share_dialog_visible"] = True
        result = self.verifier.verify_assertion(
            "docs_share_dialog_opened", state, observation
        )

        self.assertTrue(result["passed"])
        self.assertIn("share_dialog_visible=True", result["evidence"])

    def test_verifies_docs_share_dialog_not_visible(self) -> None:
        observation = self._docs_observation("云文档编辑界面_最近编辑.png")
        state = detect_docs_state(observation)

        result = self.verifier.verify_assertion(
            "docs_share_dialog_opened", state, observation
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["failure_type"], "verification")

    def test_verifies_calendar_home_ready(self) -> None:
        observation = self._calendar_observation("calendar_home.png")
        state = detect_calendar_state(observation)

        result = self.verifier.verify_assertion(
            "calendar_home_ready", state, observation
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["assertion"], "calendar_home_ready")
        self.assertIn("page_type=calendar_home", result["evidence"])

    def test_verifies_calendar_event_modal_ready(self) -> None:
        observation = self._calendar_observation("calendar_create_event_modal.png")
        state = detect_calendar_state(observation)

        result = self.verifier.verify_assertion(
            "calendar_event_modal_ready", state, observation
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["assertion"], "calendar_event_modal_ready")
        self.assertIn("page_type=calendar_event_modal", result["evidence"])

    def test_verifies_calendar_quick_add_ready(self) -> None:
        observation = self._calendar_observation("calendar_quick_add_modal.png")
        state = detect_calendar_state(observation)

        result = self.verifier.verify_assertion(
            "calendar_quick_add_ready", state, observation
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["assertion"], "calendar_quick_add_ready")
        self.assertIn(
            "calendar_creation_method=time_slot_quick_add", result["evidence"]
        )

    def test_verifies_calendar_create_surface_for_either_creation_path(self) -> None:
        for filename, expected_method in (
            ("calendar_create_event_modal.png", "create_schedule_entry"),
            ("calendar_quick_add_modal.png", "time_slot_quick_add"),
        ):
            with self.subTest(filename=filename):
                observation = self._calendar_observation(filename)
                state = detect_calendar_state(observation)

                result = self.verifier.verify_assertion(
                    "calendar_create_surface_ready", state, observation
                )

                self.assertTrue(result["passed"])
                self.assertIn(
                    f"calendar_creation_method={expected_method}",
                    result["evidence"],
                )

    def test_verifies_calendar_home_not_ready_with_wrong_product(self) -> None:
        observation = self._vc_observation("会议主页面.png")
        state = detect_vc_state(observation)

        result = self.verifier.verify_assertion(
            "calendar_home_ready", state, observation
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["failure_type"], "verification")

    def test_verifies_vc_home_ready(self) -> None:
        observation = self._vc_observation("会议主页面.png")
        state = detect_vc_state(observation)

        result = self.verifier.verify_assertion("vc_home_ready", state, observation)

        self.assertTrue(result["passed"])
        self.assertEqual(result["assertion"], "vc_home_ready")

    def test_verifies_vc_meeting_active(self) -> None:
        observation = self._vc_observation("正在会议的页面.png")
        state = detect_vc_state(observation)

        result = self.verifier.verify_assertion("vc_meeting_active", state, observation)

        self.assertTrue(result["passed"])
        self.assertIn("page_type=vc_meeting_active", result["evidence"])

    def test_verifies_vc_joined_from_active_meeting(self) -> None:
        observation = self._vc_observation("正在会议的页面.png")
        state = detect_vc_state(observation)

        result = self.verifier.verify_assertion("vc_joined", state, observation)

        self.assertTrue(result["passed"])
        self.assertIn("joined=True", result["evidence"])

    def test_verifies_vc_invite_dialog_opened(self) -> None:
        observation = self._vc_observation("会议邀请点击后.png")
        state = detect_vc_state(observation)

        result = self.verifier.verify_assertion(
            "vc_invite_dialog_opened", state, observation
        )

        self.assertTrue(result["passed"])
        self.assertIn("page_type=vc_invite_dialog", result["evidence"])


if __name__ == "__main__":
    unittest.main()
