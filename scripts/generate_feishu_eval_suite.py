from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gui_agents.feishu.testcases.eval_suite_generator import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SEED_PATH,
    generate_eval_suite_manifest,
    manifest_matches_file,
    write_eval_suite_manifest,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the read-only Feishu eval suite manifest."
    )
    parser.add_argument(
        "--seed",
        default=str(DEFAULT_SEED_PATH),
        help="Path to eval suite seed JSON.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_MANIFEST_PATH),
        help="Path to write generated manifest JSON.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the checked-in manifest does not match generated output.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    seed_path = Path(args.seed)
    output_path = Path(args.output)

    if args.check:
        if manifest_matches_file(output_path, seed_path=seed_path):
            print(f"FEISHU_EVAL_SUITE_CHECK_OK: {output_path}")
            return 0
        print(f"FEISHU_EVAL_SUITE_CHECK_FAILED: {output_path}")
        return 1

    manifest = write_eval_suite_manifest(output_path, seed_path=seed_path)
    print(f"FEISHU_EVAL_SUITE_WRITTEN: {output_path}")
    print(f"FEISHU_EVAL_SUITE_CASES: {len(manifest.get('test_cases', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
