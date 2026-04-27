import unittest

from agent.json_utils import extract_json_object


class JsonUtilsTest(unittest.TestCase):
    def test_extract_from_fenced_block(self):
        text = 'hello\n```json\n{"a": 1, "b": "x"}\n```\nbye'
        self.assertEqual(extract_json_object(text), {"a": 1, "b": "x"})

    def test_extract_from_raw_text(self):
        text = 'result: {"status":"continue","action":{"type":"wait","duration_ms":500}}'
        self.assertEqual(
            extract_json_object(text),
            {"status": "continue", "action": {"type": "wait", "duration_ms": 500}},
        )


if __name__ == "__main__":
    unittest.main()
