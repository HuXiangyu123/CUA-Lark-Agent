from pathlib import Path
import unittest

from gui_agents.feishu.detectors.calendar_state_detector import detect_calendar_state
from gui_agents.feishu.detectors.base_state_detector import detect_base_state
from gui_agents.feishu.detectors.docs_state_detector import detect_docs_state
from gui_agents.feishu.detectors.im_state_detector import detect_feishu_state
from gui_agents.feishu.detectors.vc_state_detector import detect_vc_state
from gui_agents.feishu.tooling.tool_router import (
    build_feishu_tool_guidance,
    route_feishu_tools,
)


IM_FIXTURE_DIR = Path("tests/fixtures/im")
SHELL_FIXTURE_DIR = Path("tests/fixtures/feishu_shell")
BASE_FIXTURE_DIR = Path("tests/fixtures/base")
CALENDAR_FIXTURE_DIR = Path("tests/fixtures/calendar")
DOCS_FIXTURE_DIR = Path("tests/fixtures/docs")
VC_FIXTURE_DIR = Path("tests/fixtures/vc")


class TestFeishuToolRouter(unittest.TestCase):
    def _im_observation(self, filename: str) -> dict:
        return {"image_path": str(IM_FIXTURE_DIR / filename)}

    def _shell_observation(self, filename: str) -> dict:
        return {"image_path": str(SHELL_FIXTURE_DIR / filename)}

    def _base_observation(self, filename: str) -> dict:
        return {"image_path": str(BASE_FIXTURE_DIR / filename)}

    def _calendar_observation(self, filename: str) -> dict:
        return {"image_path": str(CALENDAR_FIXTURE_DIR / filename)}

    def _docs_observation(self, filename: str) -> dict:
        return {"image_path": str(DOCS_FIXTURE_DIR / filename)}

    def _vc_observation(self, filename: str) -> dict:
        return {"image_path": str(VC_FIXTURE_DIR / filename)}

    def test_chat_main_prefers_composer_tools(self) -> None:
        observation = self._im_observation("im_chat_main_full.png")
        state = detect_feishu_state(observation)

        recommendation = route_feishu_tools(
            '在 "bot功能测试" 发送 hello world',
            observation,
            state=state,
        )

        self.assertEqual(recommendation.page_type, "chat_main")
        self.assertEqual(recommendation.next_step_focus, "message_composer")
        self.assertIn("feishu_type_message", recommendation.preferred_tools)
        self.assertIn("feishu_click_message_input", recommendation.preferred_tools)
        self.assertIn("hotkey", recommendation.preferred_tools)
        self.assertIn("click", recommendation.enabled_tools)
        self.assertEqual(recommendation.target_chat_name, "bot功能测试")

    def test_shell_search_prefers_text_driven_search(self) -> None:
        observation = self._shell_observation("global_search_results.png")
        state = detect_feishu_state(observation)

        recommendation = route_feishu_tools(
            "打开消息中的bot功能测试群聊并搜索需求",
            observation,
            state=state,
        )

        self.assertEqual(recommendation.page_type, "shell_search")
        self.assertEqual(recommendation.next_step_focus, "global_search_entry")
        self.assertIn("feishu_type", recommendation.preferred_tools)
        self.assertIn("feishu_click", recommendation.preferred_tools)
        self.assertIn("click", recommendation.discouraged_tools)

    def test_search_panel_prefers_panel_local_actions(self) -> None:
        observation = self._im_observation("im_message_searchresult_visible.png")
        state = detect_feishu_state(observation)

        recommendation = route_feishu_tools(
            "搜索需求并打开对应消息结果",
            observation,
            state=state,
        )

        self.assertEqual(recommendation.page_type, "chat_search_panel")
        self.assertEqual(
            recommendation.next_step_focus, "conversation_search_entry_or_result"
        )
        self.assertIn("feishu_click", recommendation.preferred_tools)
        self.assertIn("feishu_type", recommendation.preferred_tools)
        self.assertIn("type", recommendation.discouraged_tools)

    def test_guidance_mentions_emoji_fallback_on_chat_main(self) -> None:
        observation = self._im_observation("im_message_draft_visible.png")
        recommendation = route_feishu_tools(
            "在当前群聊点击表情并发送一个随机表情",
            observation,
        )
        guidance = build_feishu_tool_guidance(
            "在当前群聊点击表情并发送一个随机表情",
            observation,
        )

        self.assertEqual(recommendation.next_step_focus, "emoji_icon_or_picker")
        self.assertEqual(recommendation.preferred_tools[1], "click")
        self.assertIn("feishu_click", recommendation.discouraged_tools)
        self.assertIn("Preferred tools:", guidance)
        self.assertIn("click", guidance)
        self.assertIn("recovery guidance", guidance)
        self.assertNotIn("source of truth", guidance)
        self.assertIn("agent.click(...)", guidance)

    def test_full_send_then_emoji_instruction_stays_on_message_composer_first(
        self,
    ) -> None:
        observation = self._im_observation("im_chat_main_full.png")
        recommendation = route_feishu_tools(
            "打开消息中的bot功能测试群聊，在消息发送框输入hello，并且点击右侧表情图标随机选择一个表情并发送",
            observation,
        )

        self.assertEqual(recommendation.page_type, "chat_main")
        self.assertEqual(recommendation.next_step_focus, "message_composer")
        self.assertIn("feishu_type_message", recommendation.preferred_tools)
        self.assertIn("feishu_click_message_input", recommendation.preferred_tools)
        self.assertIn("Do not go to emoji first", " ".join(recommendation.hints))

    def test_base_surface_prefers_grounded_actions_over_fixed_feishu_uia(self) -> None:
        observation = self._base_observation("点击新建后.png")
        state = detect_base_state(observation)

        recommendation = route_feishu_tools(
            "新建一个多维表格并打开空白表",
            observation,
            state=state,
        )

        self.assertEqual(recommendation.product, "base")
        self.assertEqual(
            recommendation.next_step_focus, "base_browser_or_desktop_surface"
        )
        self.assertIn("click", recommendation.preferred_tools)
        self.assertIn("type", recommendation.preferred_tools)
        self.assertIn("feishu_click", recommendation.discouraged_tools)
        self.assertIn("feishu_type", recommendation.discouraged_tools)

    def test_calendar_surface_stays_agent_guided_not_fixed_workflow(self) -> None:
        observation = self._calendar_observation("点击创建日程后.png")
        state = detect_calendar_state(observation)

        recommendation = route_feishu_tools(
            "打开日历并创建一个会议日程",
            observation,
            state=state,
        )
        guidance = build_feishu_tool_guidance(
            "打开日历并创建一个会议日程",
            observation,
            state=state,
        )

        self.assertEqual(recommendation.product, "calendar")
        self.assertEqual(recommendation.page_type, "calendar_event_modal")
        self.assertEqual(
            recommendation.next_step_focus, "calendar_event_modal_controls"
        )
        self.assertIn("feishu_click", recommendation.preferred_tools)
        self.assertIn("feishu_type", recommendation.preferred_tools)
        self.assertIn(
            "Calendar should be handled as an agent-guided state surface",
            " ".join(recommendation.rationale),
        )
        self.assertIn("Do not rely on precomputed coordinates", guidance)
        self.assertIn("visible title field", guidance)

    def test_docs_home_routes_to_docs_specific_guidance_without_state(self) -> None:
        observation = self._docs_observation("主页.png")

        recommendation = route_feishu_tools(
            "打开云文档页面，点击新建按钮，创建空白文档",
            observation,
        )

        self.assertEqual(recommendation.product, "docs")
        self.assertEqual(recommendation.page_type, "docs_home")
        self.assertEqual(recommendation.next_step_focus, "docs_home_new_entry")
        self.assertIn("feishu_doc_click", recommendation.preferred_tools)
        self.assertIn("feishu_doc_type", recommendation.enabled_tools)
        self.assertIn(
            "agent-guided visible-state navigation",
            " ".join(recommendation.rationale),
        )

    def test_docs_editor_skips_earlier_create_menu_steps(self) -> None:
        observation = self._docs_observation("网页端文档.png")
        state = detect_docs_state(observation)

        recommendation = route_feishu_tools(
            "新建一个云文档，标题为项目周报",
            observation,
            state=state,
        )
        guidance = build_feishu_tool_guidance(
            "新建一个云文档，标题为项目周报",
            observation,
            state=state,
        )

        self.assertEqual(recommendation.product, "docs")
        self.assertEqual(recommendation.page_type, "docs_browser_editor")
        self.assertEqual(recommendation.next_step_focus, "docs_editor_title_or_body")
        self.assertIn("feishu_doc_type", recommendation.preferred_tools)
        self.assertIn("skip earlier create-menu steps", " ".join(recommendation.hints))
        self.assertIn("not a fixed create-document workflow", guidance)

    def test_vc_home_start_is_agent_guided_not_fixed_workflow(self) -> None:
        observation = self._vc_observation("会议主页面.png")
        state = detect_vc_state(observation)

        recommendation = route_feishu_tools(
            "发起视频会议并验证入会成功",
            observation,
            state=state,
        )
        guidance = build_feishu_tool_guidance(
            "发起视频会议并验证入会成功",
            observation,
            state=state,
        )

        self.assertEqual(recommendation.product, "vc")
        self.assertEqual(recommendation.next_step_focus, "start_meeting_card")
        self.assertIn("feishu_vc_click_start_card", recommendation.preferred_tools)
        self.assertIn("feishu_vc_click_start_button", recommendation.preferred_tools)
        self.assertIn(
            "fixed workflow stage machine", " ".join(recommendation.rationale)
        )
        self.assertIn("feishu_vc_click_start_card", guidance)

    def test_vc_join_preview_guides_meeting_id_input(self) -> None:
        observation = self._vc_observation("选择加入会议.png")
        state = detect_vc_state(observation)

        recommendation = route_feishu_tools(
            "加入会议，会议 ID 为 123456789",
            observation,
            state=state,
        )

        self.assertEqual(recommendation.page_type, "vc_join_preview")
        self.assertEqual(
            recommendation.next_step_focus, "meeting_id_input_or_join_button"
        )
        self.assertIn("feishu_vc_type_meeting_id", recommendation.preferred_tools)
        self.assertIn("feishu_vc_click_join_button", recommendation.preferred_tools)
        self.assertIn("meeting-ID input", " ".join(recommendation.hints))

    def test_vc_active_meeting_guides_invite_control(self) -> None:
        observation = self._vc_observation("正在会议的页面.png")
        state = detect_vc_state(observation)

        recommendation = route_feishu_tools(
            "在当前视频会议中邀请 bot功能测试",
            observation,
            state=state,
        )

        self.assertEqual(recommendation.page_type, "vc_meeting_active")
        self.assertEqual(recommendation.next_step_focus, "meeting_invite_control")
        self.assertIn("feishu_vc_click_invite_button", recommendation.preferred_tools)
        self.assertIn("invite toolbar control", " ".join(recommendation.hints))

    def test_vc_invite_popover_prefers_invite_entry_helper(self) -> None:
        observation = self._vc_observation("会议进行邀请.png")
        state = detect_vc_state(observation)

        recommendation = route_feishu_tools(
            "在当前视频会议中邀请 bot功能测试",
            observation,
            state=state,
        )

        self.assertEqual(recommendation.page_type, "vc_meeting_active")
        self.assertEqual(recommendation.next_step_focus, "invite_popover_entry")
        self.assertEqual(state["modal_type"], "vc_invite_popover")
        self.assertIn("feishu_vc_click_invite_entry", recommendation.preferred_tools)

    def test_anomaly_guidance_takes_recovery_focus_without_fixed_workflow(self) -> None:
        observation = {"ocr_text": "飞书云文档 权限不足 申请权限"}
        state = detect_docs_state(observation)

        recommendation = route_feishu_tools(
            "打开云文档并创建项目周报",
            observation,
            state=state,
        )
        guidance = build_feishu_tool_guidance(
            "打开云文档并创建项目周报",
            observation,
            state=state,
        )

        self.assertEqual(
            recommendation.next_step_focus, "request_permission_or_report_blocker"
        )
        self.assertIn("wait", recommendation.preferred_tools)
        self.assertIn("click", recommendation.enabled_tools)
        self.assertIn("permission_denied_visible", recommendation.state_summary)
        self.assertIn("recovery_hint=request_permission", recommendation.state_summary)
        self.assertIn("Anomaly detected", guidance)
        self.assertIn("Report the permission blocker", guidance)
        self.assertNotIn("WorkflowPlan", guidance)


if __name__ == "__main__":
    unittest.main()
