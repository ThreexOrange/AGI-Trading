from datetime import datetime, timezone

from ..native import run
from ...security import TradingError, identifier, positive


class BinanceWallet:
    """Official baw adapter."""
    def call(self, args, timeout=45, *, json_lines=False):
        if json_lines:
            return run("binance", "baw", [*args, "--json"], timeout, json_lines=True)
        return run("binance", "baw", [*args, "--json"], timeout)

    def status(self):
        return self.call(["wallet", "status"])

    def balances(self):
        return self.call(["wallet", "balance"])

    def addresses(self):
        return self.call(["wallet", "address"])

    def chains(self):
        return self.call(["wallet", "chains"])

    def login(self):
        return self.call(["auth", "signin"])

    def verify(self, session):
        return self.call(["auth", "verify", "--qrCodeId", identifier(session)], 330)

    def quote(self, chain, source, target, amount):
        positive(amount)
        return self.call(["market-order", "quote", "--binanceChainId", identifier(chain),
                          "--fromToken", identifier(source), "--toToken", identifier(target),
                          "--fromTokenQty", amount])

    def require_developer_mode(self):
        data = self.call(["wallet", "settings"])["data"]
        mode = data.get("devMode") or {}
        expiry = mode.get("expiresAt")
        if mode.get("enabled") is not True or mode.get("balanceExceeded"):
            raise TradingError("Binance Developer Mode must be active in the Binance App")
        if not isinstance(expiry, str):
            raise TradingError("Binance Developer Mode expiry is unavailable")
        expires = datetime.fromisoformat(expiry)
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            raise TradingError("Binance Developer Mode has expired")
