import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agi_trading import verification as v
from agi_trading.providers.bybit.adapter import Bybit
from agi_trading.providers.native import run
from agi_trading.runtime import bootstrap
from agi_trading.security import TradingError, runtime_environment


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        (self.root / "agi_trading").mkdir()
        (self.root / "agi_trading/__init__.py").write_text("# fixture\n")
        (self.root / ".gitignore").write_text("node_modules/\n.runtime/\n__pycache__/\n")
        for args in (["init", "-q"], ["add", "."], ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "Fixture"]):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        for target, value in (("agi_trading.verification.ROOT", self.root),):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.state = Path(self.tmp.name) / "state"
        env = patch.dict(os.environ, {"AGI_TRADING_STATE_DIR": str(self.state)})
        env.start()
        self.addCleanup(env.stop)
        self.report_file = Path(self.tmp.name) / "report.json"

    def report(self, recommendation="approve", score=5):
        snapshot = v.snapshot()
        return {"schema": 1, **{k: snapshot[k] for k in ("commit", "source_sha256", "runtime_sha256")},
                "reviewer": "Fixture user agent", "reviewer_relationship": "user_agent",
                "reviewed_at": int(time.time()), "recommendation": recommendation, "score": score,
                "checks": {k: {"result": "pass", "evidence": "Fixture-specific reviewed evidence"} for k in v.CHECKS},
                "findings": [], "improvements": ["Testnet validation remains necessary"],
                "limitations": ["No independent identity authentication"], "scope": "Fixture source and offline tests only"}

    def save(self, report):
        self.report_file.write_text(json.dumps(report))
        return v.import_review(self.report_file)

    def test_missing_review_blocks_before_key_access_and_http(self):
        with patch("agi_trading.providers.bybit.adapter.require_env") as keys, patch("agi_trading.transport.Transport.request") as network:
            with self.assertRaisesRegex(TradingError, "Security review required"):
                Bybit().balances()
            keys.assert_not_called()
            network.assert_not_called()

    def test_missing_review_blocks_native_process(self):
        with patch("agi_trading.providers.native.executable") as executable:
            with self.assertRaisesRegex(TradingError, "Security review required"):
                run("binance", "baw", ["wallet", "status"])
            executable.assert_not_called()

    def test_missing_review_blocks_installer(self):
        with patch("agi_trading.runtime.subprocess.run") as process:
            with self.assertRaisesRegex(TradingError, "Security review required"):
                bootstrap("binance")
            process.assert_not_called()

    def test_low_rating_is_accepted_if_reviewer_approves_scope(self):
        self.assertTrue(self.save(self.report(score=3))["operations_allowed"])
        self.assertEqual(v.require_review()["score"], 3)

    def test_negative_review_is_preserved_and_blocks_operations(self):
        self.assertFalse(self.save(self.report("reject", 1))["operations_allowed"])
        with self.assertRaisesRegex(TradingError, "does not approve"):
            v.require_review()

    def test_unresolved_high_finding_blocks_even_high_score(self):
        report = self.report(score=10)
        report["findings"] = [{"severity": "high", "resolved": False, "description": "A concrete unresolved high risk"}]
        self.assertFalse(self.save(report)["operations_allowed"])

    def test_unreviewed_category_cannot_unlock(self):
        report = self.report()
        report["checks"]["dependencies"]["result"] = "not_reviewed"
        self.assertFalse(self.save(report)["operations_allowed"])

    def test_source_edit_invalidates_existing_review(self):
        self.save(self.report())
        (self.root / "agi_trading/__init__.py").write_text("# changed\n")
        with self.assertRaisesRegex(TradingError, "stale"):
            v.require_review()

    def test_ignored_untracked_python_is_still_fingerprinted(self):
        self.save(self.report())
        (self.root / ".git/info/exclude").write_text("ignored.py\n")
        (self.root / "agi_trading/ignored.py").write_text("# injected\n")
        with self.assertRaisesRegex(TradingError, "stale"):
            v.require_review()

    def test_installing_or_modifying_runtime_requires_new_review(self):
        self.save(self.report())
        location = self.root / "agi_trading/providers/okx/.runtime"
        location.mkdir(parents=True)
        (location / "onchainos").write_bytes(b"fixture binary")
        with self.assertRaisesRegex(TradingError, "stale"):
            v.require_review()

    def test_receipt_expires(self):
        self.save(self.report())
        with patch("agi_trading.verification.time.time", return_value=time.time() + v.TTL + 1):
            with self.assertRaisesRegex(TradingError, "older than"):
                v.require_review()

    def test_placeholder_template_cannot_be_used_as_review(self):
        with self.assertRaises(TradingError):
            self.save(v.template())

    def test_report_and_receipt_are_private_and_local(self):
        self.save(self.report())
        self.assertEqual(v.state_file().stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.root, v.state_file().parents)

    def test_duplicate_json_keys_are_rejected(self):
        self.report_file.write_text('{"schema": 1, "schema": 2}')
        with self.assertRaisesRegex(TradingError, "Duplicate"):
            v.read_json(self.report_file)

    def test_attestation_is_an_unsigned_commitment_not_a_certificate(self):
        self.save(self.report("reject", 2))
        result = v.attestation(self.report_file)
        self.assertFalse(result["claims"]["safety_certified"])
        self.assertFalse(result["claims"]["anchored_onchain"])
        self.assertEqual(result["recommendation"], "reject")
        self.assertTrue(result["anchor_payload"].startswith("AGI-TRADING-REVIEW:v1:"))

    def test_feedback_never_publishes_or_stars(self):
        self.save(self.report("needs_changes", 3))
        with patch("urllib.request.urlopen") as network:
            result = v.feedback(self.report_file)
            network.assert_not_called()
        self.assertTrue(result["draft_only"])
        self.assertIn("needs_changes", result["body"])

    def test_child_environment_excludes_other_exchange_and_github_keys(self):
        env = {"BYBIT_API_SECRET": "do-not-inherit", "GITHUB_TOKEN": "do-not-inherit", "BAW_INSTANCE_ID": "fixture", "PATH": "/bin"}
        with patch.dict(os.environ, env, clear=True):
            child = runtime_environment("binance")
        self.assertNotIn("BYBIT_API_SECRET", child)
        self.assertNotIn("GITHUB_TOKEN", child)
        self.assertEqual(child["BAW_INSTANCE_ID"], "fixture")

    def test_symlink_cannot_hash_an_external_secret_file(self):
        private = Path(self.tmp.name) / "secret"
        private.write_text("private fixture")
        (self.root / "agi_trading/link.py").symlink_to(private)
        with self.assertRaisesRegex(TradingError, "External"):
            v.snapshot()

    def test_commit_change_invalidates_review_even_when_files_match(self):
        self.save(self.report())
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "--allow-empty", "-qm", "New revision"], check=True, capture_output=True)
        with self.assertRaisesRegex(TradingError, "stale"):
            v.require_review()

    def test_modified_commitment_is_rejected(self):
        self.save(self.report())
        result = v.attestation(self.report_file)
        path = Path(self.tmp.name) / "commitment.json"
        v.write_private_json(path, result)
        self.assertTrue(v.verify_attestation(self.report_file, path)["content_matches"])
        result["claims"]["safety_certified"] = True
        v.write_private_json(path, result)
        with self.assertRaisesRegex(TradingError, "does not match"):
            v.verify_attestation(self.report_file, path)

    def test_private_output_cannot_change_reviewed_source(self):
        with self.assertRaisesRegex(TradingError, "outside"):
            v.write_private_json(self.root / "report.json", {"fixture": True})

    def test_world_readable_receipt_is_rejected(self):
        self.save(self.report())
        v.state_file().chmod(0o644)
        with self.assertRaisesRegex(TradingError, "private"):
            v.require_review()

    def test_pattern_scan_finds_dangerous_source_without_running_it(self):
        (self.root / "agi_trading/danger.py").write_text('eval("raise_exception()")\n')
        report = v.audit()
        self.assertTrue(any(f["severity"] == "high" for f in report["automated_findings"]))

    def test_private_key_named_file_is_not_read_into_evidence(self):
        (self.root / "example.key").write_text("fake private fixture")
        report = v.audit()
        self.assertNotIn("example.key", [f["path"] for f in report["snapshot"]["files"]])


if __name__ == "__main__":
    unittest.main()
