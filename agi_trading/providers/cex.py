import json
import time
from decimal import Decimal
from urllib.parse import urlencode

from ..security import TradingError, positive, symbol
from ..transport import Transport
from ..verification import require_review


class CEX:
    def __init__(self, network="testnet", transport=None):
        if network not in ("live", "testnet"):
            raise TradingError("Network must be live or testnet")
        self.network = network
        self.transport = transport or Transport()

    def request(self, method, path, params=None, private=False):
        require_review()  # Before signing code reads any exchange credential.
        params = params or {}
        query = urlencode(sorted(params.items())) if method == "GET" else ""
        body = json.dumps(params, separators=(",", ":")) if method == "POST" else ""
        headers = {"Content-Type": "application/json"}
        if private:
            headers.update(self.sign(str(int(time.time() * 1000)), method, path, query, body))
        if self.name == "bitget" and self.network == "testnet":
            headers["paptrading"] = "1"
        url = self.base_url + path + ("?" + query if query else "")
        result = self.transport.request(method, url, headers, body.encode() if body else None)
        return self.unwrap(result)

    def instrument(self, name):
        name = symbol(name)
        rows = self.instruments(name)
        matches = [r for r in rows if r.get("symbol") == name]
        if len(matches) != 1:
            raise TradingError("Instrument is unavailable or ambiguous")
        return matches[0]

    def validate_limit(self, order):
        item = self.instrument(order["symbol"])
        qty, price = positive(order["quantity"], "quantity"), positive(order["price"], "price")
        if self.name == "bybit":
            if item.get("status") != "Trading":
                raise TradingError("Instrument is not trading")
            lots, prices = item["lotSizeFilter"], item["priceFilter"]
            step, tick = lots["basePrecision"], prices["tickSize"]
            minimum, min_value = lots["minOrderQty"], lots["minOrderAmt"]
            maximum = lots.get("maxLimitOrderQty", lots.get("maxOrderQty", "0"))
            max_value = lots.get("maxOrderAmt", "0")
        else:
            if item.get("status") != "online":
                raise TradingError("Instrument is not online")
            step = str(Decimal(10) ** -int(item["quantityPrecision"]))
            tick = str(Decimal(10) ** -int(item["pricePrecision"]))
            minimum, min_value = item.get("minOrderQty", "0"), item["minOrderAmount"]
            maximum, max_value = item.get("maxOrderQty", "0"), "0"
            prices = {}
        if item.get("quoteCoin") != "USDT" or not item.get("baseCoin"):
            raise TradingError("Only USDT-quoted spot instruments are supported")
        if qty % positive(step, "quantity step") or price % positive(tick, "price tick"):
            raise TradingError(f"Order violates quantity step {step} or price tick {tick}; no automatic rounding")
        if qty < Decimal(minimum) or qty * price < Decimal(min_value):
            raise TradingError("Order is below exchange minimum quantity or notional")
        if Decimal(maximum) > 0 and qty > Decimal(maximum):
            raise TradingError("Order exceeds exchange maximum quantity")
        if Decimal(max_value) > 0 and qty * price > Decimal(max_value):
            raise TradingError("Order exceeds exchange maximum notional")
        for bound, check in (("minPrice", lambda x: price < x), ("maxPrice", lambda x: price > x)):
            number = Decimal(prices.get(bound, "0"))
            if number > 0 and check(number):
                raise TradingError("Order price is outside instrument bounds")
        return item

    def check_balance(self, order, instrument):
        coin = "USDT" if order["side"] == "buy" else instrument["baseCoin"]
        needed = positive(order["quantity"])
        if order["side"] == "buy":
            # Conservative fee reserve; exchange remains authoritative.
            needed *= positive(order["price"]) * Decimal("1.01")
        if self.available(coin) < needed:
            raise TradingError(f"Insufficient conservative available {coin} balance (includes buy fee reserve)")
