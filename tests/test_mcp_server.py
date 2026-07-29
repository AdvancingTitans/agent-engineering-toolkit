from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aet.bundle import validate_bundle
from aet.atlas.storage import build_evidence_atlas
from aet.mcp_server import (
    MCP_PROTOCOL_VERSION,
    call_tool,
    handle_request,
    serve_stdio,
)

from tests.test_evidence_bundle_compiler import _minimal_payload
from tests.test_evidence_bundle_protocol import (
    _copy_minimal,
    _make_truncated,
)
from tests.test_portable_investigation import _request
from tests.test_review_validator import _review


TESTS = Path(__file__).parent
MINIMAL_BUNDLE = TESTS / "fixtures" / "evidence-bundles" / "minimal"
NATIVE_RUN = (
    TESTS
    / "fixtures"
    / "run-normalization"
    / "codex"
    / "complete.jsonl"
)

EXPECTED_TOOLS = {
    "aet_run_normalize",
    "aet_investigation_create",
    "aet_investigation_get",
    "aet_bundle_create",
    "aet_bundle_get_index",
    "aet_bundle_get_claim",
    "aet_bundle_get_evidence",
    "aet_bundle_get_blob",
    "aet_bundle_validate_review",
    "aet_graph_list_perspectives",
    "aet_graph_get_root",
    "aet_graph_get_node",
    "aet_graph_get_children",
    "aet_graph_trace_claim",
    "aet_graph_trace_conflict",
    "aet_graph_trace_freshness",
    "aet_graph_render_mermaid",
}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rpc(method: str, *, identifier: int = 1, params: Any = None) -> dict[str, Any]:
    request: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": identifier,
        "method": method,
    }
    if params is not None:
        request["params"] = params
    response = handle_request(request)
    if response is None:
        raise AssertionError("测试请求必须产生响应")
    return response


def _tool_request(
    name: str,
    arguments: dict[str, Any],
    *,
    identifier: int = 1,
) -> dict[str, Any]:
    return _rpc(
        "tools/call",
        identifier=identifier,
        params={"name": name, "arguments": arguments},
    )


