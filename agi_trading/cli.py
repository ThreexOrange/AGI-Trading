import argparse
import json
import sys
from datetime import datetime, timezone

from . import __version__
from .orders import Journal
from .providers import CATALOG, exchange, wallet
from .runtime import bootstrap, doctor
from .security import TradingError, identifier, redact


def parser():
    root = argparse.ArgumentParser(description="Portable AI trading integrations. JSON output; no implicit live trades.")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("providers")
    commands.add_parser("doctor")
    setup = commands.add_parser("bootstrap", help="Restore an official runtime without storing credentials")
    setup.add_argument("provider", choices=CATALOG)
    for name in ("status", "balances"):
        cmd = commands.add_parser(name)
        cmd.add_argument("provider", choices=CATALOG)
        cmd.add_argument("--network", choices=("live", "testnet"), default=None,
                         help="CEX only; defaults to testnet. Wallet commands use the wallet's own network.")
    for name in ("login", "verify", "addresses", "chains"):
        cmd = commands.add_parser(name)
        cmd.add_argument("provider", choices=("binance", "okx"))
        if name == "verify":
            cmd.add_argument("--session", required=True, help="Pairing ID from login; not a bearer token")
    quote = commands.add_parser("quote", help="On-chain swap quote only; never submits")
    quote.add_argument("provider", choices=("binance", "okx"))
    quote.add_argument("--chain", required=True)
    quote.add_argument("--from-token", required=True)
    quote.add_argument("--to-token", required=True)
    quote.add_argument("--amount", required=True, help="Human-readable source-token quantity")
    ticker = commands.add_parser("ticker", help="Spot CEX data; separate from on-chain swap quotes")
    ticker.add_argument("provider", choices=("bitget", "bybit"))
    ticker.add_argument("--symbol", required=True)
    ticker.add_argument("--network", choices=("live", "testnet"), default="testnet")
    preview = commands.add_parser("order-plan", help="Prepare a spot LIMIT order; does not submit")
    preview.add_argument("provider", choices=("bitget", "bybit"))
    preview.add_argument("--mode", choices=("paper", "testnet", "live"), default="paper")
    preview.add_argument("--symbol", required=True)
    preview.add_argument("--side", choices=("buy", "sell"), required=True)
    preview.add_argument("--quantity", required=True, help="Base-coin units; limit orders only")
    preview.add_argument("--price", required=True, help="USDT per base coin")
    execute = commands.add_parser("execute", help="Execute a reviewed plan once")
    execute.add_argument("plan_id")
    execute.add_argument("--confirm", required=True, help="Exact SHA-256 digest of the reviewed plan")
    status = commands.add_parser("order-status", help="Read exchange status; never retries an order")
    status.add_argument("plan_id")
    return root


def dispatch(args):
    command = args.command
    if command == "providers":
        return CATALOG
    if command == "doctor":
        return doctor()
    if command == "bootstrap":
        return bootstrap(args.provider)
    if command in ("status", "balances"):
        is_wallet = args.provider in ("binance", "okx")
        if is_wallet and args.network:
            raise TradingError("--network is for CEX adapters only; wallet networks are selected by chain")
        adapter = wallet(args.provider) if is_wallet else exchange(args.provider, args.network or "testnet")
        return {"provider": args.provider, "backend": CATALOG[args.provider]["backend"],
                "network": "wallet-managed" if is_wallet else adapter.network,
                "result": getattr(adapter, command)()}
    if command in ("login", "verify", "addresses", "chains", "quote"):
        adapter = wallet(args.provider)
        if command == "verify":
            result = adapter.verify(args.session)
        elif command == "quote":
            result = adapter.quote(args.chain, args.from_token, args.to_token, args.amount)
        else:
            result = getattr(adapter, command)()
        return {"provider": args.provider, "backend": "onchain-wallet", "network": "wallet-managed", "result": result}
    if command == "ticker":
        return {"provider": args.provider, "market": "spot", "network": args.network,
                "result": exchange(args.provider, args.network).ticker(args.symbol)}
    journal = Journal()
    if command == "order-plan":
        return journal.create(args.provider, args.mode, args.symbol, args.side, args.quantity, args.price)
    if command == "execute":
        return journal.execute(identifier(args.plan_id), args.confirm)
    if command == "order-status":
        return journal.reconcile(identifier(args.plan_id))
    raise TradingError("Unknown command")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = {"ok": True, "result": dispatch(args)}
        code = 0
    except (TradingError, KeyError, ValueError, OSError, ArithmeticError) as exc:
        result = {"ok": False, "error": str(exc)}
        code = 1
    except KeyboardInterrupt:
        result = {"ok": False, "error": "Interrupted. If a submission was in progress, reconcile with order-status before any further action."}
        code = 130
    result["observed_at"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(redact(result), ensure_ascii=False, indent=2))
    return_code = code
    if return_code:
        raise SystemExit(return_code)
