# 本次验证记录

日期：2026-11-01；Python 3.12、Node.js 24、Linux x86_64。

| 检查 | 结果 |
| --- | --- |
| 离线单元测试 | 30 项通过；签名、网络/凭据隔离、金额与精度、确认匹配、过期、并发、超时、脱敏、下载校验 |
| 编译检查 | 通过 |
| Binance bootstrap | npm ci 恢复成功，baw 1.12.0 可运行 |
| Binance status | 官方返回 UNCONNECTED；未发起配对 |
| OKX bootstrap | 官方 v4.6.7 原生二进制下载成功，SHA-256 与固定清单一致 |
| OKX status | 官方返回 loggedIn=false；未发起登录 |
| Bitget 可选 CLI bootstrap | npm ci 恢复成功；CLI 3.0.0，锁文件固定其 SDK 依赖 |
| Bitget 公共 REST | BTCUSDT 现货行情与 instrument 规格均返回有效 JSON |
| Bybit 公共 REST | 当前环境主站和 Testnet 返回不可用页面，JSON 解析拒绝；未绕过限制 |
| 私有余额、Demo/Testnet 下单、实盘提交 | 无账户凭据，未做端到端验证；下单逻辑使用模拟传输验证 |

未提交任何真实交易，未保存任何账户 Key，未把本地运行数据上传到 GitHub。通过离线测试不代表平台实盘接入已验证。
