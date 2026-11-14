import os
import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from agi_trading.cli import dispatch, parser
from agi_trading.providers.binance import operations
from agi_trading.providers.binance.options import catalog, json_options
from agi_trading.security import TradingError


def reply(data):
    return {"success": True, "data": data}


class BinanceWalletTests(unittest.TestCase):
    def setUp(self):
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        self.wallet = Mock()
        self.wallet.addresses.return_value = reply({
            "addresses": [{"binanceChainId": "56", "address": "0x" + "1" * 40}],
        })
        env = patch.dict(os.environ, {"AGI_TRADING_STATE_DIR": state.name, "AGI_TRADING_ENABLE_LIVE": "1"})
        env.start()
        self.addCleanup(env.stop)
        review = patch("agi_trading.providers.binance.plans.require_review", return_value={
            "commit": "commit", "source_sha256": "source", "runtime_sha256": "runtime",
        })
        review.start()
        self.addCleanup(review.stop)
        factory = patch("agi_trading.cli.wallet", return_value=self.wallet)
        factory.start()
        self.addCleanup(factory.stop)

    def cli(self, *argv):
        return dispatch(parser().parse_args(argv))

    def execute(self, result):
        return self.cli("binance-execute", result["plan"]["id"], "--confirm", result["digest"])

    def test_read_rejects_mutations_and_unknown_options(self):
        for path, options in (("wallet send", "{}"), ("signal backtest schedule", '{"interval":"4H"}'),
                              ("wallet balance", '{"json":true}')):
            with self.subTest(path=path), self.assertRaises(TradingError):
                self.cli("binance-read", path, "--options", options)
        self.wallet.call.assert_not_called()

    def test_filters_and_wallet_tracker_events(self):
        self.cli("binance-read", "wallet balance", "--options", '{"hideLowValue":"false","symbol":"USDC"}')
        self.wallet.call.assert_called_once_with(["wallet", "balance", "--hideLowValue=false", "--symbol=USDC"], timeout=45)
        with self.assertRaisesRegex(TradingError, "duration"):
            self.cli("binance-read", "tracker ws", "--options", '{"smy":true}')
        self.cli("binance-read", "tracker ws", "--options", '{"smy":true,"duration":5}')
        self.wallet.call.assert_called_with(["tracker", "ws", "--duration=5", "--smy"], timeout=25, json_lines=True)

    def test_tracker_batch_only_exposes_validated_addresses(self):
        address = "0x" + "1" * 40
        def call(args, **kwargs):
            path = Path(next(arg.split("=", 1)[1] for arg in args if arg.startswith("--address-list=")))
            self.assertEqual(path.read_text(encoding="utf-8"), address)
            return reply([])
        self.wallet.call.side_effect = call
        options = json.dumps({"chain-id": "56", "duration": 5, "addresses": [address]})
        self.assertEqual(self.cli("binance-read", "tracker ws", "--options", options), reply([]))
        options = json.dumps({"chain-id": "56", "duration": 5, "address-list": "secret.txt"})
        with self.assertRaisesRegex(TradingError, "Unsupported"):
            self.cli("binance-read", "tracker ws", "--options", options)

    def test_developer_mode_and_preview_id_bound_to_plan(self):
        self.wallet.call.side_effect = [
            reply({"requestId": "binance-id", "parsedTx": {}, "risks": {"riskDetails": []},
                   "expiresAt": int(time.time() * 1000) + 120000}),
            reply({"status": "PENDING_CONFIRMATION"}),
        ]
        result = self.cli("binance-plan", "contract-call execute", "--options",
                          '{"binanceChainId":"56","from":"wallet","to":"contract","value":"0"}')
        self.assertEqual(self.wallet.require_developer_mode.call_count, 1)
        self.assertEqual(result["plan"]["preview"]["preview"]["requestId"], "binance-id")
        with self.assertRaisesRegex(TradingError, "digest"):
            self.cli("binance-execute", result["plan"]["id"], "--confirm", "different")
        self.assertEqual(self.execute(result)["result"]["data"]["status"], "PENDING_CONFIRMATION")
        self.wallet.call.assert_called_with(["contract-call", "execute", "--requestId=binance-id"])
        self.assertEqual(self.wallet.require_developer_mode.call_count, 2)
        with self.assertRaisesRegex(TradingError, "acknowledged"):
            self.execute(result)

    def test_send_rejects_unresolved_domain(self):
        with self.assertRaisesRegex(TradingError, "full address"):
            self.cli("binance-plan", "wallet send", "--options",
                     '{"binanceChainId":56,"recipient":"alice.eth","tokenAddress":"0xabc","amount":"1"}')
        self.wallet.addresses.assert_not_called()

    def test_live_off_switch_and_ambiguous_submission(self):
        options = '{"binanceChainId":56,"recipient":"0x' + '1' * 40 + '","tokenAddress":"0x' + '2' * 40 + '","amount":"1.25"}'
        result = self.cli("binance-plan", "wallet send", "--options", options)
        self.wallet.call.assert_not_called()
        with patch.dict(os.environ, {"AGI_TRADING_ENABLE_LIVE": "0"}):
            with self.assertRaisesRegex(TradingError, "Live execution is disabled"):
                self.execute(result)
        self.wallet.call.side_effect = TradingError("Request timed out")
        with self.assertRaisesRegex(TradingError, "submission unconfirmed"):
            self.execute(result)
        self.assertEqual(self.cli("binance-plan-status", result["plan"]["id"])["state"], "submission_unknown")
        with self.assertRaisesRegex(TradingError, "submission_unknown"):
            self.execute(result)
        self.wallet.call.assert_called_once()

    def test_defi_preview_binds_same_arguments_to_submission(self):
        self.wallet.call.side_effect = [reply({"warnings": ["health factor"], "balanceChange": [], "feeAndContract": {}}),
                                        reply({"txHash": "fixture"})]
        result = self.cli("binance-plan", "defi redeem", "--options", '{"investmentId":"pool","ratio":"0.25"}')
        self.assertEqual(result["plan"]["preview"]["preview"]["warnings"], ["health factor"])
        self.execute(result)
        self.assertEqual(self.wallet.call.call_args_list[0].args[0],
                         ["defi", "preview", "--action=REDEEM", "--investmentId=pool", "--ratio=0.25"])
        self.wallet.call.assert_called_with(["defi", "redeem", "--investmentId=pool", "--ratio=0.25"])

    def test_prediction_quote_and_x402_selection(self):
        self.wallet.call.side_effect = [
            reply({"quoteId": "quoted-order", "expireAt": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
                   "orderType": "LIMIT", "slippageBps": 40}), reply({"orderId": "submitted"}),
            reply({"paymentId": "payment", "options": [{"index": 2, "status": "READY_TO_SIGN"}]}),
            reply({"paymentHeaderValue": "fixture"}),
        ]
        result = self.cli("binance-plan", "prediction trade place-order", "--options",
                          '{"binanceChainId":56,"tokenId":"token","marketTopicId":"topic","orderType":"LIMIT",'
                          '"side":"BUY","amount":"5","priceLimit":"0.5"}')
        self.execute(result)
        self.wallet.call.assert_called_with(["prediction", "trade", "place-order", "--orderType=LIMIT",
                                            "--priceLimit=0.5", "--quoteId=quoted-order", "--slippageBps=40"])
        result = self.cli("binance-plan", "x402-payment sign", "--options",
                          '{"paymentRequirements":"fixture-payload","selectedIndex":2}')
        self.execute(result)
        self.wallet.call.assert_called_with(["x402-payment", "sign", "--paymentId=payment", "--selectedIndex=2"])

    def test_market_swap_checks_audit_and_reports_terminal_state(self):
        options = ('{"binanceChainId":56,"fromToken":"0x' + '1' * 40 + '","toToken":"0x' + '2' * 40
                   + '","fromTokenQty":"1"}')
        self.wallet.call.side_effect = [reply({"toCoinAmount": "2"}), reply({"orderId": "1"}),
                                        reply({"list": [{"orderId": "1", "status": "FAILED"}]})]
        with patch.object(operations, "token_audit", return_value={"riskLevel": 1}) as audit:
            result = self.cli("binance-plan", "market-order swap", "--options", options)
            audit.assert_called_once_with(56, "0x" + "2" * 40)
        self.assertEqual(self.execute(result)["order_status"], "FAILED")
        self.assertEqual(self.cli("binance-plan-status", result["plan"]["id"])["reference"], {"orderId": "1"})

    def test_audit_and_validation_fail_closed(self):
        with patch.object(operations.Transport, "request",
                          return_value={"code": "000000", "data": {"hasResult": False, "isSupported": True}}):
            with self.assertRaisesRegex(TradingError, "unavailable"):
                operations.token_audit("56", "0x" + "2" * 40)
        with self.assertRaisesRegex(TradingError, "Duplicate"):
            json_options('{"amount":"1","amount":"2"}')
        self.assertIn("tracker ws", catalog()["queries"])
        self.assertIn("signal backtest schedule", catalog()["account_changes"])
