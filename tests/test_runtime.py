import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agi_trading.providers import native
from agi_trading.runtime import ReleaseRedirect, bootstrap, install_okx
from agi_trading.security import TradingError


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        gate = patch("agi_trading.runtime.require_review")
        gate.start()
        self.addCleanup(gate.stop)

    def test_okx_bad_checksum_refuses_installation(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b"modified binary"
        with patch("platform.system", return_value="Linux"), patch("platform.machine", return_value="x86_64"), patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaisesRegex(TradingError, "checksum mismatch"):
                install_okx()

    def test_release_redirect_requires_official_https_assets(self):
        for url in ("https://evil.example/onchainos", "http://release-assets.githubusercontent.com/file"):
            with self.subTest(url=url), self.assertRaises(TradingError):
                ReleaseRedirect().redirect_request(None, None, 302, "", {}, url)

    def test_unknown_architecture_does_not_guess(self):
        with patch("platform.system", return_value="Linux"), patch("platform.machine", return_value="riscv64"):
            with self.assertRaisesRegex(TradingError, "architecture"):
                install_okx()

    @unittest.skipUnless(os.name == "nt", "Windows Node.js entry points")
    def test_windows_runs_locked_binance_entry_with_node(self):
        with tempfile.TemporaryDirectory() as folder:
            module = Path(folder) / "native.py"
            script = module.parent / "binance/node_modules/@binance/agentic-wallet/dist/index.js"
            script.parent.mkdir(parents=True)
            script.touch()
            with (patch.object(native, "__file__", str(module)), patch.object(native, "require_review"),
                  patch.object(native.shutil, "which", return_value="node.exe"),
                  patch.object(native.subprocess, "run", return_value=MagicMock(stdout="{}", returncode=0)) as run):
                native.run("binance", "baw", ["wallet", "status", "--json"])
            self.assertEqual(run.call_args.args[0], ["node.exe", str(script), "wallet", "status", "--json"])
            self.assertFalse(run.call_args.kwargs["shell"])

    @unittest.skipUnless(os.name == "nt", "Windows Node.js entry points")
    def test_windows_bootstrap_runs_bundled_npm_with_lifecycle_scripts_disabled(self):
        with tempfile.TemporaryDirectory() as folder:
            npm_cli = Path(folder) / "node_modules/npm/bin/npm-cli.js"
            npm_cli.parent.mkdir(parents=True)
            npm_cli.touch()
            with (patch("agi_trading.runtime.shutil.which", side_effect=[str(Path(folder) / "npm.cmd"), "node.exe"]),
                  patch("agi_trading.runtime.subprocess.run", return_value=MagicMock(returncode=0)) as run):
                bootstrap("binance")
            self.assertEqual(run.call_args.args[0][:4], ["node.exe", str(npm_cli), "ci", "--ignore-scripts"])
            self.assertFalse(run.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