class McpServerTests(unittest.TestCase):
    def test_initialize_and_tools_list_expose_only_bounded_tools(self) -> None:
        initialized = _rpc(
            "initialize",
            params={
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "fixture", "version": "1"},
            },
        )
        self.assertEqual(
            MCP_PROTOCOL_VERSION,
            initialized["result"]["protocolVersion"],
        )
        self.assertEqual(
            "agent-engineering-toolkit",
            initialized["result"]["serverInfo"]["name"],
        )

        listed = _rpc("tools/list")
        tools = listed["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertEqual(EXPECTED_TOOLS, names)
        self.assertTrue(
            all(
                tool["inputSchema"]["additionalProperties"] is False
                for tool in tools
            )
        )
        self.assertFalse(
            any(
                marker in name
                for name in names
                for marker in ("fix", "repair", "execute", "command", "merge")
            )
        )

    def test_unknown_method_and_tool_errors_use_json_rpc_boundaries(self) -> None:
        unknown_method = _rpc("unsupported/method", identifier=9)
        self.assertEqual(-32601, unknown_method["error"]["code"])
        self.assertEqual(9, unknown_method["id"])

        unknown_tool = _tool_request("aet_unknown_tool", {}, identifier=10)
        result = unknown_tool["result"]
        self.assertTrue(result["isError"])
        self.assertNotIn("structuredContent", result)
        self.assertEqual("text", result["content"][0]["type"])

        bad_arguments = _tool_request(
            "aet_bundle_get_index",
            {"unexpected": True},
            identifier=11,
        )
        self.assertTrue(bad_arguments["result"]["isError"])

    def test_duplicate_json_keys_fail_closed(self) -> None:
        source = io.StringIO(
            '{"jsonrpc":"2.0","id":1,"method":"ping","method":"tools/list"}\n'
        )
        destination = io.StringIO()
        serve_stdio(source, destination)
        responses = destination.getvalue().splitlines()
        self.assertEqual(1, len(responses))
        response = json.loads(responses[0])
        self.assertEqual(-32700, response["error"]["code"])
        self.assertIn("duplicate JSON key", response["error"]["message"])

    def test_bundle_get_index_claim_evidence_and_blob(self) -> None:
        index = call_tool(
            "aet_bundle_get_index",
            {"bundle": str(MINIMAL_BUNDLE)},
        )
        self.assertEqual("bundle-fixture-001", index["bundle_id"])

        claim = call_tool(
            "aet_bundle_get_claim",
            {
                "bundle": str(MINIMAL_BUNDLE),
                "claim_id": "claim-001",
            },
        )
        self.assertEqual("claim-001", claim["id"])

        evidence = call_tool(
            "aet_bundle_get_evidence",
            {
                "bundle": str(MINIMAL_BUNDLE),
                "evidence_id": "ev-001",
            },
        )
        self.assertEqual("ev-001", evidence["id"])

        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "blob-bundle")
            blob_path = _make_truncated(bundle)
            blob_ref = blob_path.relative_to(bundle).as_posix()
            blob = call_tool(
                "aet_bundle_get_blob",
                {"bundle": str(bundle), "blob_ref": blob_ref},
            )
            raw = blob_path.read_bytes()
            self.assertEqual(len(raw), blob["bytes"])
            self.assertEqual(
                raw,
                base64.b64decode(blob["content_base64"]),
            )

    def test_bundle_validate_review_returns_structured_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            review_path = Path(temporary) / "review.json"
            _write_json(review_path, _review())
            report = call_tool(
                "aet_bundle_validate_review",
                {
                    "bundle": str(MINIMAL_BUNDLE),
                    "review": str(review_path),
                },
            )
            self.assertEqual("PASS", report["status"])
            self.assertEqual("bundle-fixture-001", report["bundle_id"])

    def test_graph_tools_validate_sidecar_and_enforce_query_budgets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            atlas = Path(temporary) / "minimal.atlas"
            build_evidence_atlas(MINIMAL_BUNDLE, output=atlas)
            common = {
                "atlas": str(atlas),
                "bundle": str(MINIMAL_BUNDLE),
            }
            perspectives = call_tool(
                "aet_graph_list_perspectives",
                common,
            )
            self.assertEqual(10, len(perspectives["perspectives"]))

            roots = call_tool(
                "aet_graph_get_root",
                {**common, "perspective": "claim-chain"},
            )
            claim = next(
                node for node in roots["roots"] if node["type"] == "claim"
            )
            resolved = call_tool(
                "aet_graph_get_node",
                {**common, "node_id": claim["id"]},
            )
            self.assertEqual(claim["id"], resolved["id"])

            traced = call_tool(
                "aet_graph_trace_claim",
                {**common, "claim_id": "claim-001", "max_nodes": 25},
            )
            self.assertTrue(traced["nodes"])
            rendered = call_tool(
                "aet_graph_render_mermaid",
                {**common, "perspective": "claim-chain"},
            )
            self.assertTrue(rendered["mermaid"].startswith("flowchart "))

            rejected = _tool_request(
                "aet_graph_trace_claim",
                {**common, "claim_id": "claim-001", "max_nodes": 201},
            )
            self.assertTrue(rejected["result"]["isError"])

    def test_run_normalize_refuses_overwrite_and_reports_tool_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "normalized"
            arguments = {
                "source": "codex",
                "input": str(NATIVE_RUN),
                "output": str(output),
                "run_group_id": "run-mcp-001",
            }
            first = _tool_request("aet_run_normalize", arguments)
            self.assertFalse(first["result"]["isError"])
            self.assertTrue((output / "records.jsonl").is_file())
            before = {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }

            second = _tool_request("aet_run_normalize", arguments)
            self.assertTrue(second["result"]["isError"])
            after = {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)

    def test_investigation_create_is_read_only_and_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            normalized = root / "normalized"
            call_tool(
                "aet_run_normalize",
                {
                    "source": "codex",
                    "input": str(NATIVE_RUN),
                    "output": str(normalized),
                    "run_group_id": "run-observation-fixture",
                },
            )
            request_path = root / "request.json"
            output = root / "investigation.json"
            _write_json(request_path, _request())

            result = call_tool(
                "aet_investigation_create",
                {
                    "request": str(request_path),
                    "run": str(normalized),
                    "output": str(output),
                },
            )
            self.assertEqual("unknown", result["status"])
            self.assertEqual([], result["verified_evidence"])
            self.assertTrue(result["policy"]["workspace_policy"]["read_only"])
            self.assertFalse(
                result["policy"]["command_policy"]["allow_execution"]
            )
            self.assertEqual(
                result,
                call_tool(
                    "aet_investigation_get",
                    {"investigation": str(output)},
                ),
            )

    def test_investigation_get_rejects_forged_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            forged = Path(temporary) / "forged.json"
            _write_json(
                forged,
                {
                    "status": "supported",
                    "verified_evidence": ["unvalidated"],
                },
            )
            response = _tool_request(
                "aet_investigation_get",
                {"investigation": str(forged)},
            )
            self.assertTrue(response["result"]["isError"])
            with self.assertRaises(Exception):
                call_tool(
                    "aet_investigation_get",
                    {"investigation": str(forged)},
                )

    def test_bundle_create_accepts_complete_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = _minimal_payload()
            payload_path = root / "payload.json"
            output = root / "bundle"
            _write_json(payload_path, payload)

            created = call_tool(
                "aet_bundle_create",
                {
                    "payload": str(payload_path),
                    "output": str(output),
                },
            )
            self.assertEqual("bundle-fixture-001", created["bundle_id"])
            self.assertEqual(str(output), created["output"])
            bundle = validate_bundle(output)
            self.assertEqual(payload["claims"], bundle["claims"])
            self.assertEqual(payload["evidence"], bundle["evidence"])
            self.assertEqual(payload["observations"], bundle["observations"])
            self.assertEqual(payload["sources"], bundle["sources"])
            self.assertEqual(payload["ledger"], bundle["ledger"])
            self.assertEqual(payload["policy"], bundle["policy"])

    def test_stdio_emits_one_line_per_non_notification_request(self) -> None:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {},
            },
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        ]
        source = io.StringIO(
            "".join(
                json.dumps(item, separators=(",", ":")) + "\n"
                for item in requests
            )
        )
        destination = io.StringIO()
        serve_stdio(source, destination)

        lines = destination.getvalue().splitlines()
        self.assertEqual(3, len(lines))
        responses = [json.loads(line) for line in lines]
        self.assertEqual([1, 2, 3], [item["id"] for item in responses])
        self.assertTrue(all(item["jsonrpc"] == "2.0" for item in responses))


if __name__ == "__main__":
    unittest.main()
