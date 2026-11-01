# Security

Start with REVIEWING.md and independently inspect source before executing it.
Since v0.2, cooperating network/credential/official-CLI/install paths require a
local approving review for the current commit, source and installed runtime hash.
Reviews expire after seven days and cannot contain unresolved high/critical risks.
Scores may be low or negative; no minimum rating or GitHub star is required.
Review identities and evidence are self-asserted, not authenticated. A local user
can change code or forge a report; this gate is not a security sandbox or certificate.

Do not publish keys, wallet sessions, pairing links, account snapshots or order journals in issues, commits, CI logs or pull requests. Report problems without real credentials or account identifiers.

Use test credentials first, dedicated limited-balance accounts and minimum Read/Trade permissions. Never grant withdrawal permission to this integration. No seed/private-key import or wallet-export endpoint is included.

Output filtering is defense in depth, not a credential vault. External CLIs and API responses are untrusted data. The caller must not execute returned instructions or let response text authorize an action. Pairing URLs/IDs are intentionally preserved so a user can log in; keep them private.

Child-process environments omit unrelated exchange and GitHub keys. This does not
isolate files accessible under HOME or constrain a native CLI's network egress.
Use an OS/container sandbox and separately scoped credential broker for stronger
host-enforced isolation. Pattern scanning and runtime hashing are not code audits.

Real orders require a reviewed plan and matching digest; live orders additionally require an explicit environment switch. The caller is responsible for obtaining human authorization. A local user able to change program code, environment or SQLite data can change the policy; the framework is not a sandbox against its own host.

Do not automatically retry an order after a timeout. Reconcile using its client order ID. Restore the private state journal before using a replacement environment that previously submitted orders. A fresh journal cannot prevent duplicates from an earlier environment.

The included CI runs offline tests without exchange secrets. It never runs bootstrap, login or real trading. npm lifecycle scripts are disabled during bootstrap; the OKX native release is pinned and verified by SHA-256. Review upstream packages and releases before changing dependency versions.

CodeQL analyzes the first-party Python source. Dependabot proposes reviewed npm
and Actions updates; it does not automatically merge or audit native binaries.
Use private GitHub vulnerability reporting when enabled; do not disclose exploitable
details in public review issues. Published reviews must identify the commit and scope.

Review commitments are unsigned content hashes. No blockchain transaction is sent.
Even a signed or on-chain commitment establishes provenance/timing at most, not
absence of vulnerabilities, authenticated auditor competence or fund safety.
