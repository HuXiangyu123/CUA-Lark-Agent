import unittest

from agent.gui.capture import ScreenshotArtifact
from agent.gui.schema import GuiAction
from agent.gui.window import (
    WindowInfo,
    _parse_window_list,
    _select_main_window,
    _titlebar_click_point,
    _window_matches_app_title,
    _window_title_candidates,
    translate_action_from_image_to_screen,
    translate_action_to_screen,
)


class GuiWindowTest(unittest.TestCase):
    def test_translate_click_to_screen(self):
        action = GuiAction.from_dict({"type": "click", "x": 20, "y": 30})
        window = WindowInfo(app_name="Feishu", x=12, y=81, width=1000, height=800)
        translated = translate_action_to_screen(action, window)
        self.assertEqual(translated.x, 32)
        self.assertEqual(translated.y, 111)

    def test_translate_hotkey_does_not_change(self):
        action = GuiAction.from_dict({"type": "hotkey", "keys": ["command", "k"]})
        window = WindowInfo(app_name="Feishu", x=12, y=81, width=1000, height=800)
        translated = translate_action_to_screen(action, window)
        self.assertEqual(translated.keys, ["command", "k"])
        self.assertIsNone(translated.x)

    def test_translate_image_pixels_to_screen(self):
        action = GuiAction.from_dict({"type": "click", "x": 1515, "y": 968})
        observation = ScreenshotArtifact(
            path=None,  # type: ignore[arg-type]
            width=2322,
            height=1008,
            origin_x=153,
            origin_y=704,
            screen_width=1161,
            screen_height=504,
            scale_x=2.0,
            scale_y=2.0,
        )
        translated = translate_action_from_image_to_screen(action, observation)
        self.assertEqual(translated.x, 911)
        self.assertEqual(translated.y, 1188)

    def test_parse_window_list_ignores_invalid_lines(self):
        windows = _parse_window_list("7,192,1161,636\ninvalid\n658,756,397,28\n")
        self.assertEqual(windows, [(7, 192, 1161, 636), (658, 756, 397, 28)])

    def test_select_main_window_prefers_largest_area(self):
        selected = _select_main_window([(658, 756, 397, 28), (7, 192, 1161, 636)])
        self.assertEqual(selected, (7, 192, 1161, 636))

    def test_titlebar_click_point_uses_safe_top_center(self):
        self.assertEqual(_titlebar_click_point(100, 200, 1000, 700), (600, 223))
        self.assertEqual(_titlebar_click_point(10, 20, 120, 28), (70, 32))

    def test_feishu_title_candidates_match_chinese_window_title(self):
        candidates = _window_title_candidates("Feishu")
        self.assertIn("飞书", candidates)
        self.assertTrue(_window_matches_app_title("飞书", candidates))
        self.assertFalse(_window_matches_app_title("PackyAPI - Microsoft Edge", candidates))


if __name__ == "__main__":
    unittest.main()
