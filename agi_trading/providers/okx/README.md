# OKX — OnchainOS Wallet

链上钱包接入；与当前 ChatGPT 的 OKX 行情插件及 OKX 交易所 API 是独立能力。

`python3 -m agi_trading bootstrap okx` 从 OKX 官方 GitHub release 下载固定版本 v4.6.7 的 CLI，并匹配本目录 `release.json` 中的 SHA-256。下载产物仅保存在忽略的 `.runtime` 中，不提交到 Git；不安装 skills、workflows 或 A2A，也不改变已有钱包会话。

公开能力：login（init）、verify（poll）、status、balances、addresses、chains、quote。用户打开 login 返回的原始链接授权。包装层没有 `--force` 透传、钱包导出或链上执行能力。
