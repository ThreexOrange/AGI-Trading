import unittest
from unittest.mock import MagicMock, patch

from agi_trading.runtime import ReleaseRedirect, install_okx
from agi_trading.security import TradingError


class RuntimeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
