import builtins
import unittest
from types import SimpleNamespace
from unittest import mock

from agent.gui import dpi


class GuiDpiTest(unittest.TestCase):
    def setUp(self):
        dpi._DPI_AWARENESS_ATTEMPTED = False

    def tearDown(self):
        dpi._DPI_AWARENESS_ATTEMPTED = False

    def test_non_windows_is_noop(self):
        with mock.patch.object(dpi.sys, "platform", "linux"):
            dpi.ensure_windows_dpi_awareness()
        self.assertFalse(dpi._DPI_AWARENESS_ATTEMPTED)

    def test_windows_prefers_per_monitor_v2_awareness(self):
        calls = []

        def set_context(context):
            calls.append(context)
            return True

        fake_ctypes = SimpleNamespace(
            windll=SimpleNamespace(
                user32=SimpleNamespace(
                    SetProcessDpiAwarenessContext=set_context,
                    SetProcessDPIAware=mock.Mock(),
                ),
                shcore=SimpleNamespace(SetProcessDpiAwareness=mock.Mock()),
            )
        )

        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "ctypes":
                return fake_ctypes
            return original_import(name, *args, **kwargs)

        with mock.patch.object(dpi.sys, "platform", "win32"), mock.patch.object(builtins, "__import__", fake_import):
            dpi.ensure_windows_dpi_awareness()

        self.assertEqual(calls, [-4])
        fake_ctypes.windll.shcore.SetProcessDpiAwareness.assert_not_called()
        fake_ctypes.windll.user32.SetProcessDPIAware.assert_not_called()

    def test_windows_dpi_awareness_is_attempted_once(self):
        set_context = mock.Mock(return_value=True)
        fake_ctypes = SimpleNamespace(
            windll=SimpleNamespace(
                user32=SimpleNamespace(
                    SetProcessDpiAwarenessContext=set_context,
                    SetProcessDPIAware=mock.Mock(),
                ),
                shcore=SimpleNamespace(SetProcessDpiAwareness=mock.Mock()),
            )
        )

        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "ctypes":
                return fake_ctypes
            return original_import(name, *args, **kwargs)

        with mock.patch.object(dpi.sys, "platform", "win32"), mock.patch.object(builtins, "__import__", fake_import):
            dpi.ensure_windows_dpi_awareness()
            dpi.ensure_windows_dpi_awareness()

        set_context.assert_called_once_with(-4)


if __name__ == "__main__":
    unittest.main()
