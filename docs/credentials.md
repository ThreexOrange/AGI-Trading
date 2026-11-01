# 连接所需信息

| 平台 | 测试/登录所需 | 实盘所需 |
| --- | --- | --- |
| Binance Agentic Wallet | 在 Binance App 创建钱包并完成配对，检查额度与会话有效期 | 相同 App 授权机制；本版未开放链上执行 |
| OKX Agentic Wallet | bootstrap 恢复官方 CLI，在返回的登录网页完成授权 | 相同钱包授权；本版未开放链上执行 |
| Bitget UTA | `BITGET_DEMO_API_KEY`、`BITGET_DEMO_SECRET_KEY`、`BITGET_DEMO_PASSPHRASE` | `BITGET_API_KEY`、`BITGET_SECRET_KEY`、`BITGET_PASSPHRASE` |
| Bybit UNIFIED | `BYBIT_TESTNET_API_KEY`、`BYBIT_TESTNET_API_SECRET` | `BYBIT_API_KEY`、`BYBIT_API_SECRET` |

先用测试账户的 Read 权限；提交测试订单再启用对应 Trade 权限。实盘采用独立低余额子账户、只开必要的 Read/Trade 权限，不启用 Withdraw；本项目不包含提现接口。Bitget 需要 UTA，Bybit 需要 UNIFIED；传统账户不能被假定兼容。Bybit 本版只支持系统生成的 HMAC Key。

这些变量应在运行环境的专用 secret / environment 配置中设置。**不要把值发送给仓库维护者或粘贴进聊天。** `.env.example` 只有变量名，程序不自动加载任意环境文件。

GitHub Actions Secrets 只注入相应 Actions 作业，不会自动出现在聊天云电脑中。聊天记忆、GitHub public 仓库和本地临时目录都不能充当跨环境凭据库。当前项目未接入某个特定云平台的长期密钥管理服务；需要实际可用的注入入口后才能完成私有连接。

钱包登录会话由官方 CLI 保存。重新安装程序不等于恢复登录；过期或环境变化后可能重新配对，不实现会话跨设备迁移。不得将钱包的 session/access token、助记词或私钥提交到 Git，即使文件已加密也不建议公开。

默认 API host 使用官方国际站；Bybit 可通过 `BYBIT_API_HOST` 选择代码中列出的官方区域域名。必须匹配账户地区及平台规则。不能用随机代理域名注入凭据；遇到区域、网络或权限限制，应停止并报告。
