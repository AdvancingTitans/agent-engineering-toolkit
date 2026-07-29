"""Build three deterministic Evidence-Guided Planner end-to-end examples."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import shutil
import tempfile
from pathlib import Path
from typing import Any

from aet.atlas import build_evidence_atlas
from aet.bundle import compile_bundle
from aet.planning.candidate_parser import parse_candidate
from aet.planning.context_builder import build_planning_context
from aet.planning.handoff import build_verification_handoff_from_package
from aet.planning.models import canonical_json_bytes
from aet.planning.package_builder import build_plan_package
from aet.planning.request_normalizer import RequestOverrides, normalize_request
from aet.planning.skill_exporter import export_plan_skill
from aet.planning.validator import validate_plan_candidate


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
IMPROVEMENT_IMPLEMENTATION = (
    "examples/evidence-grounded-improvement/sample_project/tool_result.py"
)
IMPROVEMENT_TEST = (
    "examples/evidence-grounded-improvement/sample_project/test_tool_result.py"
)
ATLAS_PATHS = [
    "src/aet/atlas/builder.py",
    "src/aet/atlas/perspectives.py",
    "src/aet/atlas/viewer.py",
    "schemas/evidence-bundle/v1/evidence.schema.json",
]


def build_examples(output: Path) -> dict[str, Any]:
    destination = Path(output).expanduser().resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        inputs = temporary / "inputs"
        improvement_bundle = inputs / "improvement-bundle"
        atlas_bundle = inputs / "atlas-self-review-bundle"
        compile_bundle(
            _example_payload(
                "examples/evidence-grounded-improvement/build_example.py"
            ),
            improvement_bundle,
        )
        compile_bundle(
            _example_payload("examples/evidence-atlas/build_example.py"),
            atlas_bundle,
        )
        improvement_atlas = Path(
            build_evidence_atlas(improvement_bundle)["output"]
        )
        atlas_atlas = Path(build_evidence_atlas(atlas_bundle)["output"])
        summaries = [
            _build_scenario(
                temporary,
                name="single-file",
                request_text=(
                    "Correct the empty tool-result adapter without weakening "
                    "the recorded regression."
                ),
                bundle=improvement_bundle,
                atlas=improvement_atlas,
                allowed_paths=[
                    IMPROVEMENT_IMPLEMENTATION,
                    IMPROVEMENT_TEST,
                ],
                verification=[
                    f"python {IMPROVEMENT_TEST}",
                ],
                candidate_name="single-file.json",
                diff=_diff_for([IMPROVEMENT_IMPLEMENTATION]),
            ),
            _build_scenario(
                temporary,
                name="cross-module",
                request_text=(
                    "Plan a bounded Graph Builder, fixed Perspective, recursive "
                    "Viewer, and Bundle v1 Change Group compatibility change."
                ),
                bundle=atlas_bundle,
                atlas=atlas_atlas,
                allowed_paths=ATLAS_PATHS,
                verification=[
                    "python -m unittest tests.test_evidence_atlas_builder "
                    "tests.test_evidence_atlas_protocol"
                ],
                candidate_name="cross-module.json",
                diff=_diff_for(ATLAS_PATHS[:3]),
            ),
            _build_scenario(
                temporary,
                name="needs-evidence",
                request_text=(
                    "Refactor every permission decision in the repository and "
                    "guarantee that no implementation point is omitted."
                ),
                bundle=improvement_bundle,
                atlas=improvement_atlas,
                allowed_paths=[],
                verification=[],
                candidate_name="needs-evidence.json",
                diff="",
            ),
        ]
        result = {
            "schema_version": "evidence-guided-planner-example/1.0",
            "status": "PASS",
            "authority": "PROPOSED",
            "scenarios": summaries,
        }
        (temporary / "summary.json").write_bytes(canonical_json_bytes(result))
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return result


def _build_scenario(
    root: Path,
    *,
    name: str,
    request_text: str,
    bundle: Path,
    atlas: Path,
    allowed_paths: list[str],
    verification: list[str],
    candidate_name: str,
    diff: str,
) -> dict[str, Any]:
    scenario = root / name
    scenario.mkdir(parents=True)
    request = normalize_request(
        request_text,
        workspace=ROOT,
        explicit=RequestOverrides(
            allowed_paths=allowed_paths,
            required_verification=verification,
        ),
    )
    context = build_planning_context(
        request,
        workspace=ROOT,
        bundle_path=bundle,
        atlas_path=atlas,
    )
    context_path = scenario / "planning-context.json"
    context_path.write_bytes(canonical_json_bytes(context))
    candidate_value = _candidate(candidate_name, context.request.request_id)
    candidate_path = scenario / "frozen-candidate.json"
    candidate_path.write_bytes(canonical_json_bytes(candidate_value))
    candidate = parse_candidate(candidate_path.read_bytes())
    result = validate_plan_candidate(context, candidate)
    package = build_plan_package(context, result, scenario / "plan")
    export_plan_skill(
        package,
        scenario / "exported-skill",
        target="generic",
    )
    diff_path = scenario / "external.diff"
    diff_path.write_text(diff, encoding="utf-8", newline="\n")
    handoff = build_verification_handoff_from_package(package, diff)
    (scenario / "verification-request.json").write_bytes(
        canonical_json_bytes(handoff)
    )
    return {
        "name": name,
        "request_id": context.request.request_id,
        "plan_id": result.plan["plan_id"],
        "plan_status": result.status,
        "gap_count": len(context.gaps),
        "edit_count": len(result.plan["edit_items"]),
        "verification_status": handoff["verification_status"],
        "unplanned_paths": handoff["unplanned_paths"],
    }


def _example_payload(relative: str) -> dict[str, Any]:
    namespace = runpy.run_path(str(ROOT / relative))
    payload = namespace.get("payload")
    if not callable(payload):
        raise RuntimeError(f"example does not expose payload(): {relative}")
    return payload()


def _candidate(name: str, request_id: str) -> dict[str, Any]:
    value = json.loads(
        (HERE / "frozen-candidates" / name).read_text(encoding="utf-8")
    )
    if value.get("request_id") != "$REQUEST_ID":
        raise RuntimeError(f"frozen Candidate binding is invalid: {name}")
    value["request_id"] = request_id
    return value


def _diff_for(paths: list[str]) -> str:
    return "".join(
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        "-before\n"
        "+after\n"
        for path in paths
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build_examples(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
