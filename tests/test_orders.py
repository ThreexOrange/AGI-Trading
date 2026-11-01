import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from agi_trading.orders import Journal
from agi_trading.security import TradingError


class FakeExchange:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def validate_limit(self, order):
        return {}

    def check_balance(self, order, instrument):
        pass

    def place_limit(self, order, client_id):
        self.calls += 1
        if self.fail:
            raise TradingError("Simulated timeout AFTER exchange acceptance")
        return {"orderId": "fake-order", "clientOrderId": client_id}

    def order_status(self, name, client_id):
        return {"clientOrderId": client_id, "orderStatus": "Filled"}


class OrderTests(unittest.TestCase):
    def setUp(self):
        gate = patch("agi_trading.orders.require_review")
        gate.start()
        self.addCleanup(gate.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"AGI_TRADING_MAX_ORDER_USDT": "100", "AGI_TRADING_ALLOWED_SYMBOLS": "BTCUSDT,ETHUSDT", "AGI_TRADING_ENABLE_LIVE": "0"})
        self.env.start()
        self.journal = Journal(self.tmp.name)

    def tearDown(self):
        self.journal.db.close()
        self.env.stop()
        self.tmp.cleanup()

    def plan(self, mode="paper"):
        with patch("agi_trading.orders.exchange", return_value=FakeExchange()):
            return self.journal.create("bybit", mode, "BTCUSDT", "buy", "0.001", "50000")

    def test_paper_is_offline_and_only_runs_once(self):
        plan = self.plan()
        result = self.journal.execute(plan["plan"]["id"], plan["digest"], factory=lambda *_: self.fail("No network allowed"))
        self.assertTrue(result["simulated"])
        with self.assertRaisesRegex(TradingError, "simulated"):
            self.journal.execute(plan["plan"]["id"], plan["digest"])

    def test_wrong_confirmation_does_not_claim_plan(self):
        plan = self.plan()
        with self.assertRaisesRegex(TradingError, "digest"):
            self.journal.execute(plan["plan"]["id"], "wrong")
        self.assertEqual(self.journal.get(plan["plan"]["id"])[2], "prepared")

    def test_live_switch_is_required(self):
        plan = self.plan("live")
        with self.assertRaisesRegex(TradingError, "Live execution is disabled"):
            self.journal.execute(plan["plan"]["id"], plan["digest"])

    def test_timeout_never_retries_and_preserves_reconcile_id(self):
        plan = self.plan("testnet")
        adapter = FakeExchange(fail=True)
        for _ in range(2):
            with self.assertRaises(TradingError):
                self.journal.execute(plan["plan"]["id"], plan["digest"], lambda *_: adapter)
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(self.journal.get(plan["plan"]["id"])[2], "submission_unknown")
        status = self.journal.reconcile(plan["plan"]["id"], lambda *_: adapter)
        self.assertEqual(status["exchange"]["orderStatus"], "Filled")

    def test_acknowledged_order_is_not_reported_filled(self):
        plan = self.plan("testnet")
        result = self.journal.execute(plan["plan"]["id"], plan["digest"], lambda *_: FakeExchange())
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(result["fill_status"], "not_checked")

    def test_changed_policy_is_rechecked_at_execution(self):
        plan = self.plan()
        with patch.dict(os.environ, {"AGI_TRADING_MAX_ORDER_USDT": "1"}):
            with self.assertRaisesRegex(TradingError, "cap"):
                self.journal.execute(plan["plan"]["id"], plan["digest"])

    def test_expired_plan_is_rejected(self):
        plan = self.plan()
        with patch("time.time", return_value=time.time() + 400):
            with self.assertRaisesRegex(TradingError, "expired"):
                self.journal.execute(plan["plan"]["id"], plan["digest"])

    def test_modified_payload_fails_integrity(self):
        plan = self.plan()
        self.journal.db.execute("UPDATE plans SET payload=replace(payload, '50000', '99999') WHERE id=?", (plan["plan"]["id"],))
        with self.assertRaisesRegex(TradingError, "integrity"):
            self.journal.execute(plan["plan"]["id"], plan["digest"])

    def test_cap_and_unlisted_symbol_are_enforced(self):
        for symbol, qty in (("DOGEUSDT", "0.001"), ("BTCUSDT", "1")):
            with self.assertRaises(TradingError):
                self.journal.create("bybit", "paper", symbol, "buy", qty, "50000")

    def test_two_workers_cannot_execute_same_plan(self):
        plan = self.plan()
        def worker():
            journal = Journal(self.tmp.name)
            try:
                journal.execute(plan["plan"]["id"], plan["digest"])
                return "executed"
            except TradingError:
                return "blocked"
            finally:
                journal.db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sorted(results), ["blocked", "executed"])


if __name__ == "__main__":
    unittest.main()
