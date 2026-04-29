import unittest

from agent.gui.capture import _region_to_image_box


class GuiCaptureTest(unittest.TestCase):
    def test_region_to_image_box_scales_high_dpi_laptop(self):
        box = _region_to_image_box(
            region=(100, 80, 1000, 700),
            virtual_origin=(0, 0),
            virtual_size=(1707, 1067),
            image_size=(2560, 1600),
        )
        self.assertEqual(box, (150, 120, 1650, 1170))

    def test_region_to_image_box_handles_negative_virtual_origin(self):
        box = _region_to_image_box(
            region=(-1800, 100, 1200, 800),
            virtual_origin=(-1920, 0),
            virtual_size=(3840, 1080),
            image_size=(3840, 1080),
        )
        self.assertEqual(box, (120, 100, 1320, 900))

    def test_region_to_image_box_clamps_to_image_bounds(self):
        box = _region_to_image_box(
            region=(-50, -20, 300, 200),
            virtual_origin=(0, 0),
            virtual_size=(1000, 800),
            image_size=(1500, 1200),
        )
        self.assertEqual(box, (0, 0, 375, 270))


if __name__ == "__main__":
    unittest.main()
