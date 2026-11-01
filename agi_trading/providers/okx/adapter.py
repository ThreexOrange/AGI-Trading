from ..native import run
from ...security import identifier, positive


class OKXWallet:
    """Official OnchainOS adapter. No execution/risk-override flags exposed."""
    def call(self, args, timeout=45):
        return run("okx", "onchainos", args, timeout)

    def status(self):
        return self.call(["wallet", "status"])

    def balances(self):
        return self.call(["wallet", "balance"])

    def addresses(self):
        return self.call(["wallet", "addresses"])

    def chains(self):
        return self.call(["wallet", "chains"])

    def login(self):
        return self.call(["wallet", "login", "--phase", "init"])

    def verify(self, session):
        return self.call(["wallet", "login", "--phase", "poll", "--session-id", identifier(session)], 330)

    def quote(self, chain, source, target, amount):
        positive(amount)
        return self.call(["swap", "quote", "--chain", identifier(chain),
                          "--from", identifier(source), "--to", identifier(target),
                          "--readable-amount", amount])
