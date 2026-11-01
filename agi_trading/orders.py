"""Durable preview/submit journal. Acknowledgement never means filled."""
import hashlib
import json
import os
import sqlite3
import time
import uuid
from decimal import localcontext
from pathlib import Path

from .providers import exchange
from .security import TradingError, positive, symbol
from .verification import require_review


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def policy(order):
    if order.get("provider") not in ("bitget", "bybit"):
        raise TradingError("Limit-order execution is supported only for Bitget and Bybit")
    if order.get("mode") not in ("paper", "testnet", "live") or order.get("side") not in ("buy", "sell"):
        raise TradingError("Invalid order mode or side")
    allowed = {symbol(s.strip()) for s in os.environ.get("AGI_TRADING_ALLOWED_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")}
    name = symbol(order["symbol"])
    if name != order["symbol"] or name not in allowed or not name.endswith("USDT"):
        raise TradingError("Symbol must be an allowlisted USDT spot pair")
    with localcontext() as ctx:
        ctx.prec = 80
        notional = positive(order["quantity"], "quantity") * positive(order["price"], "price")
    cap = positive(os.environ.get("AGI_TRADING_MAX_ORDER_USDT", "100"), "order cap")
    if notional > cap:
        raise TradingError(f"Order exceeds configured {cap} USDT per-order cap")
    return format(notional, "f")


class Journal:
    def __init__(self, root=None):
        root = Path(root or os.environ.get("AGI_TRADING_STATE_DIR", Path.home() / ".local/state/agi-trading")).expanduser().resolve()
        # Enforce runtime data outside this source checkout.
        project = Path(__file__).resolve().parent.parent
        if root == project or project in root.parents:
            raise TradingError("Runtime state must be outside the source repository")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        path = root / "orders.sqlite3"
        if path.is_symlink():
            raise TradingError("State database must not be a symlink")
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        path.chmod(0o600)
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.db.execute("CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL)")

    def create(self, provider, mode, name, side, quantity, price):
        plan_id = uuid.uuid4().hex
        order = {"schema": 1, "id": plan_id, "client_order_id": "agi" + plan_id[:28],
                 "provider": provider, "mode": mode, "market": "spot", "type": "limit",
                 "symbol": symbol(name), "side": side, "quantity": quantity, "price": price,
                 "created_at": int(time.time()), "expires_at": int(time.time()) + 300}
        notional = policy(order)
        if mode != "paper":
            exchange(provider, mode).validate_limit(order)
        payload = canonical(order)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        self.db.execute("INSERT INTO plans VALUES (?, ?, ?, 'prepared')", (plan_id, payload, digest))
        return {"plan": order, "digest": digest, "notional_usdt": notional,
                "status": "preview_only", "exchange_rules_checked": mode != "paper",
                "confirmation": "Review this exact plan, then pass its digest to execute --confirm. A digest is an intent check, not proof of human identity."}

    def get(self, plan_id):
        row = self.db.execute("SELECT payload, digest, state FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not row:
            raise TradingError("Plan not found in this runtime's journal")
        payload, digest, state = row
        if hashlib.sha256(payload.encode()).hexdigest() != digest:
            raise TradingError("Plan integrity check failed")
        return json.loads(payload), digest, state

    def execute(self, plan_id, confirmation, factory=exchange):
        # One worker can claim a plan. Claim BEFORE any API operation; a crash is ambiguous.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            order, digest, state = self.get(plan_id)
            if confirmation != digest:
                raise TradingError("Confirmation digest does not match this exact plan")
            if state != "prepared":
                raise TradingError(f"Plan is {state}; do not resubmit. Use order-status to reconcile")
            if time.time() >= order["expires_at"]:
                raise TradingError("Plan expired; obtain and review a new preview")
            policy(order)  # Re-check current policy, even if it tightened since preview.
            if order["mode"] == "live" and os.environ.get("AGI_TRADING_ENABLE_LIVE") != "1":
                raise TradingError("Live execution is disabled; AGI_TRADING_ENABLE_LIVE=1 is required")
            if order["mode"] != "paper":
                require_review()
            self.db.execute("UPDATE plans SET state='claimed' WHERE id=?", (plan_id,))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        if order["mode"] == "paper":
            self.db.execute("UPDATE plans SET state='simulated' WHERE id=?", (plan_id,))
            return {"status": "simulated", "simulated": True, "plan": order,
                    "note": "Local intent simulation only. No exchange call, fill, fees, slippage or account balance is simulated."}
        try:
            adapter = factory(order["provider"], order["mode"])
            instrument = adapter.validate_limit(order)
            adapter.check_balance(order, instrument)
            if time.time() >= order["expires_at"]:
                raise TradingError("Plan expired during pre-submit validation; obtain a fresh preview")
        except Exception:
            self.db.execute("UPDATE plans SET state='validation_failed' WHERE id=?", (plan_id,))
            raise
        # Any failure from this point could have happened AFTER exchange acceptance.
        self.db.execute("UPDATE plans SET state='submission_unknown' WHERE id=?", (plan_id,))
        result = adapter.place_limit(order, order["client_order_id"])
        self.db.execute("UPDATE plans SET state='submitted' WHERE id=?", (plan_id,))
        return {"status": "submitted", "fill_status": "not_checked", "client_order_id": order["client_order_id"],
                "result": result, "note": "Submission acknowledgement only. Query order-status for exchange state."}

    def reconcile(self, plan_id, factory=exchange):
        order, _, state = self.get(plan_id)
        if order["mode"] == "paper":
            return {"journal_state": state, "simulated": True, "plan": order}
        result = factory(order["provider"], order["mode"]).order_status(order["symbol"], order["client_order_id"])
        return {"journal_state": state, "client_order_id": order["client_order_id"], "exchange": result,
                "note": "An absent order is not proof of rejection. This command never resubmits."}
