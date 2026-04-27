import unittest

from agent.gui.schema import GuiDecision


class GuiSchemaTest(unittest.TestCase):
    def test_parse_click_action(self):
        decision = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "navigate",
                "current_state": "飞书首页",
                "progress_assessment": "还未开始",
                "previous_step_ok": True,
                "success_criteria": "进入 IM 模块",
                "completion_evidence": "尚未产生发送证据",
                "workflow_steps": ["观察聊天窗口", "点击 IM 入口"],
                "active_step_index": 1,
                "action": {"type": "click", "target": "IM", "x": 120, "y": 300},
            }
        )
        self.assertEqual(decision.stage, "navigate")
        self.assertEqual(decision.completion_evidence, "尚未产生发送证据")
        self.assertEqual(decision.workflow_steps, ["观察聊天窗口", "点击 IM 入口"])
        self.assertEqual(decision.active_step_index, 1)
        self.assertEqual(decision.action.type, "click")
        self.assertEqual(decision.action.x, 120)

    def test_done_status_allows_no_action(self):
        decision = GuiDecision.from_dict(
            {
                "status": "done",
                "stage": "complete",
                "current_state": "目标已完成",
                "progress_assessment": "消息已经发送",
                "previous_step_ok": True,
                "success_criteria": "",
                "completion_evidence": "本轮已经执行发送动作",
                "done_reason": "目标已达成",
            }
        )
        self.assertEqual(decision.status, "done")
        self.assertIsNone(decision.action)

    def test_default_stage_is_inferred(self):
        decision = GuiDecision.from_dict(
            {
                "status": "blocked",
                "current_state": "界面不可用",
                "progress_assessment": "无法继续",
                "previous_step_ok": False,
                "success_criteria": "",
                "done_reason": "窗口消失",
            }
        )
        self.assertEqual(decision.stage, "blocked")

    def test_wait_action_coerces_nonpositive_duration(self):
        decision = GuiDecision.from_dict(
            {
                "status": "continue",
                "stage": "verify",
                "current_state": "waiting for stable frame",
                "progress_assessment": "observe again",
                "previous_step_ok": True,
                "success_criteria": "frame stabilizes",
                "action": {"type": "wait", "target": "observe again", "duration_ms": 0},
            }
        )
        self.assertEqual(decision.action.duration_ms, 1000)


if __name__ == "__main__":
    unittest.main()
