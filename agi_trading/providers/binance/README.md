# Binance — Agentic Wallet

通过官方 `@binance/agentic-wallet` / `baw` 使用链上钱包，与 Binance 行情插件和交易所账户 API 权限分开。

`python3 -m agi_trading bootstrap binance` 用本目录 package-lock 恢复依赖，禁止 npm lifecycle scripts；`node_modules` 不提交到 Git。官方 CLI 不受本项目 MIT 许可证覆盖。

公开能力：login、verify、status、balances、addresses、chains、quote。登录仍需用户在 Binance App 核对配对码并批准，Key 不能代替这一流程。会话由官方工具管理，不能保证跨临时环境迁移。

尚未开放链上兑换/转账执行：需要接入官方 token audit、风险判断、特殊代币路由及终态检查后再开放，不通过任意 CLI 透传绕过这些步骤。
