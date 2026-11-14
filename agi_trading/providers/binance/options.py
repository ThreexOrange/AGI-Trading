"""Validated arguments for the pinned Binance wallet commands."""

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from ...security import TradingError, positive
from .commands import ACCOUNT, POSITIONAL, READ, TRANSACTION


def option_schema(specification):
    return {option.rstrip("?"): option.endswith("?") for option in specification.split()}


def arguments(path, options, specification):
    schema = option_schema(specification)
    positional = POSITIONAL.get(path)
    if not isinstance(options, dict):
        raise TradingError("Binance options must be a JSON object")
    unknown = options.keys() - schema.keys() - ({positional} if positional else set())
    if unknown:
        raise TradingError("Unsupported Binance options: " + ", ".join(sorted(unknown)))
    result = path.split()
    if positional:
        value = options.get(positional)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9]{1,160}", value):
            raise TradingError(f"Invalid or missing {positional}")
        result.append(value)
    for key in sorted(options.keys() & schema.keys()):
        value = options[key]
        if schema[key]:
            if type(value) is not bool:
                raise TradingError(f"{key} must be a JSON boolean")
            if value:
                result.append("--" + key)
        else:
            if type(value) not in (str, int) or not str(value) or "\x00" in str(value):
                raise TradingError(f"{key} must be a non-empty string or integer")
            # One argv entry keeps a value that looks like an option from becoming a flag.
            result.append(f"--{key}={value}")
    return result


def read(wallet, path, options):
    if path not in READ:
        raise TradingError("Use binance-plan for account changes and transactions")
    if not isinstance(options, dict):
        raise TradingError("Binance options must be a JSON object")
    if path == "tracker ws":
        return tracker_events(wallet, options)
    args = arguments(path, options, READ[path])
    if path in ("contract-call preview", "sign-message preview"):
        wallet.require_developer_mode()
    return wallet.call(args, timeout=330 if path == "auth verify" else 45)


def tracker_events(wallet, options):
    args = arguments("tracker ws", {key: value for key, value in options.items() if key != "addresses"},
                     READ["tracker ws"])
    duration = str(options.get("duration", ""))
    if not re.fullmatch(r"[1-9][0-9]{0,2}", duration) or int(duration) > 300:
        raise TradingError("tracker ws requires a duration of 1 to 300 seconds")
    timeout = int(duration) + 20
    if "addresses" not in options:
        return wallet.call(args, timeout=timeout, json_lines=True)
    require(options, "chain-id")
    addresses = options["addresses"]
    if not isinstance(addresses, list) or not 1 <= len(addresses) <= 100:
        raise TradingError("addresses must be a JSON array of 1 to 100 wallet addresses")
    for address in addresses:
        validate_address(options["chain-id"], address)
    with TemporaryDirectory(prefix="agi-tracker-") as folder:
        batch = Path(folder) / "addresses.txt"
        batch.write_text("\n".join(addresses), encoding="utf-8")
        return wallet.call([*args, f"--address-list={batch}"], timeout=timeout, json_lines=True)


# The public plan takes preview inputs for these operations. Execution IDs can
# only come from the matching Binance response, never from caller-supplied flags.
PREVIEW_INPUT = {
    "prediction trade place-order": READ["prediction trade quote"],
    "x402-payment sign": READ["x402-payment preview"] + " selectedIndex",
    "contract-call execute": READ["contract-call preview"],
    "sign-message execute": READ["sign-message preview"],
}


def catalog():
    return {"queries": READ, "account_changes": ACCOUNT,
            "transactions": {path: PREVIEW_INPUT.get(path, spec) for path, spec in TRANSACTION.items()},
            "positionals": POSITIONAL,
            "option_format": "JSON object of long option names; ? marks a boolean flag"}


def require(options, *keys):
    missing = [key for key in keys if key not in options]
    if missing:
        raise TradingError("Missing Binance options: " + ", ".join(missing))


def validate_address(chain, address):
    pattern = r"[1-9A-HJ-NP-Za-km-z]{32,44}" if str(chain) == "CT_501" else r"0x[a-fA-F0-9]{40}"
    if not isinstance(address, str) or not re.fullmatch(pattern, address):
        raise TradingError("Provide the full address for the selected chain. Resolve domain names separately.")


def validate_plan(path, options):
    if path not in ACCOUNT and path not in TRANSACTION:
        raise TradingError("Use binance-read for wallet queries and previews")
    arguments(path, options, PREVIEW_INPUT.get(path, (ACCOUNT | TRANSACTION)[path]))
    if path == "wallet send":
        require(options, "recipient", "tokenAddress", "binanceChainId")
        validate_address(options["binanceChainId"], options["recipient"])
        validate_address(options["binanceChainId"], options["tokenAddress"])
        if options.get("max", False) == ("amount" in options):
            raise TradingError("Specify exactly one of amount or max")
    if path in ("market-order swap", "limit-order buy", "limit-order sell"):
        require(options, "binanceChainId", "fromToken", "toToken", "fromTokenQty")
        for key in ("fromToken", "toToken"):
            validate_address(options["binanceChainId"], options[key])
        if path.startswith("limit-order"):
            require(options, "triggerPrice")
    for key in ("amount", "fromTokenQty", "triggerPrice"):
        if key in options:
            positive(options[key], key)
    if path == "signal backtest schedule":
        require(options, "interval")
    if path == "prediction trade place-order":
        require(options, "binanceChainId", "tokenId", "marketTopicId", "side", "amount", "orderType")
        if options["orderType"] == "LIMIT":
            require(options, "priceLimit")
    if path == "x402-payment sign":
        require(options, "paymentRequirements", "selectedIndex")
        if not re.fullmatch(r"[1-9][0-9]*", str(options["selectedIndex"])):
            raise TradingError("selectedIndex must be a positive integer")


def json_options(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique_options)
    except json.JSONDecodeError as exc:
        raise TradingError("Invalid Binance options JSON") from exc


def _unique_options(pairs):
    options = dict(pairs)
    if len(options) != len(pairs):
        raise TradingError("Duplicate keys in Binance options")
    return options
