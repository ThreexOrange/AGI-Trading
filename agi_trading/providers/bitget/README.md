# Bitget — UTA v3

原生 Python 标准库 REST 适配器，包括公开现货行情、交易规格、签名余额查询、现货限价单提交和 clientOid 对账。

测试路由：`--network testnet` / `--mode testnet` 指官方 Demo；同 `api.bitget.com` 域名，发送 `paptrading: 1`，只读取 `BITGET_DEMO_*` 变量。缺少 Demo Key 直接失败，不退回实盘。

`bootstrap bitget` 可额外安装官方 `bgc` CLI 3.0.0，用于开发时 discover；核心 REST 适配器不依赖它。不要通过外部 `bgc` 命令绕过本框架的计划审核与去重机制。

本版不是 Bitget Web3 钱包，不支持传统账户、衍生品、撤单或提现。Demo 是否支持当前账户/品种以平台实时响应为准。
