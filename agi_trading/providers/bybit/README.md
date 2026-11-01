# Bybit — V5

原生 Python 标准库 REST 适配器，使用官方 V5 HMAC 签名；核心无需安装 SDK 或下载第三方脚本。

`testnet` 使用 `api-testnet.bybit.com` 和 `BYBIT_TESTNET_API_KEY` / `BYBIT_TESTNET_API_SECRET`；`live` 使用独立的 `BYBIT_API_KEY` / `BYBIT_API_SECRET`。不支持将 Demo key 当作 Testnet key。区域 host 仅能从适配器中核对过的官方 allowlist 选择，必须匹配账户所属站点。

只支持 UNIFIED 账户、现货限价单和订单状态查询；不启用借币，不支持 RSA/OAuth、杠杆、衍生品、撤单或提现。公共 API 被运行环境/平台区域策略阻止时停止，不使用其他域名规避。
