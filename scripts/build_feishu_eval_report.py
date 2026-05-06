from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gui_agents.feishu.reports.evaluation_aggregator import write_evaluation_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Feishu batch evaluation report."
    )
    parser.add_argument(
        "--artifact-root",
        default="artifacts/test_runs",
        help="Directory containing per-run summary.json artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/evaluation",
        help="Directory for aggregate evaluation outputs.",
    )
    args = parser.parse_args()

    paths = write_evaluation_report(args.artifact_root, args.output_dir)
    print(f"FEISHU_EVALUATION_SUMMARY: {paths['evaluation_summary']}")
    print(f"FEISHU_EVALUATION_REPORT: {paths['evaluation_report']}")
    print(f"FEISHU_EVALUATION_DASHBOARD: {paths['evaluation_dashboard']}")
    print(f"FEISHU_LIVE_E2E_EVIDENCE: {paths['live_e2e_evidence']}")
    print(f"FEISHU_LIVE_E2E_REPORT: {paths['live_e2e_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
