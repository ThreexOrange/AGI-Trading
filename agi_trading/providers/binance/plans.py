"""One-time confirmation for Binance Agentic Wallet changes."""

import json
import os
import time
import uuid

from ...orders import Journal
from ...security import TradingError, identifier
from ...verification import digest, require_review
from .commands import TRANSACTION
from .operations import SIGNING, preview, submit, swap_status
from .options import validate_plan


class WalletPlans:
    def __init__(self, wallet, root=None):
        self.wallet = wallet
        self.db = Journal(root).db
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS binance_plans "
            "(id TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS binance_plan_references "
            "(id TEXT PRIMARY KEY, reference TEXT NOT NULL)"
        )

    def close(self):
        self.db.close()

    def wallet_id(self):
        reply = self.wallet.addresses()
        data = (reply.get("data") or {}).get("addresses")
        if reply.get("success") is not True or not isinstance(data, list) or not data:
            raise TradingError("Could not identify the active Binance wallet")
        addresses = sorted({(str(entry["binanceChainId"]), entry["address"]) for entry in data})
        return digest(addresses)

    def create(self, path, options):
        validate_plan(path, options)
        review = require_review()
        identity = self.wallet_id()
        execution, detail, expires = preview(self.wallet, path, options)
        plan_id = uuid.uuid4().hex
        plan = {"id": plan_id, "command": path, "options": options,
                "preview": detail, "expires_at": expires}
        # Retain only arguments needed for execution and a fingerprint of the
        # preview. The wallet's identity and returned signatures are not stored.
        payload = {"id": plan_id, "command": path, "execution": execution, "expires_at": expires,
                   "wallet": identity, "review": review_fingerprint(review),
                   "preview_digest": digest(plan)}
        confirmation = digest(payload)
        self.db.execute("INSERT INTO binance_plans VALUES (?, ?, ?, 'prepared')",
                        (plan_id, json.dumps(payload), confirmation))
        return {"status": "preview", "plan": plan, "digest": confirmation}

    def get(self, plan_id):
        row = self.db.execute("SELECT payload, digest, state FROM binance_plans WHERE id=?", (plan_id,)).fetchone()
        if not row:
            raise TradingError("Binance wallet plan not found")
        payload, confirmation, state = row
        plan = json.loads(payload)
        if plan.get("id") != plan_id or digest(plan) != confirmation:
            raise TradingError("Binance wallet plan integrity check failed")
        return plan, confirmation, state

    def status(self, plan_id):
        plan, _, state = self.get(identifier(plan_id))
        result = {"plan_id": plan_id, "command": plan["command"], "state": state}
        row = self.db.execute("SELECT reference FROM binance_plan_references WHERE id=?", (plan_id,)).fetchone()
        if row:
            result["reference"] = json.loads(row[0])
        return result

    def execute(self, plan_id, confirmation):
        plan_id = identifier(plan_id)
        plan, expected, state = self.get(plan_id)
        if confirmation != expected:
            raise TradingError("Confirmation digest does not match the Binance wallet plan")
        if state != "prepared":
            raise TradingError(f"Binance plan is {state}. Check the wallet or order history before taking another action.")
        if time.time() >= plan["expires_at"]:
            raise TradingError("Binance wallet plan expired. Create and review a new preview.")
        path = plan["command"]
        if path in TRANSACTION and os.environ.get("AGI_TRADING_ENABLE_LIVE") != "1":
            raise TradingError("Live execution is disabled; AGI_TRADING_ENABLE_LIVE=1 is required")
        review = require_review()
        if review_fingerprint(review) != plan["review"] or self.wallet_id() != plan["wallet"]:
            raise TradingError("The runtime or active Binance wallet changed. Create a new preview.")
        if path in SIGNING:
            self.wallet.require_developer_mode()
        claimed = self.db.execute(
            "UPDATE binance_plans SET state='submission_unknown' WHERE id=? AND state='prepared' AND digest=?",
            (plan_id, expected),
        )
        if claimed.rowcount != 1:
            raise TradingError("Another process already claimed this Binance plan")
        if time.time() >= plan["expires_at"]:
            self.db.execute("UPDATE binance_plans SET state='expired' WHERE id=?", (plan_id,))
            raise TradingError("Binance wallet plan expired during verification")
        try:
            response = submit(self.wallet, path, plan["execution"])
        except (TradingError, OSError, ValueError) as exc:
            raise TradingError(f"Binance submission unconfirmed. Check wallet or order history before retrying. {exc}") from exc
        state = "acknowledged" if path in TRANSACTION else "completed"
        data = response.get("data")
        reference = {field: data[field] for field in ("orderId", "strategyId", "txHash", "approveTxHash")
                     if isinstance(data, dict) and type(data.get(field)) in (str, int)}
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if reference:
                self.db.execute("INSERT INTO binance_plan_references VALUES (?, ?)", (plan_id, json.dumps(reference)))
            self.db.execute("UPDATE binance_plans SET state=? WHERE id=?", (state, plan_id))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        if path == "market-order swap":
            return {"plan_id": plan_id, **swap_status(self.wallet, response)}
        return {"plan_id": plan_id, "status": state, "result": response}


def review_fingerprint(report):
    return [report[key] for key in ("commit", "source_sha256", "runtime_sha256")]
