import unittest
from argparse import Namespace

from agent.gui.manual import build_action_from_args


class GuiManualTest(unittest.TestCase):
    def test_build_hotkey_action(self):
        action = build_action_from_args(
            Namespace(
                action_type="hotkey",
                target="search",
                x=None,
                y=None,
                end_x=None,
                end_y=None,
                text=None,
                amount=None,
                duration_ms=None,
                keys="command,k",
            )
        )
        self.assertEqual(action.type, "hotkey")
        self.assertEqual(action.keys, ["command", "k"])

    def test_build_drag_action(self):
        action = build_action_from_args(
            Namespace(
                action_type="drag",
                target="window",
                x=10,
                y=20,
                end_x=30,
                end_y=40,
                text=None,
                amount=None,
                duration_ms=None,
                keys=None,
            )
        )
        self.assertEqual(action.type, "drag")
        self.assertEqual(action.end_x, 30)
        self.assertEqual(action.end_y, 40)


if __name__ == "__main__":
    unittest.main()
