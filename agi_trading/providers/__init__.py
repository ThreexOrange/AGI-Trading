"""Separate provider integrations. No third-party source is vendored."""

CATALOG = {
    "binance": {"backend": "onchain-wallet", "binary": "baw", "wallet_reads": True,
                "swap_quote": True, "spot_limit_execute": False, "onchain_execute": False},
    "okx": {"backend": "onchain-wallet", "binary": "onchainos", "wallet_reads": True,
            "swap_quote": True, "spot_limit_execute": False, "onchain_execute": False},
    "bitget": {"backend": "cex-uta-v3", "binary": None, "wallet_reads": False,
               "swap_quote": False, "spot_limit_execute": True, "onchain_execute": False},
    "bybit": {"backend": "cex-v5", "binary": None, "wallet_reads": False,
              "swap_quote": False, "spot_limit_execute": True, "onchain_execute": False},
}


def exchange(name, network="testnet", transport=None):
    from .bitget.adapter import Bitget
    from .bybit.adapter import Bybit
    from ..security import TradingError
    if name not in ("bitget", "bybit"):
        raise TradingError("This command requires the Bitget or Bybit CEX integration")
    return {"bitget": Bitget, "bybit": Bybit}[name](network, transport)


def wallet(name):
    from .binance.adapter import BinanceWallet
    from .okx.adapter import OKXWallet
    from ..security import TradingError
    if name not in ("binance", "okx"):
        raise TradingError("This command requires the Binance or OKX on-chain wallet integration")
    return {"binance": BinanceWallet, "okx": OKXWallet}[name]()
