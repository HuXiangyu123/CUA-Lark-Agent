from pathlib import Path
import unittest

from gui_agents.feishu.testcases.nl_parser import parse_instruction


CALENDAR_DIRS = [
    Path("gui_agents/feishu/pages/calendar_home.py"),
    Path("gui_agents/feishu/pages/calendar_event_modal.py"),
    Path("gui_agents/feishu/detectors/calendar_state_detector.py"),
    Path("gui_agents/feishu/tooling/tool_router.py"),
]

CALENDAR_FIXTURE_DIR = Path("tests/fixtures/calendar")


class TestCalendarConstraints(unittest.TestCase):
    def test_calendar_fixtures_do_not_use_quantitative_metadata(self) -> None:
        forbidden = ("relative_bounds", "bbox", "confidence", "score", "x1", "y1")
        for path in CALENDAR_FIXTURE_DIR.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for token in forbidden:
                    self.assertNotIn(token, text)

    def test_calendar_runtime_files_do_not_use_quantitative_page_metadata(self) -> None:
        forbidden = ("relative_bounds", "bbox", "confidence", "score")
        for path in CALENDAR_DIRS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for token in forbidden:
                    self.assertNotIn(token, text)

    def test_calendar_instruction_no_longer_compiles_fixed_workflow(self) -> None:
        testcase = parse_instruction("帮我创建一个日历会议")

        self.assertEqual(testcase["product"], "calendar")
        self.assertEqual(testcase["steps"], [])
        self.assertTrue(testcase["artifacts"]["semantic_guidance_only"])
        self.assertEqual(testcase["artifacts"]["active_executor"], "feishu_agent")


if __name__ == "__main__":
    unittest.main()
