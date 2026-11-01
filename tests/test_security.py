import json
import os
import unittest
from unittest.mock import patch

from agi_trading.security import TradingError, identifier, positive, redact
from agi_trading.transport import NoRedirect, Transport


class SecurityTests(unittest.TestCase):
    def test_invalid_amounts_are_rejected(self):
        for amount in ("NaN", "Infinity", "0", "-1", "1e3", "0.01; ls", " 2"):
            with self.subTest(amount=amount), self.assertRaises(TradingError):
                positive(amount)

    def test_identifiers_cannot_inject_flags_or_shell(self):
        for value in ("--force", "abc;cat", "$(id)", "a\nb", "a b"):
            with self.subTest(value=value), self.assertRaises(TradingError):
                identifier(value)

    def test_nested_and_echoed_credentials_are_redacted(self):
        with patch.dict(os.environ, {"BYBIT_API_SECRET": "fake-secret-123"}):
            data = redact({"data": {"accessToken": "x", "clientId": "id", "sessionCert": "cert"},
                           "message": "echo fake-secret-123", "pairingCode": "123456"})
        self.assertNotIn("fake-secret-123", json.dumps(data))
        self.assertEqual(data["data"]["sessionCert"], "[REDACTED]")
        self.assertEqual(data["pairingCode"], "123456")

    def test_non_json_secret_patterns_are_redacted(self):
        self.assertNotIn("sensitive123", redact('accessToken=sensitive123&x=1'))
        self.assertNotIn("sensitive123", redact('Bearer sensitive123'))

    def test_untrusted_hosts_rejected_before_network(self):
        for url in ("http://api.bybit.com/x", "https://evil.example/x", "https://api.bybit.com.evil.example/x",
                    "https://user:pass@api.bybit.com/x", "https://api.bybit.com:444/x"):
            with self.subTest(url=url), self.assertRaises(TradingError):
                Transport().request("GET", url)

    def test_redirect_cannot_forward_auth_headers(self):
        with self.assertRaises(TradingError):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example")


if __name__ == "__main__":
    unittest.main()
