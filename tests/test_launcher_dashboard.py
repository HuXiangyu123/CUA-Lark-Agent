import unittest
from unittest.mock import Mock, patch

import launcher


class LauncherDashboardHelperTest(unittest.TestCase):
    def test_ensure_dashboard_server_reuses_alive_handle(self) -> None:
        handle = Mock()
        handle.thread.is_alive.return_value = True

        with patch.object(launcher, "start_dashboard_server") as start_mock:
            result = launcher.ensure_dashboard_server(handle)

        self.assertIs(result, handle)
        start_mock.assert_not_called()

    def test_ensure_dashboard_server_starts_when_handle_missing(self) -> None:
        created = Mock()
        with patch.object(
            launcher,
            "start_dashboard_server",
            return_value=created,
        ) as start_mock:
            result = launcher.ensure_dashboard_server(None)

        self.assertIs(result, created)
        start_mock.assert_called_once()

    def test_ensure_dashboard_server_restarts_dead_handle(self) -> None:
        dead_handle = Mock()
        dead_handle.thread.is_alive.return_value = False
        created = Mock()

        with patch.object(
            launcher,
            "start_dashboard_server",
            return_value=created,
        ) as start_mock:
            result = launcher.ensure_dashboard_server(dead_handle)

        self.assertIs(result, created)
        start_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
