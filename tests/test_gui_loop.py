import json
import unittest

from pathlib import Path

from agent.gui.capture import ScreenshotArtifact
from agent.gui.loop import (
    _apply_decision_state,
    _apply_execution_state,
    _apply_visual_state,
    _build_initial_run_state,
    _classify_goal_kind,
    _done_gate_error,
    _extract_target_message,
    _submit_gate_error,
    _looks_like_emoji_goal,
    GuiMessageVisualState,
    GuiRunner,
    _maybe_apply_feishu_emoji_heuristic,
    _normalize_decision_payload,
)
from agent.gui.schema import GuiDecision


class GuiLoopTest(unittest.TestCase):
    def test_normalize_action_style_payload_from_status(self):
        payload = {
            "status": "click",
            "target": "emoji button",
            "x": 100,
            "y": 200,
        }
        normalized = _normalize_decision_payload(payload)
        self.assertEqual(normalized["status"], "continue")
        self.assertEqual(normalized["action"]["type"], "click")
        self.assertEqual(normalized["action"]["x"], 100)
        self.assertEqual(normalized["action"]["y"], 200)

    def test_normalize_action_style_payload_from_type(self):
        payload = {
            "type": "hotkey",
            "keys": ["enter"],
            "target": "focused chat composer",
        }
        normalized = _normalize_decision_payload(payload)
        self.assertEqual(normalized["status"], "continue")
        self.assertEqual(normalized["action"]["type"], "hotkey")
        self.assertEqual(normalized["action"]["keys"], ["enter"])

    def test_leave_valid_decision_payload_unchanged(self):
        payload = {
            "status": "done",
            "stage": "complete",
            "current_state": "message sent",
            "progress_assessment": "goal completed",
            "previous_step_ok": True,
            "success_criteria": "message is visible in chat",
            "completion_evidence": "typed and submitted during this run",
            "done_reason": "Message was sent successfully.",
        }
        normalized = _normalize_decision_payload(payload)
        self.assertEqual(normalized, payload)

    def test_extract_target_message_from_quotes(self):
        self.assertEqual(_extract_target_message('请发送消息 “hello-world”'), "hello-world")
        self.assertEqual(_extract_target_message('send message "test" in current chat'), "test")

    def test_quoted_non_send_goal_becomes_open_chat_not_send_message(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('点击标题为 "bot功能测试" 的群聊', observation)
        self.assertEqual(run_state.goal_kind, "open_chat")
        self.assertEqual(run_state.target_message, "")

    def test_detect_emoji_goal_keywords(self):
        self.assertTrue(_looks_like_emoji_goal("点击笑脸图标发送一个表情"))
        self.assertTrue(_looks_like_emoji_goal("send an emoji in the current chat"))
        self.assertFalse(_looks_like_emoji_goal("在当前聊天窗口发送消息 hello-world"))

    def test_classify_open_calendar_and_create_event_goals(self):
        self.assertEqual(_classify_goal_kind("打开 Calendar 日历"), "open_calendar")
        self.assertEqual(
            _classify_goal_kind("打开calendar 日历，确定今天是什么时间，并点击对应时间节点创建event"),
            "create_calendar_event",
        )

    def test_done_gate_requires_open_calendar_view(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state("打开 Calendar 日历", observation)
        self.assertEqual(run_state.goal_kind, "open_calendar")
        self.assertFalse(run_state.done_gate_ready)
        self.assertIn("Calendar module", run_state.done_gate_reason)

        calendar_state = GuiMessageVisualState(
            primary_view="calendar_week_view",
            selected_sidebar_item="Calendar",
            calendar_visible=True,
            evidence="Calendar week view is visible.",
        )
        _apply_visual_state(run_state, calendar_state)
        self.assertFalse(run_state.done_gate_ready)
        _apply_visual_state(run_state, calendar_state)
        self.assertTrue(run_state.done_gate_ready)

    def test_done_gate_requires_full_calendar_event_creation_flow(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state(
            '打开calendar 日历并在今天 6:30 PM 点击对应时间节点，创建标题为 "test" 的event并保存',
            observation,
        )
        self.assertEqual(run_state.goal_kind, "create_calendar_event")
        self.assertEqual(run_state.calendar_event_title_target, "test")
        self.assertEqual(run_state.calendar_target_time_hint.lower(), "6:30 pm")

        calendar_state = GuiMessageVisualState(
            primary_view="calendar_week_view",
            selected_sidebar_item="Calendar",
            calendar_visible=True,
            calendar_today_highlighted=True,
            calendar_today_label="27",
            evidence="Calendar week view is visible and today 27 is highlighted in blue.",
        )
        _apply_visual_state(run_state, calendar_state)
        self.assertIn("time slot", run_state.done_gate_reason)

        slot_click = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "calendar week view open",
                "progress_assessment": "click requested time slot",
                "previous_step_ok": True,
                "success_criteria": "event editor opens at requested time",
                "action": {
                    "type": "click",
                    "target": "today column empty time slot at 6:30 PM in calendar grid",
                    "x": 100,
                    "y": 200,
                },
            }
        )
        _apply_execution_state(run_state, slot_click, type("Result", (), {"ok": True})())

        editor_state = GuiMessageVisualState(
            primary_view="calendar_event_editor",
            selected_sidebar_item="Calendar",
            calendar_visible=True,
            calendar_today_highlighted=True,
            calendar_today_label="27",
            calendar_event_editor_visible=True,
            calendar_event_time_range="Apr 27, 2026 6:30 PM - 7:00 PM",
            calendar_save_button_visible=True,
            evidence="A new calendar event editor is open for Apr 27, 2026 6:30 PM - 7:00 PM.",
        )
        _apply_visual_state(run_state, editor_state)
        self.assertIn("title", run_state.done_gate_reason)

        type_title = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "event editor open",
                "progress_assessment": "type requested title",
                "previous_step_ok": True,
                "success_criteria": "title test is visible in Add title field",
                "action": {"type": "type", "target": "event title field", "text": "test"},
            }
        )
        _apply_execution_state(run_state, type_title, type("Result", (), {"ok": True})())
        titled_editor_state = GuiMessageVisualState(
            primary_view="calendar_event_editor",
            selected_sidebar_item="Calendar",
            calendar_visible=True,
            calendar_today_highlighted=True,
            calendar_today_label="27",
            calendar_event_editor_visible=True,
            calendar_event_editor_title_text="test",
            calendar_event_time_range="Apr 27, 2026 6:30 PM - 7:00 PM",
            calendar_save_button_visible=True,
            evidence="The event editor shows title test and the requested 6:30 PM to 7:00 PM time range.",
        )
        _apply_visual_state(run_state, titled_editor_state)
        self.assertIn("Save", run_state.done_gate_reason)

        save_decision = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "submit",
                "current_state": "event editor ready",
                "progress_assessment": "save event",
                "previous_step_ok": True,
                "success_criteria": "editor closes and event appears in grid",
                "action": {"type": "click", "target": "Save button in calendar event editor", "x": 100, "y": 200},
            }
        )
        _apply_execution_state(run_state, save_decision, type("Result", (), {"ok": True})())
        saved_state = GuiMessageVisualState(
            primary_view="calendar_week_view",
            selected_sidebar_item="Calendar",
            calendar_visible=True,
            calendar_today_highlighted=True,
            calendar_today_label="27",
            calendar_saved_event_visible=True,
            calendar_saved_event_title="test",
            evidence="The saved calendar event test is visible in the Apr 27 6:30 PM slot.",
        )
        _apply_visual_state(run_state, saved_state)
        self.assertFalse(run_state.done_gate_ready)
        _apply_visual_state(run_state, saved_state)
        self.assertTrue(run_state.done_gate_ready)

    def test_done_gate_requires_target_chat_window(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('打开群聊 "bot功能测试"', observation)
        self.assertEqual(run_state.goal_kind, "open_chat")

        list_state = GuiMessageVisualState(
            primary_view="messenger_list",
            chat_title="bot功能测试",
            evidence="The target chat row is selected in the Messenger list.",
        )
        _apply_visual_state(run_state, list_state)
        self.assertIn("not visibly open yet", run_state.done_gate_reason)

        chat_state = GuiMessageVisualState(
            primary_view="chat_window",
            chat_title="bot功能测试",
            composer_visible=True,
            evidence="The bot功能测试 conversation window is open with the composer visible.",
        )
        _apply_visual_state(run_state, chat_state)
        self.assertFalse(run_state.done_gate_ready)
        _apply_visual_state(run_state, chat_state)
        self.assertTrue(run_state.done_gate_ready)

    def test_done_gate_rejects_old_visible_message_without_submit(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "test"', observation)
        decision = GuiDecision.from_dict(
            {
                "status": "done",
                "stage": "complete",
                "current_state": "chat shows test",
                "progress_assessment": "looks done",
                "previous_step_ok": True,
                "success_criteria": "",
                "completion_evidence": "visible test bubble",
                "done_reason": "message already visible",
            }
        )
        _apply_decision_state(run_state, decision)
        self.assertIn("send/submit action", _done_gate_error(decision, run_state))

    def test_done_gate_allows_message_after_type_and_submit(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "test"', observation)
        compose = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "composer focused",
                "progress_assessment": "ready to type",
                "previous_step_ok": True,
                "success_criteria": "test is typed",
                "completion_evidence": "",
                "action": {"type": "type", "target": "composer", "text": "test"},
            }
        )
        submit = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "submit",
                "current_state": "text is typed",
                "progress_assessment": "submit now",
                "previous_step_ok": True,
                "success_criteria": "message is sent",
                "completion_evidence": "",
                "action": {"type": "hotkey", "target": "submit composer", "keys": ["enter"]},
            }
        )
        _apply_decision_state(run_state, compose)
        _apply_execution_state(run_state, compose, type("Result", (), {"ok": True})())
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="test",
                composer_visible=True,
                composer_exact_match=True,
                composer_empty=False,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer exactly matches target.",
            ),
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="test",
                composer_visible=True,
                composer_exact_match=True,
                composer_empty=False,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer exactly matches target.",
            ),
        )
        _apply_decision_state(run_state, submit)
        _apply_execution_state(run_state, submit, type("Result", (), {"ok": True})())
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="",
                composer_exact_match=False,
                composer_empty=True,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer cleared after submit.",
            ),
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="",
                composer_exact_match=False,
                composer_empty=True,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer cleared after submit.",
            ),
        )

        done = GuiDecision.from_dict(
            {
                "status": "done",
                "stage": "complete",
                "current_state": "message sent",
                "progress_assessment": "done",
                "previous_step_ok": True,
                "success_criteria": "",
                "completion_evidence": "typed and submitted during this run",
                "done_reason": "Message was sent successfully.",
            }
        )
        _apply_decision_state(run_state, done)
        self.assertIsNone(_done_gate_error(done, run_state))

    def test_submit_gate_rejects_partial_visible_composer_text(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "genshin start"', observation)
        _apply_execution_state(
            run_state,
            GuiDecision.from_dict(
                {
                    "status": "continue",
                    "stage": "compose",
                    "current_state": "composer focused",
                    "progress_assessment": "ready to type",
                    "previous_step_ok": True,
                    "success_criteria": "target text typed",
                    "completion_evidence": "",
                    "action": {"type": "type", "target": "composer", "text": "genshin start"},
                }
            ),
            type("Result", (), {"ok": True})(),
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="enshin start",
                composer_exact_match=False,
                composer_empty=False,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer shows partial text enshin start.",
            ),
        )
        submit = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "submit",
                "current_state": "partial text visible",
                "progress_assessment": "submit now",
                "previous_step_ok": True,
                "success_criteria": "message is sent",
                "completion_evidence": "",
                "action": {"type": "hotkey", "target": "submit composer", "keys": ["enter"]},
            }
        )
        error = _submit_gate_error(submit, run_state)
        self.assertIn("enshin start", error)

    def test_submit_gate_rejects_empty_composer(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "hello-world"', observation)
        _apply_execution_state(
            run_state,
            GuiDecision.from_dict(
                {
                    "status": "continue",
                    "stage": "compose",
                    "current_state": "composer focused",
                    "progress_assessment": "typed",
                    "previous_step_ok": True,
                    "success_criteria": "target text typed",
                    "completion_evidence": "",
                    "action": {"type": "type", "target": "composer", "text": "hello-world"},
                }
            ),
            type("Result", (), {"ok": True})(),
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="",
                composer_exact_match=False,
                composer_empty=True,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer is empty and only shows placeholder text.",
            ),
        )
        submit = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "submit",
                "current_state": "composer looks empty",
                "progress_assessment": "submit now",
                "previous_step_ok": True,
                "success_criteria": "message is sent",
                "completion_evidence": "",
                "action": {"type": "hotkey", "target": "submit composer", "keys": ["enter"]},
            }
        )
        error = _submit_gate_error(submit, run_state)
        self.assertIn("does not visibly contain", error)

    def test_baseline_visible_message_does_not_mark_send_confirmed(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "hello-world"', observation)
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="",
                composer_visible=True,
                composer_exact_match=True,
                composer_empty=True,
                composer_placeholder="Message bot功能测试",
                sent_message_visible=True,
                sent_message_exact_match=True,
                latest_visible_message="hello-world",
                evidence="An old hello-world bubble is visible but the composer is empty.",
            ),
        )
        self.assertFalse(run_state.target_message_visually_verified)
        self.assertFalse(run_state.send_visually_confirmed)
        self.assertTrue(run_state.baseline_sent_message_exact_match)

    def test_done_gate_requires_visual_send_confirmation(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "genshin start"', observation)
        compose = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "composer focused",
                "progress_assessment": "ready to type",
                "previous_step_ok": True,
                "success_criteria": "target text typed",
                "completion_evidence": "",
                "action": {"type": "type", "target": "composer", "text": "genshin start"},
            }
        )
        submit = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "submit",
                "current_state": "text typed",
                "progress_assessment": "submit now",
                "previous_step_ok": True,
                "success_criteria": "message sent",
                "completion_evidence": "",
                "action": {"type": "hotkey", "target": "submit composer", "keys": ["enter"]},
            }
        )
        _apply_decision_state(run_state, compose)
        _apply_execution_state(run_state, compose, type("Result", (), {"ok": True})())
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="genshin start",
                composer_visible=True,
                composer_exact_match=True,
                composer_empty=False,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer exactly matches target.",
            ),
        )
        _apply_decision_state(run_state, submit)
        _apply_execution_state(run_state, submit, type("Result", (), {"ok": True})())

        done = GuiDecision.from_dict(
            {
                "status": "done",
                "stage": "complete",
                "current_state": "history says submit happened",
                "progress_assessment": "done",
                "previous_step_ok": True,
                "success_criteria": "",
                "completion_evidence": "typed and submitted during this run",
                "done_reason": "done",
            }
        )
        self.assertIn("visually confirmed", _done_gate_error(done, run_state))

    def test_done_gate_allows_cleared_composer_after_verified_submit(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "genshin start"', observation)
        compose = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "composer focused",
                "progress_assessment": "ready to type",
                "previous_step_ok": True,
                "success_criteria": "target text typed",
                "completion_evidence": "",
                "action": {"type": "type", "target": "composer", "text": "genshin start"},
            }
        )
        _apply_decision_state(run_state, compose)
        _apply_execution_state(run_state, compose, type("Result", (), {"ok": True})())
        for decision in (
            GuiDecision.from_dict(
                {
                    "status": "continue",
                    "stage": "submit",
                    "current_state": "text typed",
                    "progress_assessment": "submit now",
                    "previous_step_ok": True,
                    "success_criteria": "message sent",
                    "completion_evidence": "",
                    "action": {"type": "hotkey", "target": "submit composer", "keys": ["enter"]},
                }
            ),
        ):
            _apply_visual_state(
                run_state,
                GuiMessageVisualState(
                    composer_text="genshin start",
                    composer_visible=True,
                    composer_exact_match=True,
                    composer_empty=False,
                    sent_message_visible=False,
                    sent_message_exact_match=False,
                    evidence="Composer exactly matches target.",
                ),
            )
            _apply_visual_state(
                run_state,
                GuiMessageVisualState(
                    composer_text="genshin start",
                    composer_visible=True,
                    composer_exact_match=True,
                    composer_empty=False,
                    sent_message_visible=False,
                    sent_message_exact_match=False,
                    evidence="Composer exactly matches target.",
                ),
            )
            _apply_decision_state(run_state, decision)
            _apply_execution_state(run_state, decision, type("Result", (), {"ok": True})())

        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="",
                composer_exact_match=False,
                composer_empty=True,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer is now empty after submit.",
            ),
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="",
                composer_exact_match=False,
                composer_empty=True,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer is now empty after submit.",
            ),
        )
        done = GuiDecision.from_dict(
            {
                "status": "done",
                "stage": "complete",
                "current_state": "message sent",
                "progress_assessment": "done",
                "previous_step_ok": True,
                "success_criteria": "",
                "completion_evidence": "composer cleared after submit",
                "done_reason": "done",
            }
        )
        self.assertIsNone(_done_gate_error(done, run_state))

    def test_submit_gate_requires_stable_exact_match_observation(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "test"', observation)
        _apply_execution_state(
            run_state,
            GuiDecision.from_dict(
                {
                    "status": "continue",
                    "stage": "compose",
                    "current_state": "composer focused",
                    "progress_assessment": "typed",
                    "previous_step_ok": True,
                    "success_criteria": "target text typed",
                    "completion_evidence": "",
                    "action": {"type": "type", "target": "composer", "text": "test"},
                }
            ),
            type("Result", (), {"ok": True})(),
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="test",
                composer_visible=True,
                composer_exact_match=True,
                composer_empty=False,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer exactly matches target.",
            ),
        )
        submit = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "submit",
                "current_state": "text typed",
                "progress_assessment": "submit now",
                "previous_step_ok": True,
                "success_criteria": "message sent",
                "completion_evidence": "",
                "action": {"type": "hotkey", "target": "submit composer", "keys": ["enter"]},
            }
        )
        self.assertIn("not stable yet", _submit_gate_error(submit, run_state))

        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="test",
                composer_visible=True,
                composer_exact_match=True,
                composer_empty=False,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer exactly matches target.",
            ),
        )
        self.assertIsNone(_submit_gate_error(submit, run_state))

    def test_wait_action_with_submit_word_is_not_treated_as_submit(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "hello-world"', observation)
        _apply_execution_state(
            run_state,
            GuiDecision.from_dict(
                {
                    "status": "continue",
                    "stage": "compose",
                    "current_state": "composer focused",
                    "progress_assessment": "typed",
                    "previous_step_ok": True,
                    "success_criteria": "target text typed",
                    "completion_evidence": "",
                    "action": {"type": "type", "target": "composer", "text": "hello-world"},
                }
            ),
            type("Result", (), {"ok": True})(),
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="hello-world",
                composer_visible=True,
                composer_exact_match=True,
                composer_empty=False,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer exactly matches target.",
            ),
        )
        wait_decision = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "exact match visible",
                "progress_assessment": "wait for one more stable frame",
                "previous_step_ok": True,
                "success_criteria": "observation stabilizes",
                "completion_evidence": "",
                "action": {
                    "type": "wait",
                    "target": "allow UI observation to stabilize before submitting",
                    "duration_ms": 800,
                },
            }
        )
        self.assertIsNone(_submit_gate_error(wait_decision, run_state))

    def test_prefilled_exact_composer_requires_reset_before_submit(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "hello-world"', observation)
        exact_state = GuiMessageVisualState(
            composer_text="hello-world",
            composer_visible=True,
            composer_exact_match=True,
            composer_empty=False,
            sent_message_visible=False,
            sent_message_exact_match=False,
            evidence="Composer already contains the exact target message.",
        )
        _apply_visual_state(run_state, exact_state)
        _apply_visual_state(run_state, exact_state)
        submit = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "submit",
                "current_state": "exact target already drafted",
                "progress_assessment": "submit now",
                "previous_step_ok": True,
                "success_criteria": "message is sent",
                "completion_evidence": "",
                "action": {"type": "click", "target": "send button", "x": 1, "y": 1},
            }
        )
        error = _submit_gate_error(submit, run_state)
        self.assertIn("stale text", error)

    def test_select_all_then_retype_satisfies_stale_draft_reset(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "hello-world"', observation)
        stale_state = GuiMessageVisualState(
            composer_text="hello-world",
            composer_visible=True,
            composer_exact_match=True,
            composer_empty=False,
            sent_message_visible=False,
            sent_message_exact_match=False,
            evidence="Composer already contains the exact target message.",
        )
        _apply_visual_state(run_state, stale_state)
        self.assertTrue(run_state.composer_reset_required)
        self.assertFalse(run_state.composer_reset_satisfied)

        select_all = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "stale draft focused",
                "progress_assessment": "select existing draft",
                "previous_step_ok": True,
                "success_criteria": "stale draft is ready to replace",
                "completion_evidence": "",
                "action": {"type": "hotkey", "target": "select draft", "keys": ["command", "a"]},
            }
        )
        _apply_execution_state(run_state, select_all, type("Result", (), {"ok": True})())
        self.assertTrue(run_state.composer_reset_started)

        type_exact = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "compose",
                "current_state": "selection active",
                "progress_assessment": "replace stale draft",
                "previous_step_ok": True,
                "success_criteria": "fresh exact target is visible",
                "completion_evidence": "",
                "action": {"type": "type", "target": "composer", "text": "hello-world"},
            }
        )
        _apply_execution_state(run_state, type_exact, type("Result", (), {"ok": True})())
        _apply_visual_state(run_state, stale_state)
        self.assertTrue(run_state.composer_reset_satisfied)
        self.assertTrue(run_state.target_message_visually_verified)

    def test_plan_converts_unstable_submit_into_wait(self):
        Path("/tmp/mock.png").write_bytes(b"test-image")
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "hello-world"', observation)
        _apply_execution_state(
            run_state,
            GuiDecision.from_dict(
                {
                    "status": "continue",
                    "stage": "compose",
                    "current_state": "composer focused",
                    "progress_assessment": "typed",
                    "previous_step_ok": True,
                    "success_criteria": "target text typed",
                    "completion_evidence": "",
                    "action": {"type": "type", "target": "composer", "text": "hello-world"},
                }
            ),
            type("Result", (), {"ok": True})(),
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="hello-world",
                composer_visible=True,
                composer_exact_match=True,
                composer_empty=False,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer exactly matches target.",
            ),
        )

        class StubRouteAgents:
            def decide(self, prompt, data_url):
                payload = {
                    "status": "continue",
                    "stage": "submit",
                    "current_state": "exact text visible",
                    "progress_assessment": "submit now",
                    "previous_step_ok": True,
                    "success_criteria": "message sent",
                    "completion_evidence": "composer matches target",
                    "done_reason": "",
                    "action": {"type": "click", "target": "send button", "x": 100, "y": 200},
                }
                return type("Decision", (), {"model_dump": lambda self: payload})(), json.dumps(payload)

        runner = GuiRunner.__new__(GuiRunner)
        runner.max_steps = 10
        runner.route_agents = StubRouteAgents()
        decision, _ = runner._plan(
            '请在当前聊天窗口发送消息 "hello-world"',
            observation,
            [],
            1,
            "Feishu",
            run_state,
        )
        self.assertEqual(decision.action.type, "wait")
        self.assertEqual(decision.stage, "verify")

    def test_plan_converts_unstable_done_into_wait(self):
        Path("/tmp/mock.png").write_bytes(b"test-image")
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "hello-world"', observation)
        _apply_execution_state(
            run_state,
            GuiDecision.from_dict(
                {
                    "status": "continue",
                    "stage": "compose",
                    "current_state": "composer focused",
                    "progress_assessment": "typed",
                    "previous_step_ok": True,
                    "success_criteria": "target text typed",
                    "completion_evidence": "",
                    "action": {"type": "type", "target": "composer", "text": "hello-world"},
                }
            ),
            type("Result", (), {"ok": True})(),
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="hello-world",
                composer_visible=True,
                composer_exact_match=True,
                composer_empty=False,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer exactly matches target.",
            ),
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="hello-world",
                composer_visible=True,
                composer_exact_match=True,
                composer_empty=False,
                sent_message_visible=False,
                sent_message_exact_match=False,
                evidence="Composer exactly matches target.",
            ),
        )
        _apply_execution_state(
            run_state,
            GuiDecision.from_dict(
                {
                    "status": "continue",
                    "stage": "submit",
                    "current_state": "exact text visible",
                    "progress_assessment": "submit now",
                    "previous_step_ok": True,
                    "success_criteria": "message sent",
                    "completion_evidence": "",
                    "action": {"type": "click", "target": "send button", "x": 100, "y": 200},
                }
            ),
            type("Result", (), {"ok": True})(),
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                composer_text="",
                composer_visible=True,
                composer_exact_match=False,
                composer_empty=True,
                sent_message_visible=True,
                sent_message_exact_match=True,
                latest_visible_message="hello-world",
                evidence="The sent message is visible and the composer is cleared, but this is the first completion observation.",
            ),
        )

        class StubRouteAgents:
            def decide(self, prompt, data_url):
                payload = {
                    "status": "done",
                    "stage": "complete",
                    "current_state": "sent message visible and composer cleared",
                    "progress_assessment": "goal completed",
                    "previous_step_ok": True,
                    "success_criteria": "no further action needed",
                    "completion_evidence": "hello-world bubble is visible and composer is cleared",
                    "done_reason": "message sent",
                    "workflow_steps": [
                        "Observe current chat",
                        "Focus composer",
                        "Type exact target message",
                        "Submit send action",
                        "Verify sent message is new for this run",
                    ],
                    "active_step_index": 4,
                    "action": None,
                }
                return type("Decision", (), {"model_dump": lambda self: payload})(), json.dumps(payload)

        runner = GuiRunner.__new__(GuiRunner)
        runner.max_steps = 10
        runner.route_agents = StubRouteAgents()
        decision, _ = runner._plan(
            '请在当前聊天窗口发送消息 "hello-world"',
            observation,
            [],
            1,
            "Feishu",
            run_state,
        )
        self.assertEqual(decision.action.type, "wait")
        self.assertEqual(decision.action.duration_ms, 800)

    def test_plan_retries_when_blocked_on_preexisting_calendar_event(self):
        Path("/tmp/mock.png").write_bytes(b"test-image")
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state(
            '打开calendar 日历并在今天 6:30 PM 点击对应时间节点，创建标题为 "test" 的event并保存',
            observation,
        )
        _apply_visual_state(
            run_state,
            GuiMessageVisualState(
                primary_view="calendar_week_view",
                selected_sidebar_item="Calendar",
                calendar_visible=True,
                calendar_today_highlighted=True,
                calendar_today_label="27",
                calendar_saved_event_visible=True,
                calendar_saved_event_title="test",
                evidence="A matching test event tile is already visible in the 6:30 PM slot before any new actions.",
            ),
        )
        self.assertTrue(run_state.calendar_preexisting_matching_event_visible)

        class StubRouteAgents:
            def __init__(self):
                self.calls = 0

            def decide(self, prompt, data_url):
                self.calls += 1
                if self.calls == 1:
                    payload = {
                        "status": "blocked",
                        "stage": "blocked",
                        "current_state": "Calendar is already open and a matching test event is visible at 6:30 PM.",
                        "progress_assessment": "The requested event appears to exist already.",
                        "previous_step_ok": True,
                        "success_criteria": "No new event should be needed if the visible tile already satisfies the goal.",
                        "completion_evidence": "The current screenshot shows a test event tile in the requested 6:30 PM slot.",
                        "done_reason": "Blocked because the requested event is already visible.",
                        "workflow_steps": [
                            "Inspect current calendar state",
                            "Create event if needed",
                            "Save and verify",
                        ],
                        "active_step_index": 0,
                        "action": {"type": "wait", "target": "calendar state to stabilize", "duration_ms": 500},
                    }
                else:
                    payload = {
                        "status": "continue",
                        "stage": "compose",
                        "current_state": "Calendar is open and today's column is visible, but this run still needs a fresh creation flow.",
                        "progress_assessment": "Use a direct slot click to open a new event editor instead of relying on the old visible tile.",
                        "previous_step_ok": True,
                        "success_criteria": "A fresh event editor opens from the requested 6:30 PM slot in today's column.",
                        "completion_evidence": "The existing visible tile is baseline only for this run.",
                        "workflow_steps": [
                            "Inspect current calendar state",
                            "Click 6:30 PM slot in today's column",
                            "Type title and save",
                            "Verify the new event",
                        ],
                        "active_step_index": 1,
                        "action": {
                            "type": "click",
                            "target": "empty 6:30 PM slot area in today's highlighted calendar column",
                            "x": 100,
                            "y": 200,
                        },
                    }
                return type("Decision", (), {"model_dump": lambda self: payload})(), json.dumps(payload)

        stub = StubRouteAgents()
        runner = GuiRunner.__new__(GuiRunner)
        runner.max_steps = 10
        runner.route_agents = stub
        decision, _ = runner._plan(
            '打开calendar 日历并在今天 6:30 PM 点击对应时间节点，创建标题为 "test" 的event并保存',
            observation,
            [],
            1,
            "Feishu",
            run_state,
        )
        self.assertEqual(stub.calls, 2)
        self.assertEqual(decision.status, "continue")
        self.assertEqual(decision.action.type, "click")

    def test_visual_state_stability_uses_repeated_signatures(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        run_state = _build_initial_run_state('请在当前聊天窗口发送消息 "test"', observation)
        first_state = GuiMessageVisualState(
            composer_text="test",
            composer_visible=True,
            composer_exact_match=True,
            composer_empty=False,
            sent_message_visible=False,
            sent_message_exact_match=False,
            evidence="Composer exactly matches target.",
        )
        _apply_visual_state(run_state, first_state)
        self.assertFalse(run_state.perception_stable)
        self.assertEqual(run_state.perception_repeat_count, 1)

        _apply_visual_state(run_state, first_state)
        self.assertTrue(run_state.perception_stable)
        self.assertEqual(run_state.perception_repeat_count, 2)

    def test_apply_feishu_emoji_heuristic_on_first_step(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        decision = _maybe_apply_feishu_emoji_heuristic(
            "点击笑脸图标，选择一个表情发送",
            observation,
            [],
            1,
            "Feishu",
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action.type, "click")
        self.assertEqual(decision.action.target, "feishu composer smiley emoji button (heuristic)")
        self.assertEqual(decision.action.x, int(round(2322 * 0.79)))
        self.assertEqual(decision.action.y, int(round(1272 * 0.915)))
        self.assertEqual(decision.stage, "compose")

    def test_apply_feishu_emoji_heuristic_on_second_step(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        history = [
            {
                "action": {
                    "target": "feishu composer smiley emoji button (heuristic)",
                    "x": int(round(2322 * 0.79)),
                    "y": int(round(1272 * 0.915)),
                }
            }
        ]
        decision = _maybe_apply_feishu_emoji_heuristic(
            "点击笑脸图标，选择一个表情发送",
            observation,
            history,
            2,
            "Feishu",
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action.target, "feishu emoji picker frequent emoji tile (heuristic)")
        self.assertEqual(decision.action.x, int(round(2322 * 0.626)))
        self.assertEqual(decision.action.y, int(round(1272 * 0.318)))
        self.assertEqual(decision.stage, "compose")

    def test_apply_feishu_emoji_heuristic_on_third_step(self):
        observation = ScreenshotArtifact(
            path=Path("/tmp/mock.png"),
            width=2322,
            height=1272,
            origin_x=0,
            origin_y=38,
            screen_width=1161,
            screen_height=636,
            scale_x=2.0,
            scale_y=2.0,
        )
        history = [
            {"action": {"target": "feishu composer smiley emoji button (heuristic)"}},
            {"action": {"target": "feishu emoji picker frequent emoji tile (heuristic)"}},
        ]
        decision = _maybe_apply_feishu_emoji_heuristic(
            "点击笑脸图标，选择一个表情发送",
            observation,
            history,
            3,
            "Feishu",
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.action.type, "hotkey")
        self.assertEqual(decision.action.keys, ["enter"])
        self.assertEqual(decision.stage, "submit")


if __name__ == "__main__":
    unittest.main()
