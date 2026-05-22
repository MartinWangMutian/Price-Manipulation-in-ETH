#!/usr/bin/env python3
"""Generate a manifest of local project artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXCLUDED_ARTIFACTS = {
    "config/ops_contacts.local.json",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def files_under(root: Path, pattern: str) -> list[str]:
    return sorted(str(path) for path in root.glob(pattern) if path.is_file())


def recursive_files(root: Path, subdir: str, suffix: str | None = None) -> list[str]:
    base = root / subdir
    if not base.exists():
        return []
    paths = [path for path in base.rglob("*") if path.is_file()]
    if suffix is not None:
        paths = [path for path in paths if path.name.endswith(suffix)]
    relative_paths = [str(path.relative_to(root)) for path in paths]
    return sorted(path for path in relative_paths if path not in EXCLUDED_ARTIFACTS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate artifact manifest.")
    parser.add_argument("--out", default="ops/reports/artifact-manifest.latest.json")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the full manifest. The output file always contains the full manifest.",
    )
    args = parser.parse_args()

    root = Path.cwd()
    categories = {
        "config": recursive_files(root, "config", ".json"),
        "schemas": recursive_files(root, "schemas", ".json"),
        "scripts": recursive_files(root, "scripts", ".py"),
        "runbooks_and_reports_docs": recursive_files(root, "ops", ".md"),
        "reports": recursive_files(root, "ops/reports", ".json"),
        "replay": recursive_files(root, "data/replay", ".json"),
        "training": recursive_files(root, "data/training", ".json"),
        "rag": recursive_files(root, "data/rag", ".json"),
        "console": recursive_files(root, "data/console", ".json"),
        "evaluation": recursive_files(root, "data/evaluation", ".json"),
    }
    manifest = {
        "generated_at": now_iso(),
        "categories": categories,
        "counts": {name: len(paths) for name, paths in categories.items()},
        "excluded_artifacts": sorted(EXCLUDED_ARTIFACTS),
        "status_files": [
            "config/phase_b_scope.json",
            "ops/reports/project-status.latest.json",
            "ops/reports/go-no-go-audit.latest.json",
            "ops/reports/validation-metrics-audit.latest.json",
            "ops/reports/required-inputs-check.latest.json",
            "ops/reports/ops-contacts-bootstrap.latest.json",
            "ops/reports/env-local-audit.latest.json",
            "ops/reports/provider-trace-capability-probe.latest.json",
            "ops/reports/provider-trace-capability-probe.plan.json",
            "ops/reports/report-secret-audit.latest.json",
            "ops/reports/replay-label-candidates-check.latest.json",
            "ops/reports/trace-replay-queue-builder.latest.json",
            "ops/reports/trace-endpoint-preflight.plan.json",
            "ops/reports/trace-endpoint-preflight.latest.json",
            "ops/reports/historical-trace-replay.latest.json",
            "ops/reports/historical-trace-results-audit.latest.json",
            "ops/reports/normal-replay-candidates-check.latest.json",
            "ops/reports/normal-historical-trace-replay.latest.json",
            "ops/reports/normal-replay-candidates-builder.latest.json",
            "ops/reports/label-readiness-audit.latest.json",
            "ops/reports/label-promotion-audit.latest.json",
            "ops/reports/label-promotion-template-builder.latest.json",
            "ops/reports/training-dataset-check.latest.json",
            "ops/reports/phase-b-completion-audit.latest.json",
            "ops/reports/phase-b-next-action.latest.json",
            "ops/reports/phase-b-refresh.latest.json",
            "ops/reports/artifact-manifest.latest.json",
            "ops/status_summary.md",
            "ops/course_submission_summary.md",
            "ops/phase_b_completion_checklist.md",
            "ops/phase_b_handoff.md",
            "ops/trace_endpoint_application_guide.md",
            "ops/main_trace_endpoint_preflight_runbook.md",
            "ops/phase_b_user_action_packet.md",
            "ops/blocker_register.md",
            "ops/command_index.md",
        ],
    }
    write_json(root / args.out, manifest)
    stdout_payload = manifest if args.verbose else {
        "generated_at": manifest["generated_at"],
        "out": args.out,
        "counts": manifest["counts"],
        "status_files": manifest["status_files"],
    }
    print(json.dumps(stdout_payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
