# AGI-Trading

面向 AI 助手的可恢复交易工具框架。代码保存在 GitHub，需要时在有终端和网络权限的云环境或本地恢复运行。**不需要常驻服务器。**

Python 3.11+；核心无第三方 Python 依赖。官方钱包工具按需安装，源代码和凭据不打包进本仓库。

**先审查，再连接：** 人和 AI Agent 请从 [REVIEWING.md](REVIEWING.md) 开始；Agent 另见 [AGENTS.md](AGENTS.md)。v0.2 默认拦截联网、Key 签名、安装和官方 CLI 调用，直到本地导入针对当前源码及运行依赖的审查报告。报告应诚实评分并列出问题，允许拒绝和低分；不要求星标或好评。该门槛是应用控制，不能强迫外部 Agent 审计，也不能认证报告作者身份。

[离线测试](https://github.com/ThreexOrange/AGI-Trading/actions/workflows/ci.yml) · [CodeQL 检查](https://github.com/ThreexOrange/AGI-Trading/actions/workflows/codeql.yml) · [提交审查反馈](https://github.com/ThreexOrange/AGI-Trading/issues/new/choose)

## 平台与当前能力

每个平台有自己的子文件夹：[`agi_trading/providers/`](agi_trading/providers)。

| 平台 | 接入对象 | 本版已实现 | 尚未开放 |
| --- | --- | --- | --- |
| [Binance](agi_trading/providers/binance) | 官方 `baw` 链上 Agentic Wallet | 环境恢复、配对、状态、地址、余额、支持链、兑换报价 | 链上交易执行、交易所现货/合约 |
| [OKX](agi_trading/providers/okx) | 官方 OnchainOS 链上钱包 | 固定版本 CLI 恢复、分阶段登录、状态、地址、余额、支持链、兑换报价 | 链上交易执行、交易所现货/合约 |
| [Bitget](agi_trading/providers/bitget) | 交易所 UTA v3 REST | 现货行情、余额、签名请求、现货限价单预览/提交/查询、Demo 路由 | Web3 钱包、合约、提现、撤单 |
| [Bybit](agi_trading/providers/bybit) | 交易所 V5 REST，HMAC 密钥 | 现货行情、余额、签名请求、现货限价单预览/提交/查询、Testnet 路由 | Web3 钱包、RSA/OAuth、合约、提现、撤单 |

**能力实现不代表已连通实盘。** 无凭据测试包含离线单元测试、模拟流程和可用的公共接口；账户与实盘端到端验证需要各使用者自行连接。平台区域限制、账户类型和 Demo 支持范围以实际 API 响应为准，遇到限制停止，不切换为实盘。

## 快速开始

以下命令在独立阅读源码、确认允许执行后运行。连接账户和 bootstrap 前，请按 REVIEWING.md 完成审查与报告导入；本版完整验证流程要求源码 checkout，安装包本身不能替代源码审查。

```bash
git clone https://github.com/ThreexOrange/AGI-Trading.git
cd AGI-Trading
python3 -m agi_trading providers
python3 -m agi_trading doctor
python3 -m unittest discover -s tests -v
```

可选安装为终端命令：`python3 -m pip install -e .`，之后使用 `agi-trading`。需要全量恢复时重新 clone 同一个已审查的提交，重复 bootstrap。GitHub 提供源代码；云端执行权限、网络访问和凭据入口由实际运行环境提供。

### 完全离线的模拟流程

```bash
python3 -m agi_trading order-plan bybit \
  --mode paper --symbol BTCUSDT --side buy --quantity 0.001 --price 50000
```

以上是**虚构价格**示例。返回 `plan.id` 和 `digest`；审核完整计划后，将返回值填入：

```bash
python3 -m agi_trading execute PLAN_ID --confirm EXACT_DIGEST
python3 -m agi_trading order-status PLAN_ID
```

`paper` 只演练意图和执行控制，不联系交易所、不模拟资金、成交、手续费或收益。每个计划五分钟过期，只能认领一次。

### Binance / OKX 钱包

先导入当前源码快照的审查。依赖安装或变化后，再审查包含已安装运行依赖的新快照；原报告不能用于新依赖。

Binance 的官方 CLI 需要 Node.js >=20 和 npm；OKX 使用独立原生二进制：

```bash
python3 -m agi_trading bootstrap binance
python3 -m agi_trading status binance
python3 -m agi_trading login binance
# 在 Binance App 核对配对码并授权；使用 login 返回的 qrCodeId：
python3 -m agi_trading verify binance --session PAIRING_ID
python3 -m agi_trading status binance
python3 -m agi_trading balances binance
```

OKX：

```bash
python3 -m agi_trading bootstrap okx
# 从官方 release 下载固定版本并校验 SHA-256；无需额外安装 skills 或 A2A。
python3 -m agi_trading login okx
# 打开返回的 loginUrl 完成登录，然后使用 authSessionId：
python3 -m agi_trading verify okx --session AUTH_SESSION_ID
python3 -m agi_trading status okx
```

登录与轮询分开是为了先向用户展示链接，再等待授权。verify 最多等待约五分钟，请保持进程运行；最终以 status 为准。配对码、登录链接及配对 ID 仅用于当前登录流程，不应公开发布。

兑换报价：

```bash
python3 -m agi_trading quote binance --chain 56 \
  --from-token USER_VERIFIED_SOURCE_CONTRACT --to-token USER_VERIFIED_TARGET_CONTRACT --amount 0.01
python3 -m agi_trading quote okx --chain ethereum \
  --from-token USER_VERIFIED_SOURCE_CONTRACT --to-token USER_VERIFIED_TARGET_CONTRACT --amount 0.01
```

代币地址应来自用户确认或官方查询。报价不会执行兑换；没有任何 `--force` 或任意原生命令透传接口。钱包网络由钱包及 chain 决定，不会被 CEX 的 `testnet` 选项替换。

### Bitget / Bybit 账户

查看 [`docs/credentials.md`](docs/credentials.md) 和 [`.env.example`](.env.example)。只通过运行环境的安全凭据入口注入，程序不会自动读取 `.env`。不要把真实值粘贴到公开仓库、issue 或聊天中。

```bash
# 不需要额外 Python 依赖。公共行情可无 Key 调用：
python3 -m agi_trading ticker bitget --symbol BTCUSDT --network live
python3 -m agi_trading ticker bybit --symbol BTCUSDT --network testnet
# 配置相应测试凭据后：
python3 -m agi_trading balances bybit --network testnet
python3 -m agi_trading balances bitget --network testnet
python3 -m agi_trading order-plan bybit \
  --mode testnet --symbol BTCUSDT --side buy --quantity 0.001 --price 50000
```

`testnet` 对 Bybit 表示独立 Testnet；对 Bitget 表示官方 Demo（同域名、`paptrading: 1`、独立 Demo Key）。**不会混用实盘 Key。** 示例价格为虚构价格；真实测试前应读取当前盘口和交易规则。

需要实盘时必须准备 `--mode live` 的新计划，再通过外部环境显式设置 `AGI_TRADING_ENABLE_LIVE=1`，审核计划并确认 digest。默认仅允许 BTCUSDT、ETHUSDT，单笔上限 100 USDT；可用环境变量调整。限价单数量始终为基础币单位。

当前仅支持现货限价单，不支持“触价后才下单”的条件单。不能把条件指令替换为立即交易。

## 执行与恢复

- 提交前重新检查交易规则、精度、余额和当前配置；不自动舍入，不自动借币。
- SQLite 原子认领计划，提交前落盘；超时/断线不自动重发。使用同一个 client order ID 查询实际状态。
- `submitted` 是提交确认，**不等于成交**；`order-status` 返回交易所原始订单状态。
- 状态目录默认 `~/.local/state/agi-trading`，权限目录 0700/数据库 0600，禁止放在本源码目录内。
- **云环境清理会丢失本地订单去重记录和官方钱包会话。** 发生过真实提交后，应在合适的私有持久存储中保留 journal 并先对账；没有记录时不能靠重新创建计划保证去重。框架不会自动上传任何运行数据。
- 确认 digest 防止执行内容与预览不一致，它不是人类身份认证。调用方仍需获取真实用户授权，不应让模型自行生成确认。

更多内容：[架构与限制](docs/architecture.md)、[安全约定](SECURITY.md)、[官方来源](docs/sources.md)。本项目不提供选币、收益承诺或交易策略。

## License

本仓库原创代码采用 MIT。官方工具遵循各自条款，不受本仓库许可证覆盖。Binance CLI 当前 npm 标注 `UNLICENSED`；我们只调用官方分发包，不复制其源码或二进制。各平台名称仅用于标明兼容对象，本项目由 3xOrange 独立维护。

## 安全评价与可核验记录

本项目没有“已认证绝对安全”的结论。`audit` 生成离线材料，用户自己的 Agent 或审计人员独立给出报告。审查记录绑定 Git 提交、源码和运行依赖哈希，七天后或版本变化后需重新审查；未解决的高危问题阻止放行。CodeQL/测试/依赖更新用于辅助发现问题，均不构成安全证明。

`review-feedback` 只生成公开反馈草稿；实际用户自愿发布。`review-attestation` 和 `review-verify` 导出/核对内容承诺，适用于未来签名或链上存证；当前没有链上广播、身份认证或安全认证。星标完全自愿，与权限和评分无关。
