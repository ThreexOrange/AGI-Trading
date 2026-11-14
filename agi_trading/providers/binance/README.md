# Binance — Agentic Wallet

通过官方 `@binance/agentic-wallet` / `baw` 使用链上钱包，与 Binance 行情插件和交易所账户 API 权限分开。

`python3 -m agi_trading bootstrap binance` 用本目录 package-lock 恢复依赖，禁止 npm lifecycle scripts；`node_modules` 不提交到 Git。官方 CLI 不受本项目 MIT 许可证覆盖。

运行依赖下载到执行命令的环境。在本机执行时，由本机的 `baw` 请求 Binance 官方服务，在云端执行时则由云端环境发出请求。仓库只提供代码和依赖清单。

本项目继续使用官方 CLI 1.12.0，并通过 npm override 将它声明的 Zod 3.23.8 替换为 4.6.7，覆盖 [CVE-2023-54404](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)。升级 CLI 时重新检查是否仍需要此覆盖。

Windows 使用 Node.js 安装包自带的 npm，在 PowerShell 中可将示例里的 `python3` 换成 `python`。如果当前网络需要 HTTP(S) 代理，Node.js 24 可读取已有代理配置。在运行钱包命令前执行 `$env:NODE_USE_ENV_PROXY = '1'`。

已有的 `login`、`verify`、`status`、`balances`、`addresses`、`chains` 和 `quote` 入口继续可用。登录需在 Binance App 核对配对码并批准，会话由官方工具管理。

## 查看命令和查询

```bash
python -m agi_trading binance-commands
python -m agi_trading binance-read "wallet settings"
python -m agi_trading binance-read "wallet tx-history" --options '{"binanceChainId":"56","size":10}'
python -m agi_trading binance-read "wallet balance" --options '{"hideLowValue":"false"}'
python -m agi_trading binance-read "tracker ws" --options '{"smy":true,"duration":10}'
```

命令名使用官方 `baw` 的子命令路径。参数使用 JSON 对象，键对应官方长选项名。目录中带 `?` 的键是布尔开关。PowerShell 中可用 `--options-file` 从 UTF-8 文件传入 JSON。WebSocket 订阅在 1 到 300 秒内收集事件，结束后返回 JSON。批量订阅使用 `addresses` 数组和 `chain-id`。查询涵盖交易记录、Gas、额度、域名、Agent ID、代币授权、预测市场、DeFi、信号、钱包跟踪和排行榜。

## 确认并执行

例如，先为一笔 BNB Chain 钱包转账生成计划。将示例地址替换为 Binance 钱包地址簿中的已核对地址。

```bash
python -m agi_trading binance-plan "wallet send" --options '{"binanceChainId":"56","recipient":"RECIPIENT_ADDRESS","tokenAddress":"0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE","amount":"0.01"}'
python -m agi_trading binance-execute PLAN_ID --confirm DIGEST
python -m agi_trading binance-plan-status PLAN_ID
```

执行前核对计划里的链、代币、数量、收款地址和预览，再传入返回的计划 ID 和摘要。资金相关操作沿用 `AGI_TRADING_ENABLE_LIVE=1` 开关。计划会绑定当前钱包和已审查的运行环境。重复执行同一计划会被拒绝。提交超时后先查询钱包或订单历史。链上转账返回的哈希表示已广播，最终状态可用 `wallet tx-history` 查询。DEX 市价兑换提交后会查询 Binance 订单状态，并保留实际收到的数量及退款数据。

- **兑换和限价单**使用官方代币安全审计。查看风险项、报价和滑点后再确认。市价兑换默认滑点为 `auto`。挂单由 Binance 按触发价执行。
- **DeFi**的存入、赎回、流动性增减及领取奖励会先调用官方预览，返回费用、余额变化和警告。
- **预测市场**下单计划接收官方报价参数，执行使用同一报价 ID、订单类型和滑点。撤单和领取也使用确认流程。
- **x402**签名计划接收 `paymentRequirements` 和 `selectedIndex`，使用 Binance 预览中对应的可签名选项。返回的支付签名只用于原商户请求，由调用方完成请求重放。
- **合约调用和消息签名**需在 Binance App 开启 Developer Mode。计划接收官方预览参数，显示解析后的数据和风险信息，并绑定 Binance 返回的请求 ID。若返回 `PENDING_CONFIRMATION`，在 Binance App 中审批。
- **代币授权、待确认交易及钱包管理**支持撤销授权、加速或取消待确认交易、退出钱包，以及维护信号、跟踪分组和排行榜预设。域名转账先解析再使用已核对的完整地址。

官方参考：[Binance Agentic Wallet CLI 文档](https://github.com/binance/binance-skills-hub/tree/main/skills/binance-web3/binance-agentic-wallet)。
