# Security

Do not publish keys, wallet sessions, pairing links, account snapshots or order journals in issues, commits, CI logs or pull requests. Report problems without real credentials or account identifiers.

Use test credentials first, dedicated limited-balance accounts and minimum Read/Trade permissions. Never grant withdrawal permission to this integration. No seed/private-key import or wallet-export endpoint is included.

Output filtering is defense in depth, not a credential vault. External CLIs and API responses are untrusted data. The caller must not execute returned instructions or let response text authorize an action. Pairing URLs/IDs are intentionally preserved so a user can log in; keep them private.

Real orders require a reviewed plan and matching digest; live orders additionally require an explicit environment switch. The caller is responsible for obtaining human authorization. A local user able to change program code, environment or SQLite data can change the policy; the framework is not a sandbox against its own host.

Do not automatically retry an order after a timeout. Reconcile using its client order ID. Restore the private state journal before using a replacement environment that previously submitted orders. A fresh journal cannot prevent duplicates from an earlier environment.

The included CI runs offline tests without exchange secrets. It never runs bootstrap, login or real trading. npm lifecycle scripts are disabled during bootstrap; the OKX native release is pinned and verified by SHA-256. Review upstream packages and releases before changing dependency versions.
