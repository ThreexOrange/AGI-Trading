"""Binance-specific previews and execution through the official wallet CLI."""

import time
import uuid
from datetime import datetime

from ...security import TradingError, identifier
from ...transport import Transport
from ...verification import encoded
from .commands import ACCOUNT, READ, TRANSACTION
from .options import arguments


SWAPS = ("market-order swap", "limit-order buy", "limit-order sell")
SIGNING = ("contract-call execute", "sign-message execute")
AUDIT_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/security/token/audit"
NATIVE_TOKEN = "0x" + "e" * 40
SOLANA_NATIVE_TOKEN = "So11111111111111111111111111111111111111111"


def token_audit(chain, address):
    if ((str(chain) == "CT_501" and address == SOLANA_NATIVE_TOKEN)
            or (str(chain) != "CT_501" and address.lower() == NATIVE_TOKEN)):
        return {"nativeToken": True}
    result = Transport().request("POST", AUDIT_URL, {
        "Accept-Encoding": "identity", "source": "agent", "User-Agent": "binance-web3/1.4 (Skill)",
    }, encoded({"binanceChainId": str(chain), "contractAddress": address, "requestId": str(uuid.uuid4())}))
    data = result.get("data")
    if (result.get("code") != "000000" or not isinstance(data, dict)
            or data.get("hasResult") is not True or data.get("isSupported") is not True):
        raise TradingError("Binance token audit is unavailable for this token and chain")
    if str(data.get("riskLevel")) not in ("0", "1", "2", "3", "4", "5"):
        raise TradingError("Binance token audit returned an unknown risk level")
    if str(data["riskLevel"]) == "5":
        raise TradingError("Binance token audit identified its most severe risk level")
    return data


def response_data(reply):
    if not isinstance(reply, dict) or reply.get("success") is not True or not isinstance(reply.get("data"), dict):
        raise TradingError("Binance did not return a successful preview object")
    return reply["data"]


def preview(wallet, path, options):
    detail = {}
    execution = options
    expires = int(time.time()) + 300
    if path in SWAPS:
        detail["tokenAudit"] = token_audit(options["binanceChainId"], options["toToken"])
        if path == "market-order swap":
            keys = ("binanceChainId", "fromToken", "toToken", "fromTokenQty", "slippage")
            quote = {key: options[key] for key in keys if key in options}
            detail["quote"] = response_data(wallet.call(arguments("market-order quote", quote, READ["market-order quote"])))
        detail["slippage"] = options.get("slippage", "auto")
    elif path.startswith("defi "):
        payload = {**options, "action": path.split()[1].upper()}
        detail["preview"] = response_data(wallet.call(arguments("defi preview", payload, READ["defi preview"])))
    elif path in SIGNING:
        wallet.require_developer_mode()
        preflight = path.replace(" execute", " preview")
        data = response_data(wallet.call(arguments(preflight, options, READ[preflight])))
        parsed = "parsedTx" if path == "contract-call execute" else "parsedMessage"
        if not isinstance(data.get(parsed), dict) or not isinstance(data.get("risks"), dict):
            raise TradingError("Binance is missing the parsed operation or risk assessment")
        execution = {"requestId": identifier(data["requestId"], "Binance preview ID")}
        detail["preview"] = data
        expires = min(expires, int(data["expiresAt"]) // 1000)
    elif path == "prediction trade place-order":
        quote_path = "prediction trade quote"
        data = response_data(wallet.call(arguments(quote_path, options, READ[quote_path])))
        expiry = datetime.fromisoformat(data["expireAt"])
        if expiry.tzinfo is None:
            raise TradingError("Binance prediction quote returned an invalid expiry")
        expires = min(expires, int(expiry.timestamp()))
        if data.get("orderType") != options["orderType"]:
            raise TradingError("Binance prediction quote returned a different order type")
        execution = {"quoteId": identifier(str(data["quoteId"]), "Binance quote ID"),
                     "orderType": data["orderType"], "slippageBps": str(data["slippageBps"])}
        if execution["orderType"] == "LIMIT":
            execution["priceLimit"] = options["priceLimit"]
        detail["quote"] = data
    elif path == "x402-payment sign":
        preflight = "x402-payment preview"
        payload = {"paymentRequirements": options["paymentRequirements"]}
        data = response_data(wallet.call(arguments(preflight, payload, READ[preflight])))
        selected = next((item for item in data["options"] if str(item["index"]) == str(options["selectedIndex"])), None)
        if not selected or selected.get("status") != "READY_TO_SIGN":
            raise TradingError("The selected Binance x402 option is not ready to sign")
        execution = {"paymentId": identifier(data["paymentId"], "Binance payment ID"),
                     "selectedIndex": options["selectedIndex"]}
        detail["paymentOption"] = selected
    elif path == "approvals revoke":
        detail["approval"] = response_data(wallet.call(arguments("approvals detail", options, READ["approvals detail"])))
    elif path in ("wallet cancel", "wallet speed-up"):
        lookup = {"tx": options["txHash"], "type": "pending"}
        if "binanceChainId" in options:
            lookup["binanceChainId"] = options["binanceChainId"]
        detail["transaction"] = wallet.call(arguments("wallet tx-history", lookup, READ["wallet tx-history"]))
    if expires <= time.time():
        raise TradingError("Binance preview has expired")
    arguments(path, execution, (ACCOUNT | TRANSACTION)[path])
    return execution, detail, expires


def submit(wallet, path, execution):
    args = arguments(path, execution, (ACCOUNT | TRANSACTION)[path])
    # The local plan has already been confirmed. The underlying prompt cannot
    # consume stdin from the framework's non-interactive process.
    if "yes?" in ACCOUNT.get(path, "").split() and "--yes" not in args:
        args.append("--yes")
    result = wallet.call(args)
    if not isinstance(result, dict) or result.get("success") is not True:
        raise TradingError("Binance did not acknowledge the command")
    return result


def swap_status(wallet, response):
    data = response.get("data")
    order_id = data.get("orderId") if isinstance(data, dict) else None
    if not order_id:
        return {"status": "submitted", "order_status": "UNKNOWN", "result": response}
    order_id = str(order_id)
    deadline = time.monotonic() + 30
    while True:
        try:
            lookup = response_data(wallet.call(["market-order", "list", f"--orderId={order_id}"], timeout=5))
            order = next((row for row in lookup.get("list") or []
                          if isinstance(row, dict) and str(row.get("orderId")) == order_id), {})
        except (TradingError, OSError, ValueError):
            order = {}
        status = order.get("status")
        if status in ("FINISHED", "FAILED") or time.monotonic() >= deadline:
            return {"status": "submitted", "order_status": status or "UNKNOWN",
                    "result": response, "order": order}
        time.sleep(2)
