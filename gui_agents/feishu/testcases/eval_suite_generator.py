"""Generate the read-only Feishu eval suite manifest from structured seeds."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

from gui_agents.feishu.contracts import AssertionId

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SEED_PATH = REPO_ROOT / "tests" / "eval_suite" / "feishu_eval_suite_seed.json"
DEFAULT_MANIFEST_PATH = REPO_ROOT / "tests" / "eval_suite" / "feishu_eval_suite.json"

VALID_PRODUCTS = {"im", "docs", "calendar", "base", "vc"}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_COVERAGE = {"full", "partial", "missing"}
VALID_WINDOW_SCOPE = {"single_window", "cross_window"}
KNOWN_ASSERTIONS = set(get_args(AssertionId))
ALLOWED_TOP_LEVEL_KEYS = {
    "description",
    "generated_at",
    "products",
    "source_documents",
    "profiles",
    "case_seeds",
}
ALLOWED_PROFILE_KEYS = {
    "product",
    "assertions",
    "priority",
    "enabled",
    "verifier_coverage",
    "window_scope",
}
ALLOWED_CASE_SEED_KEYS = {
    "id",
    "profile",
    "title",
    "instruction",
    "product",
    "assertions",
    "priority",
    "enabled",
    "verifier_coverage",
    "window_scope",
    "related_products",
    "window_surfaces",
    "evidence_focus",
    "note",
}
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


def _read_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("seed payload must be a JSON object")
    return payload


def _validate_non_empty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _reject_unknown_keys(
    payload: dict[str, Any], allowed: set[str], *, field: str
) -> None:
    unexpected = sorted(key for key in payload if key not in allowed)
    if unexpected:
        raise ValueError(f"{field} contains unsupported fields: {unexpected}")


def _reject_forbidden_structure(value: Any, *, field: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = key.strip().lower() if isinstance(key, str) else str(key)
            if normalized in FORBIDDEN_SEMANTIC_KEYS:
                raise ValueError(f"{field} contains forbidden semantic field: {key}")
            child_field = f"{field}.{key}" if isinstance(key, str) else field
            _reject_forbidden_structure(nested, field=child_field)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_structure(item, field=f"{field}[{index}]")


def _validate_list_of_strings(
    value: Any,
    *,
    field: str,
    allowed: set[str] | None = None,
    allow_empty: bool = True,
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} items must be non-empty strings")
        normalized = item.strip()
        if allowed is not None and normalized not in allowed:
            raise ValueError(f"{field} contains unsupported value: {normalized}")
        items.append(normalized)
    if not allow_empty and not items:
        raise ValueError(f"{field} must not be empty")
    return items


def _validate_profile(name: str, profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise ValueError(f"profile {name} must be an object")
    _reject_unknown_keys(profile, ALLOWED_PROFILE_KEYS, field=f"profile {name}")
    product = profile.get("product")
    if product not in VALID_PRODUCTS:
        raise ValueError(f"profile {name} has invalid product: {product}")
    priority = profile.get("priority")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"profile {name} has invalid priority: {priority}")
    coverage = profile.get("verifier_coverage")
    if coverage not in VALID_COVERAGE:
        raise ValueError(f"profile {name} has invalid verifier_coverage: {coverage}")
    enabled = profile.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError(f"profile {name} enabled must be boolean")
    window_scope = profile.get("window_scope", "single_window")
    if window_scope not in VALID_WINDOW_SCOPE:
        raise ValueError(f"profile {name} has invalid window_scope: {window_scope}")
    assertions = _validate_list_of_strings(
        profile.get("assertions", []),
        field=f"profile {name}.assertions",
        allowed=KNOWN_ASSERTIONS,
    )
    return {
        "product": product,
        "priority": priority,
        "enabled": enabled,
        "verifier_coverage": coverage,
        "window_scope": window_scope,
        "assertions": assertions,
    }


def load_eval_suite_seed(path: str | Path = DEFAULT_SEED_PATH) -> dict[str, Any]:
    return load_eval_suite_seed_from_payload(_read_json(path))


def _validate_case_seed(seed: Any) -> dict[str, Any]:
    if not isinstance(seed, dict):
        raise ValueError("case seed must be an object")
    case_id = seed.get("id", "unknown")
    field_name = f"case seed {case_id}" if isinstance(case_id, str) else "case seed"
    _reject_unknown_keys(seed, ALLOWED_CASE_SEED_KEYS, field=field_name)
    for field in ("id", "profile", "title", "instruction"):
        _validate_non_empty_string(seed.get(field), field=f"{field_name}.{field}")
    return seed


def _build_case(seed: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    product = seed.get("product", profile["product"])
    priority = seed.get("priority", profile["priority"])
    coverage = seed.get("verifier_coverage", profile["verifier_coverage"])

    if product is not None:
        product = _validate_non_empty_string(product, field=f"{seed['id']}.product")
    if priority is not None:
        priority = _validate_non_empty_string(priority, field=f"{seed['id']}.priority")
    if coverage is not None:
        coverage = _validate_non_empty_string(
            coverage, field=f"{seed['id']}.verifier_coverage"
        )

    case = {
        "id": seed["id"].strip(),
        "product": product,
        "title": seed["title"].strip(),
        "instruction": seed["instruction"].strip(),
        "assertions": list(seed.get("assertions", profile["assertions"])),
        "priority": priority,
        "enabled": seed.get("enabled", profile["enabled"]),
        "verifier_coverage": coverage,
    }

    window_scope = seed.get("window_scope", profile.get("window_scope"))
    if window_scope is not None:
        window_scope = _validate_non_empty_string(
            window_scope,
            field=f"{case['id']}.window_scope",
        )
    if window_scope == "cross_window":
        case["window_scope"] = "cross_window"
        for field in ("related_products", "window_surfaces", "evidence_focus"):
            case[field] = _validate_list_of_strings(
                seed.get(field, []),
                field=f"{case['id']}.{field}",
                allowed=VALID_PRODUCTS if field == "related_products" else None,
                allow_empty=False,
            )
        note = seed.get("note")
        if not isinstance(note, str) or not note.strip():
            raise ValueError(f"{case['id']}.note is required for cross_window cases")
        case["note"] = note.strip()
    elif window_scope not in {None, "single_window"}:
        raise ValueError(f"{case['id']} has invalid window_scope: {window_scope}")
    else:
        cross_window_only_fields = {
            "related_products",
            "window_surfaces",
            "evidence_focus",
            "note",
        }
        unexpected = sorted(
            field for field in cross_window_only_fields if field in seed
        )
        if unexpected:
            raise ValueError(
                f"{case['id']} defines cross_window-only fields without cross_window scope: {unexpected}"
            )

    if case["product"] not in VALID_PRODUCTS:
        raise ValueError(f"{case['id']} has invalid product: {case['product']}")
    if case["priority"] not in VALID_PRIORITIES:
        raise ValueError(f"{case['id']} has invalid priority: {case['priority']}")
    if not isinstance(case["enabled"], bool):
        raise ValueError(f"{case['id']} enabled must be boolean")
    if case["verifier_coverage"] not in VALID_COVERAGE:
        raise ValueError(
            f"{case['id']} has invalid verifier_coverage: {case['verifier_coverage']}"
        )
    case["assertions"] = _validate_list_of_strings(
        case["assertions"],
        field=f"{case['id']}.assertions",
        allowed=KNOWN_ASSERTIONS,
    )

    serialized = json.dumps(case, ensure_ascii=False).lower()
    for forbidden in FORBIDDEN_SEMANTIC_KEYS:
        if forbidden in serialized:
            raise ValueError(
                f"{case['id']} contains forbidden semantic token: {forbidden}"
            )

    if case.get("window_scope") == "cross_window":
        related_products = case["related_products"]
        if len(set(related_products)) < 2:
            raise ValueError(
                f"{case['id']} cross_window related_products must include at least two products"
            )
        if case["product"] not in related_products:
            raise ValueError(
                f"{case['id']} cross_window related_products must include target product"
            )
    return case


def build_eval_suite_manifest(seed_payload: dict[str, Any]) -> dict[str, Any]:
    payload = load_eval_suite_seed_from_payload(seed_payload)
    seen_ids: set[str] = set()
    cases: list[dict[str, Any]] = []

    for raw_seed in payload["case_seeds"]:
        seed = _validate_case_seed(raw_seed)
        profile_name = seed["profile"].strip()
        if profile_name not in payload["profiles"]:
            raise ValueError(f"{seed['id']} references unknown profile: {profile_name}")
        case = _build_case(seed, payload["profiles"][profile_name])
        if case["id"] in seen_ids:
            raise ValueError(f"duplicate case id: {case['id']}")
        seen_ids.add(case["id"])
        cases.append(case)

    return {
        "$schema": "feishu_eval_suite.schema.json",
        "description": payload["description"],
        "generated_at": payload["generated_at"],
        "products": payload["products"],
        "test_cases": cases,
    }


def load_eval_suite_seed_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    required = {"description", "generated_at", "products", "profiles", "case_seeds"}
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"seed missing required fields: {sorted(missing)}")
    _reject_unknown_keys(payload, ALLOWED_TOP_LEVEL_KEYS, field="seed")
    _reject_forbidden_structure(payload, field="seed")

    validated = {
        "description": _validate_non_empty_string(
            payload["description"],
            field="seed.description",
        ),
        "generated_at": _validate_non_empty_string(
            payload["generated_at"],
            field="seed.generated_at",
        ),
        "products": _validate_list_of_strings(
            payload["products"],
            field="products",
            allowed=VALID_PRODUCTS,
            allow_empty=False,
        ),
        "source_documents": _validate_list_of_strings(
            payload.get("source_documents", []),
            field="source_documents",
        ),
        "profiles": {},
        "case_seeds": payload["case_seeds"],
    }

    profiles_raw = payload["profiles"]
    if not isinstance(profiles_raw, dict) or not profiles_raw:
        raise ValueError("profiles must be a non-empty object")
    for name, profile in profiles_raw.items():
        validated["profiles"][name] = _validate_profile(name, profile)

    case_seeds = payload["case_seeds"]
    if not isinstance(case_seeds, list) or not case_seeds:
        raise ValueError("case_seeds must be a non-empty list")
    return validated


def generate_eval_suite_manifest(
    seed_path: str | Path = DEFAULT_SEED_PATH,
) -> dict[str, Any]:
    return build_eval_suite_manifest(load_eval_suite_seed(seed_path))


def write_eval_suite_manifest(
    output_path: str | Path = DEFAULT_MANIFEST_PATH,
    *,
    seed_path: str | Path = DEFAULT_SEED_PATH,
) -> dict[str, Any]:
    manifest = generate_eval_suite_manifest(seed_path)
    path = Path(output_path)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def manifest_matches_file(
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    *,
    seed_path: str | Path = DEFAULT_SEED_PATH,
) -> bool:
    expected = generate_eval_suite_manifest(seed_path)
    actual = _read_json(manifest_path)
    return expected == actual
