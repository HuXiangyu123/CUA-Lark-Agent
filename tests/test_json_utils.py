import unittest

from agent.json_utils import extract_json_object


class JsonUtilsTest(unittest.TestCase):
    def test_extract_from_fenced_block(self):
        text = 'hello\n```json\n{"a": 1, "b": "x"}\n```\nbye'
        self.assertEqual(extract_json_object(text), {"a": 1, "b": "x"})

    def test_extract_from_uppercase_fenced_block(self):
        text = 'hello\n```JSON\n{"a": 1}\n```\nbye'
        self.assertEqual(extract_json_object(text), {"a": 1})

    def test_extract_from_raw_text(self):
        text = 'result: {"status":"continue","action":{"type":"wait","duration_ms":500}}'
        self.assertEqual(
            extract_json_object(text),
            {"status": "continue", "action": {"type": "wait", "duration_ms": 500}},
        )

    def test_extract_skips_braces_inside_strings(self):
        text = 'result: {"text": "keep {literal} braces", "quote": "say \\"hi\\""} done'
        self.assertEqual(
            extract_json_object(text),
            {"text": "keep {literal} braces", "quote": 'say "hi"'},
        )

    def test_extract_skips_invalid_object_candidate(self):
        text = 'bad: {not json} good: {"ok": true}'
        self.assertEqual(extract_json_object(text), {"ok": True})

    def test_returns_none_for_no_object(self):
        self.assertIsNone(extract_json_object("no json here"))


if __name__ == "__main__":
    unittest.main()
