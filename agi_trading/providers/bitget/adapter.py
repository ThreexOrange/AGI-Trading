import base64
import hashlib
import hmac
from decimal import Decimal

from ..cex import CEX
from ...security import TradingError, require_env, symbol


class Bitget(CEX):
    name = "bitget"
    base_url = "https://api.bitget.com"

    @property
    def credential_names(self):
        prefix = "BITGET_DEMO" if self.network == "testnet" else "BITGET"
        return [prefix + "_API_KEY", prefix + "_SECRET_KEY", prefix + "_PASSPHRASE"]

    def sign(self, timestamp, method, path, query, body):
        key, secret, passphrase = require_env(self.credential_names)
        message = timestamp + method + path + ("?" + query if query else "") + body
        signature = base64.b64encode(hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()).decode()
        return {"ACCESS-KEY": key, "ACCESS-SIGN": signature, "ACCESS-TIMESTAMP": timestamp,
                "ACCESS-PASSPHRASE": passphrase}

    def unwrap(self, result):
        if result.get("code") != "00000":
            raise TradingError(f"Bitget {result.get('code')}: {result.get('msg', 'Unknown API error')}")
        return result["data"]

    def ticker(self, name):
        return self.request("GET", "/api/v3/market/tickers", {"category": "SPOT", "symbol": symbol(name)})

    def instruments(self, name):
        return self.request("GET", "/api/v3/market/instruments", {"category": "SPOT", "symbol": name})

    def balances(self):
        return self.request("GET", "/api/v3/account/assets", private=True)

    def available(self, coin):
        for row in self.balances()["assets"]:
            if row.get("coin") == coin:
                return Decimal(row["available"])
        return Decimal(0)

    def status(self):
        self.balances()
        return {"authenticated": True, "accountType": "UTA", "network": self.network,
                "demo": self.network == "testnet"}

    def place_limit(self, order, client_id):
        return self.request("POST", "/api/v3/trade/place-order", {
            "category": "SPOT", "symbol": order["symbol"], "side": order["side"],
            "orderType": "limit", "qty": order["quantity"], "price": order["price"],
            "timeInForce": "gtc", "clientOid": client_id,
        }, private=True)

    def order_status(self, name, client_id):
        return self.request("GET", "/api/v3/trade/order-info", {
            "clientOid": client_id,
        }, private=True)
