"""Ensure eval suite manifest is valid and consistent with verifier assertions."""

from __future__ import annotations

import json
import os
import unittest

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "feishu_eval_suite.json")

KNOWN_ASSERTIONS = {
    "chat_title_matched",
    "message_input_contains_text",
    "message_sent",
    "docs_home_ready",
    "docs_new_menu_opened",
    "docs_template_gallery_ready",
    "doc_editor_ready",
    "doc_title_contains_text",
    "doc_body_contains_text",
    "base_home_ready",
    "base_new_menu_opened",
    "base_template_gallery_ready",
    "base_editor_ready",
    "im_search_panel_ready",
    "docs_share_dialog_opened",
    "calendar_create_surface_ready",
    "calendar_home_ready",
    "calendar_event_modal_ready",
    "calendar_quick_add_ready",
    "vc_home_ready",
    "vc_start_preview_ready",
    "vc_meeting_active",
    "vc_join_preview_ready",
    "vc_meeting_id_entered",
    "vc_joined",
    "vc_invite_dialog_opened",
}

VALID_PRODUCTS = {"im", "docs", "calendar", "base", "vc"}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_COVERAGE = {"full", "partial", "missing"}
VALID_WINDOW_SCOPE = {"single_window", "cross_window"}
FORBIDDEN_SEMANTIC_KEYS = {
    "relative_bounds",
    "bbox",
    "bounding_box",
    "coordinate",
    "coordinates",
    "confidence",
    "score",
    "resolution",
    "image_width",
    "image_height",
    "steps",
    "ordered_steps",
    "action_sequence",
}


class EvalSuiteManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as handle:
            cls.data = json.load(handle)

    def test_manifest_has_test_cases(self):
        cases = self.data.get("test_cases", [])
        self.assertIsInstance(cases, list)
        self.assertGreater(
            len(cases), 0, "manifest must contain at least one test case"
        )

    def test_every_case_has_required_fields(self):
        required = {"id", "product", "title", "instruction", "priority", "enabled"}
        for tc in self.data["test_cases"]:
            with self.subTest(tc_id=tc.get("id", "??")):
                for field in required:
                    self.assertIn(field, tc, f"missing required field: {field}")

    def test_ids_are_unique(self):
        ids = [tc["id"] for tc in self.data["test_cases"]]
        self.assertEqual(len(ids), len(set(ids)), "test case IDs must be unique")

    def test_ids_follow_convention(self):
        for tc in self.data["test_cases"]:
            with self.subTest(tc_id=tc["id"]):
                self.assertTrue(
                    tc["id"].startswith("tc_"),
                    f"id must start with tc_: {tc['id']}",
                )

    def test_products_are_valid(self):
        for tc in self.data["test_cases"]:
            with self.subTest(tc_id=tc["id"]):
                self.assertIn(tc["product"], VALID_PRODUCTS)

    def test_priorities_are_valid(self):
        for tc in self.data["test_cases"]:
            with self.subTest(tc_id=tc["id"]):
                self.assertIn(tc["priority"], VALID_PRIORITIES)

    def test_enabled_is_boolean(self):
        for tc in self.data["test_cases"]:
            with self.subTest(tc_id=tc["id"]):
                self.assertIsInstance(tc["enabled"], bool)

    def test_instructions_are_non_empty(self):
        for tc in self.data["test_cases"]:
            with self.subTest(tc_id=tc["id"]):
                inst = tc.get("instruction", "")
                self.assertTrue(isinstance(inst, str) and inst.strip())

    def test_assertions_reference_known_verifiers(self):
        for tc in self.data["test_cases"]:
            with self.subTest(tc_id=tc["id"]):
                for assertion in tc.get("assertions", []):
                    self.assertIn(
                        assertion,
                        KNOWN_ASSERTIONS,
                        f"unknown assertion: {assertion}",
                    )

    def test_coverage_field_if_present(self):
        for tc in self.data["test_cases"]:
            coverage = tc.get("verifier_coverage")
            if coverage is not None:
                with self.subTest(tc_id=tc["id"]):
                    self.assertIn(coverage, VALID_COVERAGE)

    def test_all_products_have_at_least_one_test(self):
        products_in_manifest = {tc["product"] for tc in self.data["test_cases"]}
        self.assertEqual(products_in_manifest, VALID_PRODUCTS)

    def test_disabled_cases_have_note(self):
        for tc in self.data["test_cases"]:
            if not tc["enabled"]:
                with self.subTest(tc_id=tc["id"]):
                    self.assertTrue(
                        tc.get("note"),
                        "disabled test cases should explain why",
                    )

    def test_enabled_cases_have_full_or_partial_coverage(self):
        for tc in self.data["test_cases"]:
            if tc["enabled"]:
                with self.subTest(tc_id=tc["id"]):
                    self.assertIn(
                        tc.get("verifier_coverage"),
                        ("full", "partial"),
                        "enabled cases must have verifier coverage",
                    )

    def test_window_scope_if_present(self):
        for tc in self.data["test_cases"]:
            scope = tc.get("window_scope")
            if scope is not None:
                with self.subTest(tc_id=tc["id"]):
                    self.assertIn(scope, VALID_WINDOW_SCOPE)

    def test_cross_window_cases_are_explicit_and_reviewable(self):
        cross_window_cases = [
            tc
            for tc in self.data["test_cases"]
            if tc.get("window_scope") == "cross_window"
        ]

        self.assertGreaterEqual(len(cross_window_cases), 4)
        for tc in cross_window_cases:
            with self.subTest(tc_id=tc["id"]):
                related_products = tc.get("related_products", [])
                self.assertGreaterEqual(len(set(related_products)), 2)
                self.assertIn(tc["product"], related_products)
                self.assertTrue(tc.get("window_surfaces"))
                self.assertTrue(tc.get("evidence_focus"))
                self.assertTrue(tc.get("note"))
                self.assertEqual(tc.get("verifier_coverage"), "partial")

    def test_cross_window_cases_are_semantic_only(self):
        cross_window_cases = [
            tc
            for tc in self.data["test_cases"]
            if tc.get("window_scope") == "cross_window"
        ]
        for tc in cross_window_cases:
            with self.subTest(tc_id=tc["id"]):
                self.assertFalse(
                    FORBIDDEN_SEMANTIC_KEYS.intersection(tc.keys()),
                    "cross-window cases must not define coordinate or step-chain fields",
                )
                serialized = json.dumps(tc, ensure_ascii=False).lower()
                for forbidden in (
                    "relative_bounds",
                    "bbox",
                    "confidence",
                    "image_width",
                    "image_height",
                    "ordered step",
                    "ordered_steps",
                    "action_sequence",
                ):
                    self.assertNotIn(forbidden, serialized)
