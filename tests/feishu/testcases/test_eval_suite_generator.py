"""Tests for the Feishu eval suite manifest generator."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gui_agents.feishu.testcases.eval_suite_generator import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SEED_PATH,
    FORBIDDEN_SEMANTIC_KEYS,
    build_eval_suite_manifest,
    generate_eval_suite_manifest,
    manifest_matches_file,
    write_eval_suite_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_feishu_eval_suite.py"


class TestEvalSuiteGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.seed_payload = json.loads(DEFAULT_SEED_PATH.read_text(encoding="utf-8"))
        cls.checked_in_manifest = json.loads(
            DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8")
        )

    def setUp(self) -> None:
        self.maxDiff = None

    def test_generated_manifest_matches_checked_in_manifest(self) -> None:
        manifest = generate_eval_suite_manifest()

        self.assertEqual(manifest, self.checked_in_manifest)
        self.assertTrue(manifest_matches_file())

    def test_write_eval_suite_manifest_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "generated_eval_suite.json"

            manifest = write_eval_suite_manifest(output_path)

            self.assertEqual(manifest, self.checked_in_manifest)
            self.assertTrue(manifest_matches_file(output_path))

    def test_cross_window_cases_remain_semantic_only(self) -> None:
        manifest = generate_eval_suite_manifest()
        cross_window_cases = [
            case
            for case in manifest["test_cases"]
            if case.get("window_scope") == "cross_window"
        ]

        self.assertGreaterEqual(len(cross_window_cases), 4)
        for case in cross_window_cases:
            with self.subTest(tc_id=case["id"]):
                self.assertFalse(FORBIDDEN_SEMANTIC_KEYS.intersection(case.keys()))
                serialized = json.dumps(case, ensure_ascii=False).lower()
                for forbidden in FORBIDDEN_SEMANTIC_KEYS:
                    self.assertNotIn(forbidden, serialized)

    def test_rejects_unknown_profile_reference(self) -> None:
        payload = copy.deepcopy(self.seed_payload)
        payload["case_seeds"][0]["profile"] = "missing_profile"

        with self.assertRaisesRegex(ValueError, "references unknown profile"):
            build_eval_suite_manifest(payload)

    def test_rejects_unsupported_assertion_in_profile(self) -> None:
        payload = copy.deepcopy(self.seed_payload)
        payload["profiles"]["im_send_message"]["assertions"] = [
            "chat_title_matched",
            "unknown_assertion",
        ]

        with self.assertRaisesRegex(ValueError, "contains unsupported value"):
            build_eval_suite_manifest(payload)

    def test_rejects_workflow_like_fields_in_seed(self) -> None:
        payload = copy.deepcopy(self.seed_payload)
        payload["case_seeds"][0]["steps"] = [{"id": "forbidden"}]

        with self.assertRaisesRegex(ValueError, "forbidden semantic field: steps"):
            build_eval_suite_manifest(payload)

    def test_cli_check_succeeds(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertIn("FEISHU_EVAL_SUITE_CHECK_OK", result.stdout)
