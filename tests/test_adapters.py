import base64
import hashlib
import hmac
import json
import os
import unittest
import subprocess
from unittest.mock import patch

from agi_trading.providers.binance.adapter import BinanceWallet
from agi_trading.providers.bitget.adapter import Bitget
from agi_trading.providers.bybit.adapter import Bybit
from agi_trading.providers.okx.adapter import OKXWallet
from agi_trading.providers.native import executable, run
from agi_trading.security import TradingError


class Capture:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, *args):
        self.calls.append(args)
        return self.response


class AdapterTests(unittest.TestCase):
    def setUp(self):
        # These tests isolate API encoding. Gate behavior is exercised separately.
        for target in ("agi_trading.providers.cex.require_review", "agi_trading.providers.native.require_review"):
            gate = patch(target)
            gate.start()
            self.addCleanup(gate.stop)

    def test_bybit_signed_bytes_match_actual_post_body(self):
        capture = Capture({"retCode": 0, "result": {"orderId": "fake"}})
        order = {"symbol": "BTCUSDT", "side": "buy", "quantity": "0.001", "price": "50000"}
        with patch.dict(os.environ, {"BYBIT_TESTNET_API_KEY": "fake-key", "BYBIT_TESTNET_API_SECRET": "fake-secret"}), patch("time.time", return_value=1700000000):
            Bybit("testnet", capture).place_limit(order, "agi-test")
        method, url, headers, body = capture.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api-testnet.bybit.com/v5/order/create")
        expected = hmac.new(b"fake-secret", b"1700000000000fake-key5000" + body, hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-BAPI-SIGN"], expected)
        self.assertEqual(json.loads(body)["isLeverage"], 0)
        self.assertEqual(json.loads(body)["orderLinkId"], "agi-test")

    def test_bitget_demo_get_signs_exact_sorted_query(self):
        capture = Capture({"code": "00000", "data": {}})
        env = {"BITGET_DEMO_API_KEY": "fake-key", "BITGET_DEMO_SECRET_KEY": "fake-secret", "BITGET_DEMO_PASSPHRASE": "fake-pass"}
        with patch.dict(os.environ, env), patch("time.time", return_value=1700000000):
            Bitget("testnet", capture).request("GET", "/api/v3/account/fee-rate", {"symbol": "BTCUSDT", "category": "SPOT"}, True)
        _, url, headers, body = capture.calls[0]
        expected = base64.b64encode(hmac.new(b"fake-secret", b"1700000000000GET/api/v3/account/fee-rate?category=SPOT&symbol=BTCUSDT", hashlib.sha256).digest()).decode()
        self.assertTrue(url.endswith("?category=SPOT&symbol=BTCUSDT"))
        self.assertEqual(headers["ACCESS-SIGN"], expected)
        self.assertEqual(headers["paptrading"], "1")
        self.assertIsNone(body)

    def test_test_credentials_never_fall_back_to_live(self):
        with patch.dict(os.environ, {"BYBIT_API_KEY": "live-key", "BYBIT_API_SECRET": "live-secret"}, clear=True):
            with self.assertRaisesRegex(TradingError, "BYBIT_TESTNET_API_KEY"):
                Bybit("testnet", Capture({})).balances()

    def test_bitget_test_credentials_do_not_fall_back(self):
        with patch.dict(os.environ, {"BITGET_API_KEY": "live-key", "BITGET_SECRET_KEY": "live-secret", "BITGET_PASSPHRASE": "live-pass"}, clear=True):
            with self.assertRaisesRegex(TradingError, "BITGET_DEMO_API_KEY"):
                Bitget("testnet", Capture({})).balances()

    def test_bitget_order_quantity_is_base_coin_for_limit(self):
        capture = Capture({"code": "00000", "data": {"orderId": "fake"}})
        with patch.dict(os.environ, {"BITGET_DEMO_API_KEY": "k", "BITGET_DEMO_SECRET_KEY": "s", "BITGET_DEMO_PASSPHRASE": "p"}):
            Bitget("testnet", capture).place_limit({"symbol": "BTCUSDT", "side": "buy", "quantity": "0.001", "price": "50000"}, "agi-test")
        body = json.loads(capture.calls[0][3])
        self.assertEqual((body["category"], body["orderType"], body["qty"]), ("SPOT", "limit", "0.001"))

    def test_bybit_regional_host_is_allowlisted(self):
        with patch.dict(os.environ, {"BYBIT_API_HOST": "attacker.example"}):
            with self.assertRaises(TradingError):
                Bybit("live")

    def test_precision_and_minimum_notional_fail_closed(self):
        data = [{"symbol": "BTCUSDT", "status": "online", "baseCoin": "BTC", "quoteCoin": "USDT",
                 "quantityPrecision": "6", "pricePrecision": "2", "minOrderAmount": "5", "minOrderQty": "0", "maxOrderQty": "0"}]
        adapter = Bitget("testnet", Capture({"code": "00000", "data": data}))
        order = {"symbol": "BTCUSDT", "quantity": "0.001", "price": "50000.001"}
        with self.assertRaisesRegex(TradingError, "precision|tick"):
            adapter.validate_limit(order)
        order.update(quantity="0.000001", price="50000")
        with self.assertRaisesRegex(TradingError, "minimum"):
            adapter.validate_limit(order)

    def test_bybit_api_error_not_success(self):
        with self.assertRaisesRegex(TradingError, "10003"):
            Bybit("testnet", Capture({"retCode": 10003, "retMsg": "Invalid key"})).ticker("BTCUSDT")

    def test_wallet_quote_cannot_turn_into_execute(self):
        with patch("agi_trading.providers.binance.adapter.run", return_value={}) as run:
            BinanceWallet().quote("56", "0xabc", "0xdef", "0.1")
            args = run.call_args.args[2]
            self.assertEqual(args[:2], ["market-order", "quote"])
            self.assertEqual(args[-1], "--json")
            self.assertNotIn("swap", args)
        with patch("agi_trading.providers.okx.adapter.run", return_value={}) as run:
            OKXWallet().quote("ethereum", "0xabc", "0xdef", "0.1")
            self.assertEqual(run.call_args.args[2][:2], ["swap", "quote"])
            self.assertNotIn("--force", run.call_args.args[2])

    def test_okx_quote_rejects_option_injection(self):
        with self.assertRaises(TradingError):
            OKXWallet().quote("ethereum", "--force", "0xdef", "0.1")

    def test_native_failure_envelope_is_not_success_even_at_exit_zero(self):
        response = subprocess.CompletedProcess([], 0, '{"ok":false,"error":"Login required"}', '')
        with patch("agi_trading.providers.native.executable", return_value="onchainos"), patch("subprocess.run", return_value=response):
            with self.assertRaisesRegex(TradingError, "Login required"):
                run("okx", "onchainos", ["wallet", "status"])

    def test_unreviewed_path_binary_is_not_used(self):
        with self.assertRaisesRegex(TradingError, "Reviewed local"):
            executable("not-installed-fixture", "sh")


if __name__ == "__main__":
    unittest.main()
