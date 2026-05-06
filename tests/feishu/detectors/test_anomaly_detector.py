import unittest

from gui_agents.feishu.detectors.anomaly import detect_anomaly_product_state
from gui_agents.feishu.detectors.docs_state_detector import detect_docs_state
from gui_agents.feishu.detectors.im_state_detector import detect_feishu_state


class TestAnomalyDetector(unittest.TestCase):
    def test_detects_permission_denied_from_ocr(self) -> None:
        state = detect_anomaly_product_state("权限不足 需要权限 申请权限")

        self.assertTrue(state["permission_denied_visible"])
        self.assertEqual(state["recovery_hint"], "request_permission")
        self.assertIn("permission_denied", state["anomaly_types"])

    def test_detects_loading_from_ocr(self) -> None:
        state = detect_anomaly_product_state("加载中 请稍候")

        self.assertTrue(state["loading_visible"])
        self.assertEqual(state["recovery_hint"], "retry_after_load")
        self.assertIn("loading", state["anomaly_types"])

    def test_detects_wrong_surface_from_ocr(self) -> None:
        state = detect_anomaly_product_state("页面不存在 内容已删除")

        self.assertTrue(state["wrong_surface"])
        self.assertEqual(state["recovery_hint"], "navigate_to_correct_page")
        self.assertIn("wrong_surface", state["anomaly_types"])

    def test_detects_blocking_modal_from_multiple_modal_actions(self) -> None:
        state = detect_anomaly_product_state("提示 确定 取消 关闭")

        self.assertTrue(state["blocking_modal_visible"])
        self.assertEqual(state["recovery_hint"], "close_modal_or_wait")
        self.assertIn("blocking_modal", state["anomaly_types"])

    def test_single_cancel_does_not_mark_calendar_like_modal_as_blocking(self) -> None:
        state = detect_anomaly_product_state("创建日程 添加主题 保存 取消")

        self.assertNotIn("blocking_modal_visible", state)
        self.assertNotIn("recovery_hint", state)

    def test_product_fallback_merges_anomaly_flags(self) -> None:
        docs_state = detect_docs_state({"ocr_text": "飞书云文档 权限不足 申请权限"})
        im_state = detect_feishu_state({"ocr_text": "发送给 bot 加载中 请稍候"})

        self.assertTrue(docs_state["product_state"]["permission_denied_visible"])
        self.assertEqual(
            docs_state["product_state"]["recovery_hint"], "request_permission"
        )
        self.assertTrue(im_state["product_state"]["loading_visible"])
        self.assertEqual(im_state["product_state"]["recovery_hint"], "retry_after_load")


if __name__ == "__main__":
    unittest.main()
