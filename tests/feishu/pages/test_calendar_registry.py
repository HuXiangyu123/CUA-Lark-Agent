import unittest

from gui_agents.feishu.pages.registry import get_page_descriptor, get_page_ids


class TestCalendarPageRegistry(unittest.TestCase):
    def test_registry_exposes_calendar_home_descriptor(self) -> None:
        self.assertIn("calendar_home", get_page_ids())
        descriptor = get_page_descriptor("calendar_home")
        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor["page_type"], "calendar_home")
        self.assertNotIn("relative_bounds", str(descriptor["key_regions"]))
        self.assertIn("visible_text", descriptor["key_regions"]["create_event_button"])

    def test_registry_exposes_calendar_event_modal_descriptor(self) -> None:
        self.assertIn("calendar_event_modal", get_page_ids())
        descriptor = get_page_descriptor("calendar_event_modal")
        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor["page_type"], "calendar_event_modal")
        self.assertNotIn("relative_bounds", str(descriptor["key_regions"]))
        self.assertIn("visible_text", descriptor["key_regions"]["save_button"])

    def test_registry_exposes_calendar_quick_add_descriptor(self) -> None:
        self.assertIn("calendar_quick_add_modal", get_page_ids())
        descriptor = get_page_descriptor("calendar_quick_add_modal")
        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor["page_type"], "calendar_quick_add_modal")
        self.assertNotIn("relative_bounds", str(descriptor["key_regions"]))
        self.assertEqual(
            descriptor["layout_hints"]["origin"], "calendar_week_grid_time_slot"
        )

    def test_registry_exposes_calendar_date_picker_descriptor(self) -> None:
        self.assertIn("calendar_date_picker", get_page_ids())
        descriptor = get_page_descriptor("calendar_date_picker")
        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor["page_type"], "calendar_date_picker")
        self.assertNotIn("relative_bounds", str(descriptor["key_regions"]))
        self.assertIn("today_shortcut", descriptor["key_regions"])


if __name__ == "__main__":
    unittest.main()
