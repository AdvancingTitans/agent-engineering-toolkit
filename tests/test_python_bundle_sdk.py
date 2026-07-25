from __future__ import annotations

import hashlib
import unittest
import tempfile
from pathlib import Path

from aet.bundle import BundleError
from aet.bundle import manifest_content_hash
from aet_bundle import (
    load_bundle,
    query_claims,
    query_evidence,
    read_blob,
    render_prompt_context,
    resolve_source,
    validate_bundle,
)
from tests.test_evidence_bundle_protocol import _copy_minimal, _make_truncated


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "evidence-bundles"
    / "minimal"
)


class PythonBundleSdkTests(unittest.TestCase):
    def test_load_query_and_prompt_context_are_read_only(self) -> None:
        bundle = validate_bundle(FIXTURE)
        self.assertEqual(bundle["manifest"], load_bundle(FIXTURE)["manifest"])
        self.assertEqual(["claim-001"], [item["id"] for item in query_claims(bundle)])
        self.assertEqual(
            ["ev-001"],
            [
                item["id"]
                for item in query_evidence(
                    bundle,
                    strength="reproduced",
                    freshness="current",
                )
            ],
        )
        source = resolve_source(bundle, bundle["evidence"][0]["source_refs"][0])
        self.assertEqual("proof_receipt", source["type"])
        context = render_prompt_context(bundle)
        self.assertIn('"claims"', context)
        self.assertNotIn('"blobs"', context)

    def test_blob_and_budget_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle_path = _copy_minimal(Path(temporary), "blob-bundle")
            blob_path = _make_truncated(bundle_path)
            bundle = validate_bundle(bundle_path)
            blob_ref = blob_path.relative_to(bundle_path).as_posix()
            original = blob_path.read_bytes()
            self.assertEqual(original, read_blob(bundle, blob_ref))
            bundle["blobs"][blob_ref] = b"tampered"
            forged_hash = hashlib.sha256(b"tampered").hexdigest()
            forged_ref = f"blobs/sha256-{forged_hash}"
            bundle["blobs"] = {forged_ref: b"tampered"}
            bundle["manifest"]["integrity"]["file_hashes"].pop(blob_ref)
            bundle["manifest"]["integrity"]["file_hashes"][forged_ref] = forged_hash
            bundle["manifest"]["bundle"]["content_hash"] = manifest_content_hash(
                bundle["manifest"]
            )
            with self.assertRaises(BundleError):
                read_blob(bundle, forged_ref)
            self.assertEqual(original, read_blob(bundle_path, blob_ref))
        with self.assertRaises(BundleError):
            read_blob(bundle, "blobs/sha256-" + "0" * 64)
        with self.assertRaises(BundleError):
            render_prompt_context(bundle, max_bytes=1)


if __name__ == "__main__":
    unittest.main()
