import hashlib
import hmac
import os
from decimal import Decimal

from ..cex import CEX
from ...security import TradingError, require_env, symbol

LIVE_HOSTS = {
    "api.bybit.com", "api.bybit.tr", "api.bybit.kz", "api.bybitgeorgia.ge",
    "api.bybit.ae", "api.bybit.eu", "api.bybit.id", "api.manepa.jp", "api.spark-fintech.com",
}


class Bybit(CEX):
    name = "bybit"

    def __init__(self, network="testnet", transport=None):
        super().__init__(network, transport)
        host = os.environ.get("BYBIT_API_HOST", "api.bybit.com")
        if host not in LIVE_HOSTS:
            raise TradingError("BYBIT_API_HOST is not an official allowlisted host")
        self.base_url = "https://" + ("api-testnet.bybit.com" if network == "testnet" else host)

    @property
    def credential_names(self):
        prefix = "BYBIT_TESTNET" if self.network == "testnet" else "BYBIT"
        return [prefix + "_API_KEY", prefix + "_API_SECRET"]

    def sign(self, timestamp, method, path, query, body):
        key, secret = require_env(self.credential_names)
        window = "5000"
        message = timestamp + key + window + (query if method == "GET" else body)
        signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        return {"X-BAPI-API-KEY": key, "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": window, "X-BAPI-SIGN": signature}

    def unwrap(self, result):
        if result.get("retCode") != 0:
            raise TradingError(f"Bybit {result.get('retCode')}: {result.get('retMsg', 'Unknown API error')}")
        return result["result"]

    def ticker(self, name):
        return self.request("GET", "/v5/market/tickers", {"category": "spot", "symbol": symbol(name)})

    def instruments(self, name):
        return self.request("GET", "/v5/market/instruments-info", {"category": "spot", "symbol": name})["list"]

    def balances(self):
        return self.request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"}, private=True)

    def available(self, coin):
        for account in self.balances()["list"]:
            for row in account.get("coin", []):
                if row.get("coin") == coin:
                    # Intentionally conservative. Never borrow or enable spot margin.
                    return max(Decimal(0), Decimal(row["walletBalance"]) - Decimal(row.get("locked") or "0")
                               - Decimal(row.get("borrowAmount") or "0") - Decimal(row.get("spotBorrow") or "0"))
        return Decimal(0)

    def status(self):
        self.balances()
        return {"authenticated": True, "accountType": "UNIFIED", "network": self.network}

    def place_limit(self, order, client_id):
        return self.request("POST", "/v5/order/create", {
            "category": "spot", "symbol": order["symbol"], "side": order["side"].title(),
            "orderType": "Limit", "qty": order["quantity"], "price": order["price"],
            "timeInForce": "GTC", "isLeverage": 0, "orderLinkId": client_id,
        }, private=True)

    def order_status(self, name, client_id):
        params = {"category": "spot", "symbol": symbol(name), "orderLinkId": client_id}
        result = self.request("GET", "/v5/order/realtime", params, private=True)
        if not result.get("list"):
            result = self.request("GET", "/v5/order/history", params, private=True)
        return result
