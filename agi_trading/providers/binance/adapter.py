from ..native import run
from ...security import identifier, positive


class BinanceWallet:
    """Official baw adapter. This release exposes auth, reads and quotes only."""
    def call(self, args, timeout=45):
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
