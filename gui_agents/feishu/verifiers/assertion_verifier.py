"""Semantic assertion verifier for Feishu agentic runtime."""

from __future__ import annotations

from typing import Any

from gui_agents.feishu.contracts import FeishuState, RuntimeContext, TestCase
from gui_agents.feishu.observation import normalize_observation


def _success(assertion: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "passed": True,
        "assertion": assertion,
        "evidence": evidence,
        "failure_type": None,
        "failure_reason": None,
    }


def _failure(assertion: str, reason: str) -> dict[str, Any]:
    return {
        "passed": False,
        "assertion": assertion,
        "evidence": [],
        "failure_type": "verification",
        "failure_reason": reason,
    }


class AssertionVerifier:
    def verify_assertion(
        self,
        assertion: str,
        state: FeishuState,
        observation: dict[str, Any],
        expected: dict[str, Any] | None = None,
        runtime_context: RuntimeContext | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del runtime_context

        expected = expected or {}
        metadata = normalize_observation(observation)
        product_state = state.get("product_state", {})
        ocr_text = observation.get("ocr_text", "") or metadata.get(
            "text_anchors_text", ""
        )

        if assertion == "chat_title_matched":
            expected_chat_name = (
                expected.get("chat_name")
                or expected.get("target")
                or (expected.get("params") or {}).get("chat_name")
                or metadata.get("chat_name")
            )
            actual_chat_name = state.get("chat_name")
            if expected_chat_name and actual_chat_name == expected_chat_name:
                return _success(
                    assertion,
                    [f"chat_name={actual_chat_name}", "page_type=chat_main"],
                )
            if expected_chat_name and expected_chat_name in ocr_text:
                return _success(
                    assertion,
                    [f"ocr_contains={expected_chat_name}", "source=ocr_fallback"],
                )
            return _failure(
                assertion,
                f"chat title mismatch: expected={expected_chat_name!r}, actual={actual_chat_name!r}",
            )

        if assertion == "message_input_contains_text":
            expected_text = (
                expected.get("message_text")
                or expected.get("text")
                or (expected.get("params") or {}).get("text")
                or (expected.get("payload") or {}).get("text")
            )
            draft_text = product_state.get("draft_text")
            if expected_text and draft_text == expected_text:
                return _success(
                    assertion,
                    [f"draft_text={draft_text}", "draft_present=True"],
                )
            if expected_text and expected_text in ocr_text:
                return _success(
                    assertion,
                    [f"ocr_contains={expected_text}", "source=ocr_fallback"],
                )
            return _failure(
                assertion,
                f"message input text mismatch: expected={expected_text!r}, actual={draft_text!r}",
            )

        if assertion == "message_sent":
            expected_text = (
                expected.get("message_text")
                or expected.get("text")
                or (expected.get("params") or {}).get("text")
                or (expected.get("payload") or {}).get("text")
            )
            sent_visible = bool(product_state.get("message_sent_visible"))
            sent_text = product_state.get("sent_message_text")
            if sent_visible and (not expected_text or sent_text == expected_text):
                evidence = ["message_sent_visible=True"]
                if sent_text:
                    evidence.append(f"sent_message_text={sent_text}")
                return _success(assertion, evidence)
            if expected_text and expected_text in ocr_text:
                return _success(
                    assertion,
                    [f"ocr_contains={expected_text}", "source=ocr_fallback"],
                )
            return _failure(
                assertion,
                f"sent message mismatch: expected={expected_text!r}, actual={sent_text!r}",
            )

        if assertion == "im_search_panel_ready":
            if state.get("page_type") == "chat_search_panel" or product_state.get(
                "local_search_panel_visible"
            ):
                evidence = ["page_type=chat_search_panel"]
                if product_state.get("local_search_result_list_visible"):
                    evidence.append("search_result_list_visible=True")
                return _success(assertion, evidence)
            return _failure(
                assertion,
                f"IM search panel not visible: page_type={state.get('page_type')!r}",
            )

        if assertion == "base_home_ready":
            if state.get("product") == "base" and (
                state.get("page_type") == "base_home"
                or product_state.get("base_home_visible")
            ):
                return _success(assertion, ["product=base", "page_type=base_home"])
            return _failure(
                assertion,
                f"Base home not ready: product={state.get('product')!r}, page_type={state.get('page_type')!r}",
            )

        if assertion == "base_new_menu_opened":
            if state.get("page_type") == "base_new_menu" or product_state.get(
                "new_menu_visible"
            ):
                return _success(assertion, ["new_menu_visible=True"])
            return _failure(assertion, "Base new menu is not visible")

        if assertion == "base_template_gallery_ready":
            if state.get("page_type") == "base_template_gallery" or product_state.get(
                "template_gallery_visible"
            ):
                return _success(assertion, ["template_gallery_visible=True"])
            return _failure(assertion, "Base template gallery is not visible")

        if assertion == "base_editor_ready":
            if state.get("page_type") == "base_browser_table" or product_state.get(
                "base_editor_ready"
            ):
                evidence = ["base_editor_ready=True"]
                if product_state.get("grid_visible"):
                    evidence.append("grid_visible=True")
                return _success(assertion, evidence)
            if "未命名多维表格" in ocr_text and "数据表" in ocr_text:
                return _success(
                    assertion,
                    ["ocr_contains=未命名多维表格", "ocr_contains=数据表"],
                )
            return _failure(assertion, "Base table editor is not ready")

        if assertion == "docs_home_ready":
            if state.get("product") == "docs" and (
                state.get("page_type") == "docs_home"
                or product_state.get("docs_home_visible")
            ):
                return _success(assertion, ["product=docs", "page_type=docs_home"])
            return _failure(
                assertion,
                f"Docs home not ready: product={state.get('product')!r}, page_type={state.get('page_type')!r}",
            )

        if assertion == "docs_new_menu_opened":
            if state.get("page_type") == "docs_new_dropdown" or product_state.get(
                "new_dropdown_visible"
            ):
                return _success(assertion, ["new_dropdown_visible=True"])
            return _failure(assertion, "Docs new dropdown is not visible")

        if assertion == "docs_template_gallery_ready":
            if state.get("page_type") == "docs_template_gallery" or product_state.get(
                "template_gallery_visible"
            ):
                return _success(assertion, ["template_gallery_visible=True"])
            return _failure(assertion, "Docs template gallery is not visible")

        if assertion == "doc_editor_ready":
            if state.get("page_type") == "docs_browser_editor" or product_state.get(
                "editor_ready"
            ):
                return _success(assertion, ["editor_ready=True"])
            return _failure(assertion, "Docs browser editor is not ready")

        if assertion == "doc_title_contains_text":
            expected_text = (
                expected.get("doc_title")
                or expected.get("title")
                or expected.get("text")
                or (expected.get("params") or {}).get("text")
                or (expected.get("payload") or {}).get("text")
            )
            actual_title = product_state.get("doc_title")
            if expected_text and actual_title == expected_text:
                return _success(assertion, [f"doc_title={actual_title}"])
            if expected_text and expected_text in ocr_text:
                return _success(
                    assertion,
                    [f"ocr_contains={expected_text}", "source=ocr_fallback"],
                )
            return _failure(
                assertion,
                f"doc title mismatch: expected={expected_text!r}, actual={actual_title!r}",
            )

        if assertion == "doc_body_contains_text":
            expected_text = (
                expected.get("body_text")
                or expected.get("text")
                or (expected.get("params") or {}).get("text")
                or (expected.get("payload") or {}).get("text")
            )
            actual_body = product_state.get("body_text")
            if expected_text and actual_body == expected_text:
                return _success(assertion, [f"body_text={actual_body}"])
            if expected_text and expected_text in ocr_text:
                return _success(
                    assertion,
                    [f"ocr_contains={expected_text}", "source=ocr_fallback"],
                )
            return _failure(
                assertion,
                f"doc body mismatch: expected={expected_text!r}, actual={actual_body!r}",
            )

        if assertion == "im_search_results_visible":
            if (
                state.get("page_type") == "im_chat_search_panel"
                or product_state.get("local_search_panel_visible")
                or state.get("search_box_visible")
            ):
                evidence = ["search_visible=True"]
                if product_state.get("visible_conversation_search_results"):
                    evidence.append(
                        f"results={product_state['visible_conversation_search_results']}"
                    )
                return _success(assertion, evidence)
            return _failure(
                assertion,
                f"IM search not visible: page_type={state.get('page_type')!r}",
            )

        if assertion == "docs_share_dialog_opened":
            if product_state.get("share_dialog_visible"):
                return _success(assertion, ["share_dialog_visible=True"])
            ocr_lower = ocr_text.lower() if ocr_text else ""
            if "分享链接" in ocr_lower or (
                "分享" in ocr_lower and "复制链接" in ocr_lower
            ):
                return _success(
                    assertion,
                    ["ocr_contains=分享链接", "source=ocr_fallback"],
                )
            return _failure(assertion, "Docs share dialog is not visible")

        if assertion == "calendar_home_ready":
            if state.get("product") == "calendar" and (
                state.get("page_type") == "calendar_home"
                or product_state.get("calendar_home_visible")
            ):
                evidence = ["product=calendar", "page_type=calendar_home"]
                if product_state.get("create_event_button_visible"):
                    evidence.append("create_event_button_visible=True")
                return _success(assertion, evidence)
            return _failure(
                assertion,
                f"Calendar home not ready: product={state.get('product')!r}, page_type={state.get('page_type')!r}",
            )

        if assertion == "calendar_event_modal_ready":
            if state.get("product") == "calendar" and (
                state.get("page_type") == "calendar_event_modal"
                or product_state.get("event_modal_visible")
            ):
                evidence = ["product=calendar", "page_type=calendar_event_modal"]
                if product_state.get("title_input_visible"):
                    evidence.append("title_input_visible=True")
                if product_state.get("save_button_visible"):
                    evidence.append("save_button_visible=True")
                return _success(assertion, evidence)
            return _failure(
                assertion,
                f"Calendar event modal not ready: product={state.get('product')!r}, page_type={state.get('page_type')!r}",
            )

        if assertion == "calendar_quick_add_ready":
            if state.get("product") == "calendar" and (
                state.get("page_type")
                in {"calendar_quick_add_modal", "calendar_quick_add_attendee"}
                or product_state.get("quick_add_visible")
            ):
                evidence = ["product=calendar", f"page_type={state.get('page_type')}"]
                evidence.append("calendar_creation_method=time_slot_quick_add")
                if product_state.get("title_input_visible"):
                    evidence.append("title_input_visible=True")
                if product_state.get("save_button_visible"):
                    evidence.append("save_button_visible=True")
                return _success(assertion, evidence)
            return _failure(
                assertion,
                f"Calendar quick-add popup not ready: product={state.get('product')!r}, page_type={state.get('page_type')!r}",
            )

        if assertion == "calendar_create_surface_ready":
            if state.get("product") == "calendar" and (
                state.get("page_type") == "calendar_event_modal"
                or product_state.get("event_modal_visible")
            ):
                evidence = [
                    "product=calendar",
                    "page_type=calendar_event_modal",
                    "calendar_creation_method=create_schedule_entry",
                ]
                if product_state.get("title_input_visible"):
                    evidence.append("title_input_visible=True")
                if product_state.get("save_button_visible"):
                    evidence.append("save_button_visible=True")
                return _success(assertion, evidence)
            if state.get("product") == "calendar" and (
                state.get("page_type")
                in {"calendar_quick_add_modal", "calendar_quick_add_attendee"}
                or product_state.get("quick_add_visible")
            ):
                evidence = [
                    "product=calendar",
                    f"page_type={state.get('page_type')}",
                    "calendar_creation_method=time_slot_quick_add",
                ]
                if product_state.get("title_input_visible"):
                    evidence.append("title_input_visible=True")
                if product_state.get("save_button_visible"):
                    evidence.append("save_button_visible=True")
                return _success(assertion, evidence)
            return _failure(
                assertion,
                f"Calendar create surface not ready: product={state.get('product')!r}, page_type={state.get('page_type')!r}",
            )

        if assertion == "vc_home_ready":
            if state.get("product") == "vc" and (
                state.get("page_type") == "vc_home"
                or product_state.get("vc_home_visible")
            ):
                return _success(assertion, ["product=vc", "page_type=vc_home"])
            return _failure(
                assertion,
                f"VC home not ready: product={state.get('product')!r}, page_type={state.get('page_type')!r}",
            )

        if assertion == "vc_start_preview_ready":
            if state.get("page_type") == "vc_start_preview" or product_state.get(
                "start_preview_visible"
            ):
                evidence = ["page_type=vc_start_preview"]
                if product_state.get("start_button_visible"):
                    evidence.append("start_button_visible=True")
                return _success(assertion, evidence)
            return _failure(assertion, "VC start preview is not visible")

        if assertion == "vc_meeting_active":
            if state.get("page_type") == "vc_meeting_active" or product_state.get(
                "meeting_active"
            ):
                evidence = ["page_type=vc_meeting_active"]
                runtime_hint = product_state.get("runtime_semantic_hint")
                if runtime_hint:
                    evidence.append(f"runtime_semantic_hint={runtime_hint}")
                if product_state.get("invite_button_visible"):
                    evidence.append("invite_button_visible=True")
                return _success(assertion, evidence)
            return _failure(assertion, "VC meeting is not active")

        if assertion == "vc_join_preview_ready":
            if state.get("page_type") == "vc_join_preview" or product_state.get(
                "join_preview_visible"
            ):
                evidence = ["page_type=vc_join_preview"]
                if product_state.get("meeting_id_input_visible"):
                    evidence.append("meeting_id_input_visible=True")
                return _success(assertion, evidence)
            return _failure(assertion, "VC join preview is not visible")

        if assertion == "vc_meeting_id_entered":
            expected_meeting_id = (
                expected.get("meeting_id")
                or expected.get("text")
                or (expected.get("params") or {}).get("meeting_id")
                or (expected.get("payload") or {}).get("meeting_id")
            )
            actual_meeting_id = product_state.get("meeting_id")
            if expected_meeting_id and actual_meeting_id == expected_meeting_id:
                return _success(assertion, [f"meeting_id={actual_meeting_id}"])
            if expected_meeting_id and expected_meeting_id in ocr_text:
                return _success(
                    assertion,
                    [f"ocr_contains={expected_meeting_id}", "source=ocr_fallback"],
                )
            if product_state.get("meeting_id_entered"):
                return _success(assertion, ["meeting_id_entered=True"])
            return _failure(
                assertion,
                f"meeting ID not confirmed: expected={expected_meeting_id!r}, actual={actual_meeting_id!r}",
            )

        if assertion == "vc_joined":
            if state.get("page_type") == "vc_meeting_active" or product_state.get(
                "meeting_active"
            ):
                evidence = ["page_type=vc_meeting_active", "joined=True"]
                runtime_hint = product_state.get("runtime_semantic_hint")
                if runtime_hint:
                    evidence.append(f"runtime_semantic_hint={runtime_hint}")
                if product_state.get("invite_button_visible"):
                    evidence.append("invite_button_visible=True")
                return _success(assertion, evidence)
            return _failure(assertion, "VC join did not reach an active meeting")

        if assertion == "vc_invite_dialog_opened":
            if state.get("page_type") == "vc_invite_dialog" or product_state.get(
                "invite_dialog_visible"
            ):
                evidence = ["page_type=vc_invite_dialog"]
                runtime_hint = product_state.get("runtime_semantic_hint")
                if runtime_hint:
                    evidence.append(f"runtime_semantic_hint={runtime_hint}")
                if product_state.get("share_button_visible"):
                    evidence.append("share_button_visible=True")
                return _success(assertion, evidence)
            return _failure(assertion, "VC invite dialog is not visible")

        return _failure(assertion, f"unsupported assertion: {assertion}")

    def verify_step(
        self,
        expected: dict[str, Any],
        state: FeishuState,
        observation: dict[str, Any],
        runtime_context: RuntimeContext | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assertion = expected.get("assertion")
        if not assertion:
            return {
                "passed": True,
                "step_id": expected.get("step_id"),
                "assertion": None,
                "evidence": [],
                "failure_type": None,
                "failure_reason": None,
            }

        result = self.verify_assertion(
            assertion,
            state,
            observation,
            expected=expected,
            runtime_context=runtime_context,
        )
        result["step_id"] = expected.get("step_id")
        return result

    def verify_case(
        self,
        testcase: TestCase,
        runtime_context: RuntimeContext | dict[str, Any],
    ) -> dict[str, Any]:
        step_results = runtime_context.get("step_results", [])
        failed_steps = [
            result
            for result in step_results
            if result.get("verification_result", {}).get("passed") is False
        ]
        return {
            "passed": not failed_steps,
            "total_steps": len(testcase.get("steps", [])),
            "passed_steps": len(step_results) - len(failed_steps),
            "failed_steps": len(failed_steps),
            "failure_type": "verification" if failed_steps else None,
            "failure_reason": (
                failed_steps[0].get("verification_result", {}).get("failure_reason")
                if failed_steps
                else None
            ),
        }
