import unittest

from agent.router import RouteMode, resolve_route


class RouterTest(unittest.TestCase):
    def test_force_gui_prefix(self):
        route, text = resolve_route("/gui 点击飞书搜索框", RouteMode.AUTO)
        self.assertEqual(route, RouteMode.GUI)
        self.assertEqual(text, "点击飞书搜索框")

    def test_auto_routes_gui_keywords(self):
        route, _ = resolve_route("在飞书客户端里点击日历按钮", RouteMode.AUTO)
        self.assertEqual(route, RouteMode.GUI)

    def test_auto_routes_api_by_default(self):
        route, _ = resolve_route("帮我查一下最近的日历事件", RouteMode.AUTO)
        self.assertEqual(route, RouteMode.API)


if __name__ == "__main__":
    unittest.main()
